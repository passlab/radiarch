"""NRRD ingestion — read a CT ``.nrrd`` (+ optional Slicer ``.seg.nrrd``) into
the exact objects the Geometry pipeline already consumes.

Motivation
----------
The production ingest path reads **DICOM** (CT series + RTSTRUCT) via OpenTPS's
``dataLoader.readData``. For fast iteration on real 3D anatomy we also want to
feed the pipeline NRRD volumes exported from 3D Slicer, *without* changing any
downstream code (HU→density, resampling, rasterization, persistence, dose).

The trick: the geometry pipeline is duck-typed at two seams —

* it reads ``ct.imageArray`` / ``ct.spacing`` / ``ct.origin`` from an OpenTPS
  ``CTImage``; and
* the rasterizer (``services/rasterization.py``) only needs, per structure, an
  object with ``.name`` and ``.getBinaryMask(origin, gridSize, spacing) -> obj
  with .imageArray``.

So this module produces a real ``CTImage`` plus a list of tiny
``_SegmentContour`` adapters that satisfy the ``ContourLike`` protocol. Nothing
in ``GeometryService._process`` or the rasterizer has to change.

Axis convention
---------------
OpenTPS stores ``imageArray`` as ``[x, y, z]`` — i.e. ``np.transpose`` of the
``[z, y, x]`` array SimpleITK returns — with ``origin``/``spacing`` taken
straight from the ITK image (see ``opentps/core/io/sitkIO.py:readImage``). We
replicate that exactly, so an NRRD-loaded CT is byte-for-byte convention-
compatible with a DICOM-loaded one.

Orientation
-----------
Any acquisition direction is brought into an axis-aligned LPS frame at load
time (see ``_canonicalize_to_axis_aligned``): identity passes through; axis
flips/swaps are reoriented losslessly; a genuinely oblique (tilted) grid is
resampled onto an axis-aligned grid and the change is logged, not hidden.

Honesty / limitations (surfaced loudly, per the charter)
--------------------------------------------------------
* **CT and segmentation must share a geometry.** If a ``.seg.nrrd`` is handed in
  whose grid (size/origin/spacing) disagrees with the CT, we raise. A silently
  mis-registered mask is worse than no mask. (Note: an oblique CT and its
  oblique segmentation are each resampled to the *same* axis-aligned grid,
  since that grid is a deterministic function of the shared source geometry.)
* **Multi-layer / overlapping Slicer segmentations are not supported yet** —
  a single collapsed label volume is expected (we assert 3D).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
from loguru import logger

from ..models.geometry import GridSpec
from ..services.resampling import resample_to_grid

# Spacing/origin equality tolerance (mm). ITK stores e.g. 1mm as 0.998901, and
# a native-grid getBinaryMask must recognise "same grid" despite float noise.
_TOL_MM = 1e-3


# ---------------------------------------------------------------------------
# Small return type for getBinaryMask — the rasterizer only reads .imageArray.
# ---------------------------------------------------------------------------

@dataclass
class _MaskArray:
    imageArray: np.ndarray  # bool, OpenTPS [x, y, z] convention


@dataclass
class _SegmentContour:
    """A single Slicer segment, adapted to the rasterizer's ``ContourLike``.

    Holds one boolean mask on the segmentation's *native* grid. ``getBinaryMask``
    returns it directly when the requested grid matches native (the fast path,
    which is what ``GeometryService`` does when no explicit target grid is set),
    and nearest-neighbour resamples it otherwise so labels are never blurred.
    """

    name: str
    _mask_xyz: np.ndarray            # bool [x, y, z]
    _origin: Tuple[float, float, float]
    _spacing: Tuple[float, float, float]

    def _is_native(self, origin, gridSize, spacing) -> bool:
        if origin is None or gridSize is None or spacing is None:
            return True
        return (
            tuple(int(s) for s in gridSize) == self._mask_xyz.shape
            and np.allclose(origin, self._origin, atol=_TOL_MM)
            and np.allclose(spacing, self._spacing, atol=_TOL_MM)
        )

    def getBinaryMask(self, origin=None, gridSize=None, spacing=None) -> _MaskArray:
        if self._is_native(origin, gridSize, spacing):
            return _MaskArray(imageArray=self._mask_xyz)

        # Non-native target grid: nearest-neighbour resample the label mask.
        src = GridSpec(
            spacing_mm=tuple(float(s) for s in self._spacing),
            origin_mm=tuple(float(o) for o in self._origin),
            size=tuple(int(s) for s in self._mask_xyz.shape),
        )
        tgt = GridSpec(
            spacing_mm=tuple(float(s) for s in spacing),
            origin_mm=tuple(float(o) for o in origin),
            size=tuple(int(s) for s in gridSize),
        )
        resampled = resample_to_grid(
            self._mask_xyz.astype(np.float32), src.to_numpy_affine(), tgt,
            order=0, cval=0.0,
        )
        return _MaskArray(imageArray=resampled > 0.5)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _canonicalize_to_axis_aligned(image, *, is_label: bool):
    """Return an image whose direction is the identity (axis-aligned LPS).

    OpenTPS ``imageArray`` and our resampler represent only axis-aligned grids,
    so any non-identity acquisition direction must be brought into that frame
    *before* we hand the array downstream. Three cases:

    * **Identity** — already axis-aligned; returned unchanged (fast path).
    * **Signed permutation** (axis flips and/or swaps — the common DICOM case,
      e.g. an ``RAI``/``LPS`` flip): reoriented **losslessly** with
      ``DICOMOrient`` (pure flip/transpose of voxels — no interpolation).
    * **Oblique rotation** (a genuine tilt, e.g. gantry-tilted CT): there is no
      lossless reorientation, so the volume is **resampled** onto an
      axis-aligned grid that bounds its physical extent (nearest-neighbour for
      labels so values are preserved; trilinear for CT). This changes the voxel
      grid — reported by the caller, not hidden.

    Returns ``(image_out, description)``.
    """
    import SimpleITK as sitk

    d = np.asarray(image.GetDirection(), dtype=float)
    if d.size != 9:
        return image, "identity"
    d3 = d.reshape(3, 3)
    if np.allclose(d3, np.eye(3), atol=1e-4):
        return image, "identity"

    # Signed permutation? Every entry is ~0 or ~±1 (direction cols are always
    # orthonormal, so this exactly separates flips/swaps from true rotations).
    absd = np.abs(d3)
    if np.all((absd < 1e-3) | (absd > 1 - 1e-3)):
        out = sitk.DICOMOrient(image, "LPS")
        if not np.allclose(np.asarray(out.GetDirection()).reshape(3, 3),
                           np.eye(3), atol=1e-4):
            raise RuntimeError(  # pragma: no cover — defensive
                "DICOMOrient did not yield an axis-aligned direction; "
                f"got {out.GetDirection()}"
            )
        return out, "reoriented (lossless flip/permute)"

    # Genuine oblique rotation: resample onto an axis-aligned bounding grid.
    origin = np.asarray(image.GetOrigin(), dtype=float)
    spacing = np.asarray(image.GetSpacing(), dtype=float)
    size = np.asarray(image.GetSize(), dtype=float)
    corners = []
    for i in (0, size[0] - 1):
        for j in (0, size[1] - 1):
            for k in (0, size[2] - 1):
                corners.append(origin + d3 @ (spacing * np.array([i, j, k])))
    corners = np.asarray(corners)
    lo = corners.min(axis=0)
    hi = corners.max(axis=0)
    new_size = [int(np.ceil((hi[a] - lo[a]) / spacing[a])) + 1 for a in range(3)]

    ref = sitk.Image(int(new_size[0]), int(new_size[1]), int(new_size[2]),
                     image.GetPixelID())
    ref.SetSpacing(tuple(float(s) for s in spacing))
    ref.SetOrigin(tuple(float(o) for o in lo))
    ref.SetDirection((1, 0, 0, 0, 1, 0, 0, 0, 1))
    interp = sitk.sitkNearestNeighbor if is_label else sitk.sitkLinear
    default = 0.0 if is_label else -1000.0   # air HU outside a resampled CT
    out = sitk.Resample(image, ref, sitk.Transform(), interp, default,
                        image.GetPixelID())
    return out, f"resampled oblique grid -> axis-aligned {tuple(new_size)}"


def _read_itk(path: str | Path, *, is_label: bool = False):
    """Read an ITK image and return ``(array_xyz, origin, spacing, orig_image,
    canon)`` in OpenTPS convention, canonicalized to an axis-aligned grid.

    ``orig_image`` is the *pre-canonicalization* image — used only to read
    metadata (e.g. Slicer ``Segment*`` fields), which reorientation does not
    change since label *values* are preserved.
    """
    import SimpleITK as sitk

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"NRRD file not found: {path}")
    orig_image = sitk.ReadImage(str(path))
    image, canon = _canonicalize_to_axis_aligned(orig_image, is_label=is_label)
    if canon != "identity":
        logger.info("%s: %s", path.name, canon)

    array_xyz = np.transpose(sitk.GetArrayFromImage(image))  # [z,y,x] -> [x,y,z]
    origin = tuple(float(o) for o in image.GetOrigin())
    spacing = tuple(float(s) for s in image.GetSpacing())
    return array_xyz, origin, spacing, orig_image, canon


def load_ct(path: str | Path, *, patient: Any = None):
    """Load a CT ``.nrrd`` into a real OpenTPS ``CTImage`` (HU as float32)."""
    from opentps.core.data.images import CTImage

    array_xyz, origin, spacing, _, _ = _read_itk(path, is_label=False)
    if array_xyz.ndim != 3:
        raise ValueError(
            f"{Path(path).name}: expected a 3D CT volume, got shape {array_xyz.shape}"
        )
    ct = CTImage(
        imageArray=array_xyz.astype(np.float32, copy=False),
        name=Path(path).name,
        origin=origin,
        spacing=spacing,
        seriesInstanceUID=f"NRRD-CT:{Path(path).name}",
        frameOfReferenceUID=f"NRRD-FOR:{Path(path).name}",
        patient=patient,
    )
    logger.info(
        "Loaded NRRD CT %s: shape=%s spacing=%s origin=%s",
        Path(path).name, array_xyz.shape, spacing, origin,
    )
    return ct


def load_segmentation(path: str | Path) -> List[_SegmentContour]:
    """Load a Slicer ``.seg.nrrd`` label volume into per-segment contour adapters.

    Reads ``Segment{i}_Name`` / ``Segment{i}_LabelValue`` metadata to name each
    structure and pick out its label value. Falls back to naming by raw label
    value for any positive label not described in the header.
    """
    array_xyz, origin, spacing, image, _ = _read_itk(path, is_label=True)
    if array_xyz.ndim != 3:
        raise ValueError(
            f"{Path(path).name}: expected a 3D label volume, got shape "
            f"{array_xyz.shape}. Multi-layer/overlapping Slicer segmentations "
            "are not supported yet."
        )
    labels = np.rint(array_xyz).astype(np.int64)

    # Map declared segments: label value -> name (from NRRD metadata fields).
    declared: dict[int, str] = {}
    i = 0
    while image.HasMetaDataKey(f"Segment{i}_LabelValue"):
        lv = int(image.GetMetaData(f"Segment{i}_LabelValue"))
        name = (
            image.GetMetaData(f"Segment{i}_Name")
            if image.HasMetaDataKey(f"Segment{i}_Name")
            else f"Segment_{lv}"
        )
        declared[lv] = name.strip()
        i += 1

    present = sorted(int(v) for v in np.unique(labels) if v > 0)
    contours: List[_SegmentContour] = []
    for lv in present:
        name = declared.get(lv, f"label_{lv}")
        mask = labels == lv
        contours.append(
            _SegmentContour(
                name=name,
                _mask_xyz=mask,
                _origin=origin,
                _spacing=spacing,
            )
        )
    named = ", ".join(f"{c.name}(lv={lv})" for c, lv in zip(contours, present))
    logger.info(
        "Loaded NRRD segmentation %s: %d structure(s) [%s]",
        Path(path).name, len(contours), named,
    )
    if declared and set(present) - set(declared):
        logger.warning(
            "%s: labels %s present in volume but not described in header metadata "
            "— named by raw value.",
            Path(path).name, sorted(set(present) - set(declared)),
        )
    return contours


def _grids_match(ct, contours: List[_SegmentContour]) -> Optional[str]:
    """Return a human-readable reason if any segment's native grid disagrees
    with the CT grid; ``None`` if all consistent."""
    ct_size = tuple(int(s) for s in np.asarray(ct.imageArray).shape)
    ct_origin = tuple(float(o) for o in ct.origin)
    ct_spacing = tuple(float(s) for s in ct.spacing)
    for c in contours:
        if c._mask_xyz.shape != ct_size:
            return (f"segment {c.name!r} size {c._mask_xyz.shape} != CT size {ct_size}")
        if not np.allclose(c._origin, ct_origin, atol=_TOL_MM):
            return (f"segment {c.name!r} origin {c._origin} != CT origin {ct_origin}")
        if not np.allclose(c._spacing, ct_spacing, atol=_TOL_MM):
            return (f"segment {c.name!r} spacing {c._spacing} != CT spacing {ct_spacing}")
    return None


def load_nrrd_case(
    ct_path: str | Path,
    seg_path: Optional[str | Path] = None,
    *,
    patient_name: str = "NRRD_ANONYMOUS",
):
    """Load a CT ``.nrrd`` (+ optional ``.seg.nrrd``) into ``(ct, patient, contours)``.

    This tuple matches what ``GeometryService._load_from_disk`` returns, so the
    caller can wrap it in ``_LoadedCT`` and run the unchanged pipeline.

    Raises if the segmentation grid does not match the CT grid — a mis-registered
    overlay must fail loudly, not be silently trusted.
    """
    from opentps.core.data import Patient

    patient = Patient(name=patient_name)
    ct = load_ct(ct_path, patient=patient)

    contours: List[_SegmentContour] = []
    if seg_path is not None:
        contours = load_segmentation(seg_path)
        reason = _grids_match(ct, contours)
        if reason is not None:
            raise ValueError(
                f"Segmentation geometry does not match the CT: {reason}. "
                "Refusing to build geometry with a mis-registered mask."
            )
    return ct, patient, contours


__all__ = ["load_ct", "load_segmentation", "load_nrrd_case"]
