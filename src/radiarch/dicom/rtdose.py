"""RT Dose → a volume on radiarch's grid convention (roadmap R2).

An RT Dose is a stack of frames: ``ImagePositionPatient`` locates the first
voxel of the first frame, ``PixelSpacing`` gives the row (y) and column (x)
spacing, and ``GridFrameOffsetVector`` places every frame along z — relative
to the image position when its first value is 0, absolute z otherwise. Only
axis-aligned doses (``ImageOrientationPatient`` 1 0 0 / 0 1 0) are accepted,
which is what every planning system writes. Frames are returned in ascending
z so the result is a ``(z, y, x)`` array with a positive spacing, like every
other radiarch volume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import pydicom
from pydicom.dataset import Dataset
from scipy.ndimage import map_coordinates

from .uids import SOP

Vec3 = Tuple[float, float, float]


class RTDoseError(ValueError):
    pass


@dataclass
class RTDoseVolume:
    """A dose grid in radiarch's frame: ``(z, y, x)`` values in Gy, origin at the
    centre of voxel ``[0, 0, 0]`` in the patient (LPS) frame."""

    dose_zyx: np.ndarray
    spacing_mm: Vec3
    origin_mm: Vec3
    frame_of_reference_uid: str = ""
    dose_units: str = "GY"
    dose_type: str = "PHYSICAL"
    summation_type: str = "PLAN"
    referenced_plan_uid: str = ""
    sop_instance_uid: str = ""
    series_instance_uid: str = ""
    source_path: str = ""

    @property
    def shape_zyx(self) -> Tuple[int, int, int]:
        return tuple(int(v) for v in self.dose_zyx.shape)

    def axis_mm(self, axis: str) -> np.ndarray:
        i = "xyz".index(axis)
        n = self.dose_zyx.shape[2 - i]
        return self.origin_mm[i] + self.spacing_mm[i] * np.arange(n)


def read_rtdose(src: Union[str, Path, Dataset]) -> RTDoseVolume:
    if isinstance(src, Dataset):
        ds, path = src, ""
    else:
        ds, path = pydicom.dcmread(str(src)), str(src)
    if str(getattr(ds, "SOPClassUID", "")) != SOP.RTDOSE and str(getattr(ds, "Modality", "")) != "RTDOSE":
        raise RTDoseError("not an RT Dose object")

    iop = np.asarray([float(v) for v in ds.ImageOrientationPatient], dtype=np.float64)
    if not np.allclose(iop, [1, 0, 0, 0, 1, 0], atol=1e-3):
        raise RTDoseError(f"only axis-aligned doses are supported (ImageOrientationPatient {iop.tolist()})")
    ipp = [float(v) for v in ds.ImagePositionPatient]
    row_spacing, col_spacing = (float(v) for v in ds.PixelSpacing)
    n_frames = int(getattr(ds, "NumberOfFrames", 1))

    offsets = np.asarray([float(v) for v in getattr(ds, "GridFrameOffsetVector", [0.0])], dtype=np.float64)
    if offsets.size != n_frames:
        raise RTDoseError(f"GridFrameOffsetVector has {offsets.size} entries for {n_frames} frames")
    if n_frames > 1:
        z = ipp[2] + offsets if offsets[0] == 0.0 else offsets.copy()    # relative, else absolute z
        dz = np.diff(z)
        if not np.allclose(dz, dz[0], atol=1e-3):
            raise RTDoseError("non-uniform frame spacing is not supported")
        slice_spacing = float(abs(dz[0]))
    else:
        z = np.asarray([ipp[2] + offsets[0]]) if offsets[0] == 0.0 else offsets.copy()
        slice_spacing = float(getattr(ds, "SliceThickness", 1.0) or 1.0)

    arr = ds.pixel_array
    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]
    dose = arr.astype(np.float64) * float(getattr(ds, "DoseGridScaling", 1.0))
    if n_frames > 1 and z[1] < z[0]:
        dose = dose[::-1]
        z = z[::-1]
    return RTDoseVolume(
        dose_zyx=np.ascontiguousarray(dose.astype(np.float32)),
        spacing_mm=(col_spacing, row_spacing, slice_spacing),
        origin_mm=(ipp[0], ipp[1], float(z[0])),
        frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
        dose_units=str(getattr(ds, "DoseUnits", "GY")),
        dose_type=str(getattr(ds, "DoseType", "PHYSICAL")),
        summation_type=str(getattr(ds, "DoseSummationType", "PLAN")),
        referenced_plan_uid=(str(ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID)
                             if getattr(ds, "ReferencedRTPlanSequence", None) else ""),
        sop_instance_uid=str(getattr(ds, "SOPInstanceUID", "")),
        series_instance_uid=str(getattr(ds, "SeriesInstanceUID", "")),
        source_path=path,
    )


def resample_dose_to_grid(dose: RTDoseVolume, origin_mm: Vec3, spacing_mm: Vec3, shape_zyx: Tuple[int, int, int],
                          order: int = 1, fill: float = 0.0) -> np.ndarray:
    """Trilinear resampling of a dose onto a radiarch grid (voxel centres at
    ``origin + index * spacing``); voxels outside the dose grid get ``fill``."""
    nz, ny, nx = (int(v) for v in shape_zyx)
    zz, yy, xx = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    sx, sy, sz = (float(v) for v in spacing_mm)
    ox, oy, oz = (float(v) for v in origin_mm)
    dsx, dsy, dsz = dose.spacing_mm
    dox, doy, doz = dose.origin_mm
    coords = np.stack([
        (oz + zz * sz - doz) / dsz,
        (oy + yy * sy - doy) / dsy,
        (ox + xx * sx - dox) / dsx,
    ])
    out = map_coordinates(dose.dose_zyx.astype(np.float32), coords, order=order, mode="constant", cval=fill, prefilter=(order > 1))
    return out.astype(np.float32)


__all__ = ["RTDoseError", "RTDoseVolume", "read_rtdose", "resample_dose_to_grid"]
