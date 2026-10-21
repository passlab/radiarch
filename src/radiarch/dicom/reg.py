"""Spatial and Deformable Spatial Registration objects (roadmap R2).

A Spatial Registration lists, for each frame of reference it registers, the
rigid (or affine) 4 × 4 matrices that map that frame into the object's own
frame of reference; successive matrices in a ``MatrixSequence`` compose. A
Deformable Spatial Registration adds, per source frame, a vector grid of
displacements (mm, LPS) stored ``[z][y][x][3]`` with optional pre- and
post-deformation matrices. Registration is roadmap R9's work; here the
objects are read into plain structures the services can use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
import pydicom
from pydicom.dataset import Dataset

from .uids import SOP

Vec3 = Tuple[float, float, float]


class RegistrationError(ValueError):
    pass


def _matrix(seq) -> np.ndarray:
    """Compose the matrices of a MatrixSequence (applied in order) into one 4 × 4."""
    m = np.eye(4)
    for item in seq or []:
        values = [float(v) for v in item.FrameOfReferenceTransformationMatrix]
        if len(values) != 16:
            raise RegistrationError("FrameOfReferenceTransformationMatrix must have 16 values")
        m = np.asarray(values, dtype=np.float64).reshape(4, 4) @ m
    return m


@dataclass
class SpatialRegistration:
    """``matrices[source_for] @ [x, y, z, 1]`` moves a point of the source frame into ``frame_of_reference_uid``."""

    frame_of_reference_uid: str
    matrices: dict = field(default_factory=dict)        # source FoR UID → 4 × 4
    matrix_types: dict = field(default_factory=dict)    # source FoR UID → "RIGID" / "RIGID_SCALE" / "AFFINE"
    sop_instance_uid: str = ""

    def transform_points(self, source_for: str, points_mm: np.ndarray) -> np.ndarray:
        m = self.matrices[source_for]
        pts = np.asarray(points_mm, dtype=np.float64).reshape(-1, 3)
        hom = np.concatenate([pts, np.ones((pts.shape[0], 1))], axis=1)
        return (hom @ m.T)[:, :3]


@dataclass
class DeformableRegistration:
    """One deformation: ``post @ (x + displacement(pre @ x))`` maps the source frame into the registered frame."""

    frame_of_reference_uid: str
    source_frame_of_reference_uid: str
    grid_origin_mm: Vec3
    grid_spacing_mm: Vec3
    displacement_zyx: np.ndarray            # (nz, ny, nx, 3) float32, mm
    pre_matrix: np.ndarray = field(default_factory=lambda: np.eye(4))
    post_matrix: np.ndarray = field(default_factory=lambda: np.eye(4))
    sop_instance_uid: str = ""

    @property
    def grid_shape_zyx(self) -> Tuple[int, int, int]:
        return tuple(int(v) for v in self.displacement_zyx.shape[:3])


def read_registration(src: Union[str, Path, Dataset]) -> Union[SpatialRegistration, List[DeformableRegistration]]:
    ds = src if isinstance(src, Dataset) else pydicom.dcmread(str(src))
    sop = str(getattr(ds, "SOPClassUID", ""))
    if sop == SOP.SPATIAL_REGISTRATION or hasattr(ds, "RegistrationSequence"):
        reg = SpatialRegistration(frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
                                  sop_instance_uid=str(getattr(ds, "SOPInstanceUID", "")))
        for item in ds.RegistrationSequence:
            src_for = str(item.FrameOfReferenceUID)
            mreg = item.MatrixRegistrationSequence[0]
            reg.matrices[src_for] = _matrix(mreg.MatrixSequence)
            reg.matrix_types[src_for] = str(mreg.MatrixSequence[0].FrameOfReferenceTransformationMatrixType) if len(mreg.MatrixSequence) else "RIGID"
        return reg
    if sop == SOP.DEFORMABLE_SPATIAL_REGISTRATION or hasattr(ds, "DeformableRegistrationSequence"):
        out: List[DeformableRegistration] = []
        for item in ds.DeformableRegistrationSequence:
            grid = item.DeformableRegistrationGridSequence[0]
            nx, ny, nz = (int(v) for v in grid.GridDimensions)
            iop = np.asarray([float(v) for v in grid.ImageOrientationPatient])
            if not np.allclose(iop, [1, 0, 0, 0, 1, 0], atol=1e-3):
                raise RegistrationError("only axis-aligned deformation grids are supported")
            data = np.frombuffer(grid.VectorGridData, dtype="<f4")
            if data.size != 3 * nx * ny * nz:
                raise RegistrationError(f"VectorGridData has {data.size} values for a {nx}×{ny}×{nz} grid")
            pre = getattr(item, "PreDeformationMatrixRegistrationSequence", None)
            post = getattr(item, "PostDeformationMatrixRegistrationSequence", None)
            out.append(DeformableRegistration(
                frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
                source_frame_of_reference_uid=str(item.SourceFrameOfReferenceUID),
                grid_origin_mm=tuple(float(v) for v in grid.ImagePositionPatient),
                grid_spacing_mm=tuple(float(v) for v in grid.GridResolution),
                displacement_zyx=np.ascontiguousarray(data.reshape((nz, ny, nx, 3))),
                pre_matrix=_matrix(pre) if pre else np.eye(4),
                post_matrix=_matrix(post) if post else np.eye(4),
                sop_instance_uid=str(getattr(ds, "SOPInstanceUID", "")),
            ))
        return out
    raise RegistrationError(f"not a Spatial or Deformable Spatial Registration (SOP class {sop or 'missing'})")


__all__ = ["RegistrationError", "SpatialRegistration", "DeformableRegistration", "read_registration"]
