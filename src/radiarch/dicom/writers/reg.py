"""Spatial Registration and Deformable Spatial Registration objects out (roadmap R9).

Both lie in the registered (fixed) frame of reference, the object's own ``FrameOfReferenceUID``:

* a Spatial Registration holds, for the source (moving) frame, the 4 × 4 matrix that moves a point of the source
  frame into the registered frame (PS3.3 C.20.2), the inverse of radiarch's rigid matrix (fixed → moving); an
  identity item for the registered frame itself;
* a Deformable Spatial Registration holds the displacement grid in the registered frame, applied to points of the
  registered frame to give points of the source frame (C.20.3): radiarch's field ``u`` with ``T(x) = x + u(x)``,
  written as it is, with identity pre- and post-deformation matrices (the field already includes the rigid part).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union

import numpy as np
from pydicom.dataset import Dataset

from ..uids import SOP
from .common import CaseContext, ds_list, new_dataset, save, seq, with_frame_of_reference


@dataclass
class REGResult:
    path: str
    sop_class_uid: str
    sop_instance_uid: str
    series_instance_uid: str


def _matrix_item(m: np.ndarray, kind: str = "RIGID") -> Dataset:
    item = Dataset()
    item.FrameOfReferenceTransformationMatrix = ds_list([float(v) for v in np.asarray(m, float).reshape(16)])
    item.FrameOfReferenceTransformationMatrixType = kind
    return item


def _content(ds: Dataset, ctx: CaseContext, label: str, description: str) -> None:
    ds.ContentDate = ctx.date
    ds.ContentTime = ctx.time
    ds.ContentLabel = label[:16]
    ds.ContentDescription = description[:64]
    ds.ContentCreatorName = "radiarch"


def write_spatial_registration(ctx: CaseContext, source_frame_of_reference_uid: str, source_to_registered: np.ndarray,
                               path: Union[str, Path], *, label: str = "RESEARCH", description: str = "",
                               series_number: int = 400, series_instance_uid: str = None) -> REGResult:
    """``ctx.frame_of_reference_uid`` is the registered frame; the matrix moves source-frame points into it."""
    m = np.asarray(source_to_registered, float)
    if m.shape != (4, 4) or not np.allclose(m[3], [0, 0, 0, 1]):
        raise ValueError("the registration matrix must be a 4 x 4 homogeneous transform")
    ds = new_dataset(ctx, SOP.SPATIAL_REGISTRATION, "REG", series_number=series_number, series_instance_uid=series_instance_uid)
    with_frame_of_reference(ds, ctx)
    _content(ds, ctx, label, description or "rigid registration, research use only")
    items = []
    for for_uid, matrix in ((ctx.frame_of_reference_uid, np.eye(4)), (source_frame_of_reference_uid, m)):
        item = Dataset()
        item.FrameOfReferenceUID = for_uid
        mreg = Dataset()
        mreg.MatrixSequence = seq([_matrix_item(matrix)])
        item.MatrixRegistrationSequence = seq([mreg])
        items.append(item)
    ds.RegistrationSequence = seq(items)
    save(ds, path)
    return REGResult(str(path), SOP.SPATIAL_REGISTRATION, str(ds.SOPInstanceUID), str(ds.SeriesInstanceUID))


def write_deformable_registration(ctx: CaseContext, source_frame_of_reference_uid: str, displacement_zyx3: np.ndarray,
                                  grid_origin_mm: Sequence[float], grid_spacing_mm: Sequence[float], path: Union[str, Path], *,
                                  pre: np.ndarray = None, post: np.ndarray = None, label: str = "RESEARCH", description: str = "",
                                  series_number: int = 401, series_instance_uid: str = None) -> REGResult:
    """``displacement_zyx3``: (nz, ny, nx, 3) mm on the registered frame's grid; registered point + vector = source point."""
    d = np.asarray(displacement_zyx3, dtype="<f4")
    if d.ndim != 4 or d.shape[3] != 3:
        raise ValueError("the displacement grid must be (nz, ny, nx, 3)")
    nz, ny, nx = d.shape[:3]
    ds = new_dataset(ctx, SOP.DEFORMABLE_SPATIAL_REGISTRATION, "REG", series_number=series_number, series_instance_uid=series_instance_uid)
    with_frame_of_reference(ds, ctx)
    _content(ds, ctx, label, description or "deformable registration, research use only")
    item = Dataset()
    item.SourceFrameOfReferenceUID = source_frame_of_reference_uid
    grid = Dataset()
    grid.ImagePositionPatient = ds_list([float(v) for v in grid_origin_mm])
    grid.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    grid.GridDimensions = [int(nx), int(ny), int(nz)]
    grid.GridResolution = [float(v) for v in grid_spacing_mm]
    grid.VectorGridData = np.ascontiguousarray(d).tobytes()
    item.DeformableRegistrationGridSequence = seq([grid])
    item.PreDeformationMatrixRegistrationSequence = seq([_matrix_item(np.eye(4) if pre is None else pre)])
    item.PostDeformationMatrixRegistrationSequence = seq([_matrix_item(np.eye(4) if post is None else post)])
    ds.DeformableRegistrationSequence = seq([item])
    save(ds, path)
    return REGResult(str(path), SOP.DEFORMABLE_SPATIAL_REGISTRATION, str(ds.SOPInstanceUID), str(ds.SeriesInstanceUID))


__all__ = ["REGResult", "write_spatial_registration", "write_deformable_registration"]
