"""Image registration between two geometries (roadmap R9).

A registration maps the *fixed* geometry's points into the *moving* geometry: ``T(x) = x + u(x)`` with ``u``
a displacement field on the fixed geometry's grid (ITK's convention). Anything defined on the moving
geometry (its CT, structures, a dose) is brought onto the fixed grid by sampling it at ``T(x)``. The rigid
part and the deformable part are composed into the one field.

Quality follows AAPM TG-132: image similarity inside the body before and after, the Jacobian determinant of
``T`` (folding where it is not positive), and the landmark error when landmarks are given.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class DeformableMethod(str, Enum):
    none = "none"          # rigid only
    demons = "demons"      # diffeomorphic Demons: same modality and calibration (CT to CT, 4DCT phases)
    bspline = "bspline"    # B-spline with normalised correlation: CT to CBCT, a different (linear) calibration


class RigidInit(str, Enum):
    auto = "auto"          # identity when both share a frame of reference, else the image centres
    identity = "identity"
    centres = "centres"    # the centres of the two CT volumes
    moments = "moments"    # the centres of mass of the body


class LandmarkPair(BaseModel):
    """A landmark as a structure on each geometry: the structures' centroids are the points."""

    fixed_structure: str = Field(..., max_length=128)
    moving_structure: str = Field(..., max_length=128)


class RegistrationRequest(BaseModel):
    fixed_geometry_id: str = Field(..., max_length=36)
    moving_geometry_id: str = Field(..., max_length=36)
    rigid: bool = Field(default=True, description="Register rigidly first (six degrees of freedom).")
    rigid_init: RigidInit = RigidInit.auto
    deformable: DeformableMethod = DeformableMethod.demons
    working_spacing_mm: float = Field(default=3.0, ge=1.0, le=8.0, description="Isotropic spacing the images are registered at.")
    hu_window: Tuple[float, float] = Field(default=(-1000.0, 1500.0), description="HU range the images are clipped to.")
    levels: int = Field(default=3, ge=1, le=4, description="Resolution levels (each halves the previous).")
    demons_iterations: int = Field(default=60, ge=1, le=1000, description="Demons iterations at each level.")
    demons_sigma_mm: float = Field(default=6.0, gt=0.0, le=30.0, description="Gaussian regularisation of the Demons field.")
    bspline_grid_mm: float = Field(default=40.0, ge=10.0, le=200.0, description="B-spline control-point spacing.")
    bspline_iterations: int = Field(default=80, ge=1, le=1000)
    bspline_sampling: float = Field(default=0.10, gt=0.0, le=1.0,
                                    description="Fraction of the masked fixed voxels the B-spline metric samples: time against accuracy "
                                                "(on a pancreas CT to cone-beam pair, 20 % took 210 s, 10 % 94 s, 5 % 68 s, the stomach "
                                                "Dice 0.635, 0.626, 0.619).")
    landmarks: List[LandmarkPair] = Field(default_factory=list, max_length=64)

    def cache_key(self, fixed_key: str, moving_key: str) -> str:
        payload = {"fixed": fixed_key, "moving": moving_key, **self.model_dump(mode="json", exclude={"fixed_geometry_id", "moving_geometry_id"}),
                   "algorithm": REGISTRATION_ALGORITHM_VERSION}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


REGISTRATION_ALGORITHM_VERSION = "1.1.0"   # 1.1: the metric masked to the fixed body, the B-spline bounded


class Similarity(BaseModel):
    """Inside the fixed body (HU > -500): mean absolute HU difference and normalised cross-correlation."""

    mean_abs_hu: float
    ncc: float


class JacobianStats(BaseModel):
    min: float
    max: float
    mean: float
    fraction_nonpositive: float = Field(..., description="Fraction of body voxels where the transform folds (Jacobian ≤ 0).")


class LandmarkError(BaseModel):
    fixed_structure: str
    moving_structure: str
    before_mm: float = Field(..., description="Distance between the two centroids with the initial transform only.")
    rigid_mm: Optional[float] = Field(default=None, description="After the rigid step.")
    after_mm: float = Field(..., description="After the full registration.")


class RegistrationQuality(BaseModel):
    before: Similarity
    rigid: Optional[Similarity] = None
    after: Similarity
    jacobian: Optional[JacobianStats] = None
    landmarks: List[LandmarkError] = Field(default_factory=list)
    max_displacement_mm: float = 0.0


class RegistrationResult(BaseModel):
    registration_id: str
    fixed_geometry_id: str
    moving_geometry_id: str
    fixed_frame_of_reference_uid: str
    moving_frame_of_reference_uid: str
    rigid_matrix: List[List[float]] = Field(..., description="4 x 4, fixed patient coordinates (mm) to moving; identity without a rigid step.")
    rigid_parameters: Dict[str, float] = Field(default_factory=dict, description="Rotation about x, y, z (degrees) and translation (mm).")
    deformable: DeformableMethod
    field_uri: str = Field(..., description="Displacement field u on the fixed grid (NIfTI, three components, mm): T(x) = x + u(x).")
    quality: RegistrationQuality
    request: RegistrationRequest
    algorithm_version: str = REGISTRATION_ALGORITHM_VERSION
    seconds: float = 0.0
    cache_key: str
    created_at: Optional[datetime] = None


class MapDoseRequest(BaseModel):
    """Bring a dose computed on the moving geometry onto the fixed one through a registration."""

    dose_id: str = Field(..., max_length=64)


class PropagateRequest(BaseModel):
    """Bring structures of the moving geometry onto the fixed one through a registration."""

    structures: Optional[List[str]] = Field(default=None, max_length=64, description="Moving structures to propagate; null = all.")
    suffix: str = Field(default="", max_length=32, description="Appended to each propagated structure's name (to keep the fixed geometry's own).")
    threshold: float = Field(default=0.5, gt=0.0, lt=1.0, description="A warped mask's partial-volume level kept as inside.")


__all__ = ["DeformableMethod", "RigidInit", "LandmarkPair", "RegistrationRequest", "Similarity", "JacobianStats", "LandmarkError",
           "RegistrationQuality", "RegistrationResult", "MapDoseRequest", "PropagateRequest", "REGISTRATION_ALGORITHM_VERSION"]
