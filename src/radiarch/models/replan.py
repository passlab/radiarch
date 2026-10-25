"""Adaptive replanning (roadmap R9): a plan checked on the anatomy of a later image (a re-planning CT or a cone-beam
CT of a treatment day), and the course accumulated when a new plan takes over.

The day's image is the *fixed* image of the registration and the planning CT the *moving* one, so the planning
structures and the planning CT's densities are pulled onto the day's grid. The plan's isocenter moves with the
rigid part of the registration, as the couch shift that sets the patient up to the planning isocenter does.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .common import ResearchArtifact
from .dose import EngineSpec
from .evaluation import GoalSetSpec
from .registration import DeformableMethod, RegistrationQuality, RigidInit


class DensitySource(str, Enum):
    own = "own"                                       # a re-planning CT: its own HU, calibrated
    deformed_planning_ct = "deformed_planning_ct"     # a cone-beam CT: the planning CT's HU deformed onto it


class ReplanAssessRequest(BaseModel):
    planning_geometry_id: str = Field(..., max_length=36)
    day_geometry_id: str = Field(..., max_length=36, description="The later image: a re-planning CT or a cone-beam CT.")
    beam_model_id: str = Field(..., max_length=36, description="The plan, with its metersets (photon apertures and MU).")
    planned_dose_id: Optional[str] = Field(default=None, max_length=64, description="The plan's dose on the planning geometry, to compare.")
    density: DensitySource = DensitySource.deformed_planning_ct
    deformable: DeformableMethod = DeformableMethod.bspline
    rigid_init: RigidInit = RigidInit.auto
    working_spacing_mm: float = Field(default=3.0, ge=1.0, le=8.0)
    structures: Optional[List[str]] = Field(default=None, max_length=64, description="Planning structures to propagate; null = all.")
    suffix: str = Field(default="", max_length=32, description="Appended to propagated names that the day's image already has.")
    engine: EngineSpec = Field(default_factory=lambda: EngineSpec(name="pb"))
    prescription_gy: float = Field(..., gt=0.0)
    target_structure: Optional[str] = Field(default=None, max_length=128)
    fractions: Optional[int] = Field(default=None, ge=1)
    goals: Optional[GoalSetSpec] = None


class GoalComparison(BaseModel):
    structure: str
    metric: str
    op: str
    value: float
    priority: int
    planned: Optional[float] = None
    day: Optional[float] = None
    planned_passed: Optional[bool] = None
    day_passed: Optional[bool] = None


class ReplanAssessment(ResearchArtifact):
    assessment_id: str
    request: ReplanAssessRequest
    registration_id: str
    registration_quality: RegistrationQuality
    day_geometry_id: str = Field(..., description="The day's image with the planning structures propagated (and its density, per request).")
    day_beam_model_id: str = Field(..., description="The plan with its isocenter moved by the rigid registration (the couch shift).")
    day_dose_id: str = Field(..., description="The plan recomputed on the day's anatomy.")
    mapped_planned_dose_id: Optional[str] = Field(default=None, description="The planned dose mapped onto the day's grid, for comparison.")
    isocenter_shift_mm: List[float] = Field(..., description="Day isocenter minus planned isocenter (patient mm).")
    residual_rotation_deg: List[float] = Field(default_factory=list, description="The rigid rotation the couch shift leaves uncorrected.")
    goals: List[GoalComparison] = Field(default_factory=list)
    cache_key: str
    created_at: Optional[datetime] = None


__all__ = ["DensitySource", "ReplanAssessRequest", "GoalComparison", "ReplanAssessment"]
