# from __future__ import annotations
# from typing import TYPE_CHECKING
#
# if TYPE_CHECKING:
#     from opentps.core.data.images import ROIMask

__all__ = ['ROIContour']

import logging

import numpy as np
from PIL import Image, ImageDraw
from skimage.draw import polygon2mask

from opentps.core import Event
from opentps.core.data._patientData import PatientData
from opentps.core.processing.imageProcessing import resampler3D
import SimpleITK as sitk

logger = logging.getLogger(__name__)


class ROIContour(PatientData):
    """
    Class for storing a ROI contour. The contour is stored as a list of polygon meshes. Each polygon mesh is a list of
    coordinates (x,y,z) of the vertices of the polygon. The coordinates are in the patient coordinate system.
    A ROI contour can be converted to a binary mask image using the getBinaryMask() method.

    Parameters
    ----------
    name: str
        Name of the ROI contour.
    color: tuple
        Display color of the ROI contour.
    referencedFrameOfReferenceUID: str
        UID of the frame of reference that the ROI contour is referenced to.
    referencedSOPInstanceUIDs: list
        List of SOP instance UIDs of the images that the ROI contour is referenced to.
    polygonMesh: list
        List of polygon meshes that define the ROI contour. Each polygon mesh is a list of coordinates (x,y,z) of the
        vertices of the polygon. The coordinates are in the patient coordinate system.
    """

    def __init__(self, name="ROI contour", displayColor=(0, 0, 0), referencedFrameOfReferenceUID=None):
        super().__init__(name=name)

        self.colorChangedSignal = Event(object)

        self._displayColor = displayColor
        self.referencedFrameOfReferenceUID = referencedFrameOfReferenceUID
        self.referencedSOPInstanceUIDs = []
        self.polygonMesh = []

    @property
    def color(self):
        return self._displayColor

    @color.setter
    def color(self, color):
        self._displayColor = color
        self.colorChangedSignal.emit(self._displayColor)

    def getBinaryMask(self, origin=None, gridSize=None, spacing=None):
        """
        Convert the ROI contour to a binary mask image.

        Parameters
        ---------
        origin: array    (optional)
            Origin of the binary mask image.
        gridSize: array    (optional)
            Grid size of the binary mask image.
        spacing: array    (optional)
            Voxel spacing of the binary mask image.

        Returns
        -------
        mask: ROIMask
            Binary mask image.
        """
        logger.warning(
            "getBinaryMask() is deprecated and will be removed in a future version. "
            "Use ROIContour.get_partial_volume_mask() instead."
        )
        return self.get_partial_volume_mask(
            origin=origin,
            gridSize=gridSize,
            spacing=spacing,
            binarization_threshold=0.5,
        )

    def _round_half_away_from_zero(self, value: float) -> int:
        """Round half values away from zero to avoid banker's rounding shifts."""
        if value >= 0:
            return int(np.floor(value + 0.5))
        return int(np.ceil(value - 0.5))

    def _polygon_to_mask_slice(
        self,
        polygons_xy,
        contour_origin_xy,
        contour_spacing_xy,
        grid_xy,
        precision: int,
        combine_mode: str = "xor",
    ) -> np.ndarray:
        """Convert polygons on one z slice into a partial-volume mask."""
        gx, gy = int(grid_xy[0]), int(grid_xy[1])
        hr_shape = (gx * precision, gy * precision)
        slice_mask = np.zeros((gx, gy), dtype=np.float32)

        ox, oy = float(contour_origin_xy[0]), float(contour_origin_xy[1])
        sx, sy = float(contour_spacing_xy[0]), float(contour_spacing_xy[1])
        shift_x = 0.5 * (1.0 - sx)
        shift_y = 0.5 * (1.0 - sy)
        center_offset = 0.5 * (precision - 1)

        for poly in polygons_xy:
            rows = ((poly[:, 0] + shift_x - ox) / sx) * precision + center_offset
            cols = ((poly[:, 1] + shift_y - oy) / sy) * precision + center_offset
            polygon_mask = polygon2mask(hr_shape, np.column_stack((rows, cols)))

            if precision == 1:
                down = polygon_mask.astype(np.float32)
            else:
                down = polygon_mask.astype(np.float32).reshape(gx, precision, gy, precision).mean(axis=(1, 3))

            if combine_mode == "union":
                slice_mask = np.maximum(slice_mask, down)
            else:
                slice_mask = np.abs(slice_mask - down)

        return np.clip(slice_mask, 0.0, 1.0)

    def _group_polygons_by_z(self, z_tolerance: float = 1e-3) -> dict:
        """Group polygons by z coordinate with tolerance clustering."""
        grouped = {}
        for contour_data in self.polygonMesh:
            coords = np.asarray(contour_data, dtype=float)
            if coords.size < 9 or coords.size % 3 != 0:
                continue
            triplets = coords.reshape(-1, 3)
            z = float(np.median(triplets[:, 2]))
            if z_tolerance > 0:
                z = float(np.round(z / z_tolerance) * z_tolerance)
            grouped.setdefault(z, []).append(triplets[:, :2])
        return grouped

    def _interpolate_between_two_slices(self, lower_slice: np.ndarray, upper_slice: np.ndarray) -> np.ndarray:
        """Blend two slices, using non-zero values when only one side is present."""
        lower = np.clip(lower_slice, 0.0, 1.0).astype(np.float32)
        upper = np.clip(upper_slice, 0.0, 1.0).astype(np.float32)

        out = 0.5 * (lower + upper)
        eps = 1e-8

        lower_zero = np.abs(lower) <= eps
        upper_zero = np.abs(upper) <= eps
        out[lower_zero & (~upper_zero)] = upper[lower_zero & (~upper_zero)]
        out[upper_zero & (~lower_zero)] = lower[upper_zero & (~lower_zero)]

        lower_one = np.abs(lower - 1.0) <= eps
        upper_one = np.abs(upper - 1.0) <= eps
        out[lower_one | upper_one] = 1.0

        return np.clip(out, 0.0, 1.0).astype(np.float32)

    def get_partial_volume_mask(
        self,
        origin,
        gridSize,
        spacing,
        precision=16,
        binarization_threshold=None,
    ):
        """
        Convert the ROI contour to a partial-volume mask image.

        Parameters
        ---------
        origin: array
            Origin of the output mask image.
        gridSize: array
            Grid size of the output mask image.
        spacing: array
            Voxel spacing of the output mask image.
        precision: int (optional)
            Supersampling factor used during rasterization. Higher values improve
            partial-volume accuracy but increase computation time.
        binarization_threshold: float (optional)
            If provided, convert the partial-volume mask to a binary mask using
            this threshold in [0.0, 1.0].

        Returns
        -------
        mask: ROIMask
            Partial-volume ROI mask (or binary mask when
            ``binarization_threshold`` is provided).
        """
        from opentps.core.data.images._roiMask import ROIMask

        if self is None or not hasattr(self, "polygonMesh"):
            raise ValueError("contour must provide a polygonMesh attribute.")

        if spacing is None:
            spacing = (1.0, 1.0, 1.0)

        if precision is None or int(precision) <= 0:
            raise ValueError("precision must be a positive integer.")
        precision = int(precision)

        spacing = np.asarray(spacing, dtype=float)
        origin = np.asarray(origin, dtype=float)
        gridSize = np.asarray(gridSize, dtype=int)

        if spacing.shape[0] != 3 or origin.shape[0] != 3 or gridSize.shape[0] != 3:
            raise ValueError("origin, spacing and gridSize must be 3D.")
        if np.any(spacing <= 0):
            raise ValueError("spacing values must be strictly positive.")
        if np.any(gridSize <= 0):
            raise ValueError("gridSize values must be strictly positive.")

        allX = []
        allY = []
        allZ = []
        for contourData in self.polygonMesh:
            coords = np.asarray(contourData, dtype=float)
            if coords.size < 9 or coords.size % 3 != 0:
                continue
            allX.append(coords[0::3])
            allY.append(coords[1::3])
            allZ.append(float(np.mean(coords[2::3])))

        if not allX or not allY or not allZ:
            return ROIMask(np.zeros(tuple(gridSize.tolist()), dtype=np.float32))

        allX = np.sort(np.concatenate(allX).astype(float))
        allY = np.sort(np.concatenate(allY).astype(float))
        allZ = np.sort(np.asarray(allZ, dtype=float))

        contour_min = np.array([allX[0], allY[0], allZ[0]], dtype=float)
        contour_max = np.array([allX[-1], allY[-1], allZ[-1]], dtype=float)
        target_min = origin.copy()
        target_max = target_min + (gridSize.astype(float) - 1.0) * spacing
        tol = 1e-6
        if np.any(contour_min < target_min - tol) or np.any(contour_max > target_max + tol):
            logger.warning(
                "Output grid does not fully contain contour bounding box in physical space. "
                "This can appear as a shift or truncation, especially at smaller spacing. "
                "Ensure gridSize is scaled with spacing to keep the same physical FOV.",
                RuntimeWarning,
                stacklevel=2,
            )

        zDiff = np.abs(np.diff(allZ))
        zDiff[zDiff == 0] = np.inf
        finite_zDiff = zDiff[np.isfinite(zDiff)]
        native_z_spacing = float(finite_zDiff.min()) if finite_zDiff.size > 0 else float(spacing[2])

        box_start_idx = np.floor((contour_min - origin) / spacing - 0.5).astype(int)
        box_end_idx = np.ceil((contour_max - origin) / spacing + 0.5).astype(int)

        if float(spacing[2]) < native_z_spacing:
            box_end_idx[2] += 1

        box_start_idx = np.maximum(box_start_idx, 0)
        box_end_idx = np.minimum(box_end_idx, gridSize - 1)

        if np.any(box_end_idx < box_start_idx):
            return ROIMask(
                np.zeros(tuple(gridSize.tolist()), dtype=np.float32),
                name=self.name,
                origin=origin,
                spacing=spacing,
                displayColor=self._displayColor,
            )

        box_grid_size = (box_end_idx - box_start_idx + 1).astype(int)
        box_origin = origin + box_start_idx.astype(float) * spacing

        gx, gy, gz = int(box_grid_size[0]), int(box_grid_size[1]), int(box_grid_size[2])
        local_mask3D = np.zeros((gx, gy, gz), dtype=np.float32)

        max_high_res_side = 512
        if max(gx, gy) >= 256:
            adaptive_precision = 1
        else:
            adaptive_precision = max(
                1,
                min(
                    int(precision),
                    int(max_high_res_side / max(gx, gy)) if max(gx, gy) > 0 else int(precision),
                ),
            )

        z_group_tol = max(1e-4, 0.02 * float(spacing[2]))
        grouped = self._group_polygons_by_z(z_tolerance=z_group_tol)
        if not grouped:
            return ROIMask(
                np.zeros(tuple(gridSize.tolist()), dtype=np.float32),
                name=self.name,
                origin=origin,
                spacing=spacing,
                displayColor=self._displayColor,
            )

        interpolate_z = float(spacing[2]) < native_z_spacing

        if interpolate_z:
            grouped_by_k = {}
            for z_val, polys in grouped.items():
                k_global = self._round_half_away_from_zero((float(z_val) - float(origin[2])) / float(spacing[2]))
                k_local = int(k_global - int(box_start_idx[2]))
                if 0 <= k_local < gz:
                    grouped_by_k.setdefault(k_local, []).extend(polys)

            if not grouped_by_k:
                return ROIMask(
                    np.zeros(tuple(gridSize.tolist()), dtype=np.float32),
                    name=self.name,
                    origin=origin,
                    spacing=spacing,
                    displayColor=self._displayColor,
                )

            contour_k = np.array(sorted(grouped_by_k.keys()), dtype=int)
            first_k = int(contour_k[0])
            last_k = int(contour_k[-1])
            native_steps = max(1.0, float(native_z_spacing) / float(spacing[2]))
            hat_half_steps = 0.5 * native_steps
            exact_slice_cache = {}

            for k_exact in contour_k:
                local_mask3D[:, :, int(k_exact)] = self._polygon_to_mask_slice(
                    polygons_xy=grouped_by_k[int(k_exact)],
                    contour_origin_xy=box_origin[:2],
                    contour_spacing_xy=spacing[:2],
                    grid_xy=(gx, gy),
                    precision=adaptive_precision,
                    combine_mode="xor",
                )
                exact_slice_cache[int(k_exact)] = local_mask3D[:, :, int(k_exact)].copy()

            for k in range(gz):
                if k in grouped_by_k:
                    continue

                lower_candidates = contour_k[contour_k < k]
                upper_candidates = contour_k[contour_k > k]

                if lower_candidates.size == 0:
                    d = float(first_k - k)
                    if d <= hat_half_steps:
                        t_hat = d / max(hat_half_steps, 1e-6)
                        local_mask3D[:, :, k] = (1.0 - t_hat) * exact_slice_cache[first_k]
                    continue

                if upper_candidates.size == 0:
                    d = float(k - last_k)
                    if d <= hat_half_steps:
                        t_hat = d / max(hat_half_steps, 1e-6)
                        local_mask3D[:, :, k] = (1.0 - t_hat) * exact_slice_cache[last_k]
                    continue

                k0 = int(lower_candidates[-1])
                k1 = int(upper_candidates[0])
                if k1 <= k0:
                    continue

                local_mask3D[:, :, k] = self._interpolate_between_two_slices(
                    exact_slice_cache[k0],
                    exact_slice_cache[k1],
                )

            for k_exact, exact_slice in exact_slice_cache.items():
                local_mask3D[:, :, k_exact] = exact_slice
        else:
            grouped_z = np.array(sorted(grouped.keys()), dtype=float)
            contour_k_coarse = []
            for z_val in grouped_z:
                k_global = self._round_half_away_from_zero((float(z_val) - float(origin[2])) / float(spacing[2]))
                k_local = int(k_global - int(box_start_idx[2]))
                if 0 <= k_local < gz:
                    contour_k_coarse.append(k_local)

            if not contour_k_coarse:
                return ROIMask(
                    np.zeros(tuple(gridSize.tolist()), dtype=np.float32),
                    name=self.name,
                    origin=origin,
                    spacing=spacing,
                    displayColor=self._displayColor,
                )

            coarse_precision = max(1, min(adaptive_precision, 4))
            coarse_mask_cache = {}
            first_k_coarse = int(min(contour_k_coarse))
            last_k_coarse = int(max(contour_k_coarse))

            for k in range(gz):
                if k < first_k_coarse or k > last_k_coarse:
                    continue
                z_target = float(box_origin[2]) + k * float(spacing[2])
                z_sel = float(grouped_z[int(np.argmin(np.abs(grouped_z - z_target)))])
                polys = grouped[z_sel]
                if not polys:
                    continue
                cache_key = float(z_sel)
                cached_mask = coarse_mask_cache.get(cache_key)
                if cached_mask is None:
                    cached_mask = self._polygon_to_mask_slice(
                        polygons_xy=polys,
                        contour_origin_xy=box_origin[:2],
                        contour_spacing_xy=spacing[:2],
                        grid_xy=(gx, gy),
                        precision=coarse_precision,
                        combine_mode="xor",
                    )
                    coarse_mask_cache[cache_key] = cached_mask
                local_mask3D[:, :, k] = cached_mask

        if binarization_threshold is not None:
            if not (0.0 <= float(binarization_threshold) <= 1.0):
                raise ValueError("binarization_threshold must be in the range [0.0, 1.0].")
            local_mask3D = (local_mask3D >= float(binarization_threshold)).astype(bool)

        mask = ROIMask(
            imageArray=local_mask3D,
            name=self.name,
            origin=box_origin,
            spacing=spacing,
            displayColor=self._displayColor,
        )

        if origin is not None:
            mask3D = np.zeros(tuple(gridSize.tolist()), dtype=np.float32)
            referenceImage = ROIMask(imageArray=mask3D, spacing=spacing, origin=origin)
            resampler3D.resampleImage3DOnImage3D(
                mask,
                referenceImage,
                inPlace=True,
                fillValue=0,
                sitk_interpolator=sitk.sitkNearestNeighbor,
            )

        return mask

    def getCenterOfMass(self, origin=None, gridSize=None, spacing=None):
        """
        Calculate the center of mass of the contour.
        """
        tempMask = self.getBinaryMask(origin=origin, gridSize=gridSize, spacing=spacing)
        centerOfMass = tempMask.centerOfMass
        return centerOfMass

    def getBinaryContourMask(self, origin=(0, 0, 0), gridSize=(100, 100, 100), spacing=(1, 1, 1)):
        """
        Convert the polygon mesh to a binary contour mask image.
        """
        mask3D = np.zeros(gridSize, dtype=bool)

        for contourData in self.polygonMesh:
            coordXY = list(
                zip(
                    ((np.array(contourData[0::3]) - origin[0]) / spacing[0]),
                    ((np.array(contourData[1::3]) - origin[1]) / spacing[1]),
                )
            )
            coordZ = (float(contourData[2]) - origin[2]) / spacing[2]
            sliceZ = int(round(coordZ))

            if sliceZ < 0 or sliceZ >= gridSize[2]:
                logging.warning("Warning: RTstruct slice outside mask boundaries has been ignored for contour " + self.name)
                continue

            img = Image.new('L', (gridSize[0], gridSize[1]), 0)
            if len(coordXY) > 1:
                ImageDraw.Draw(img).polygon(coordXY, outline=1, fill=0)
            mask2D = np.array(img).transpose(1, 0)
            mask3D[:, :, sliceZ] = np.logical_or(mask3D[:, :, sliceZ], mask2D)

        from opentps.core.data.images._roiMask import ROIMask

        contourMask = ROIMask(
            imageArray=mask3D,
            name=self.name,
            origin=origin,
            spacing=spacing,
            displayColor=self._displayColor,
        )

        return contourMask
