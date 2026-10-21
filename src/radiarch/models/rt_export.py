"""Models of the RT object export (roadmap R6).

An export turns one of radiarch's plans — an aperture sequence, a proton
optimization or a beam model with its own metersets — into the DICOM RT
objects of a case: the structure set of its geometry, the plan, the dose
(and the dose per beam when asked), one DRR per beam. Treatment records are
written afterwards against an export, one per session, plus the course
summary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from .beam_model import Modality
from .common import ResearchArtifact
from .dose import EngineSpec

OBJECT_KINDS = ("rtstruct", "rtplan", "rtdose", "rtimage")


class PrescriptionSpec(BaseModel):
    dose_gy: float = Field(..., gt=0.0, description="Total prescribed dose over the course.")
    fractions: int = Field(default=1, ge=1)
    target_structure: Optional[str] = Field(default=None, max_length=128, description="Structure the dose is prescribed to; null = the geometry's target.")


class RTExportRequest(BaseModel):
    """Which plan to export, and what to write. Exactly one of ``sequence_id``,
    ``optimization_id`` and ``beam_model_id`` names the plan."""

    sequence_id: Optional[str] = Field(default=None, max_length=36, description="An aperture sequence (photons): its plan carries the segment MU and its dose is the segment dose.")
    optimization_id: Optional[str] = Field(default=None, max_length=36, description="A proton optimization: its weights become the spot metersets; its dose is written.")
    beam_model_id: Optional[str] = Field(default=None, max_length=36, description="A beam model whose plan has its own metersets (an imported plan, a basic plan).")
    dose_id: Optional[str] = Field(default=None, max_length=36, description="The dose to write with a beam model; null = none.")
    plan_id: Optional[str] = Field(default=None, max_length=36)
    label: str = Field(default="radiarch", max_length=64)
    description: str = Field(default="", max_length=200)
    machine_name: str = Field(default="RADIARCH", max_length=16)
    prescription: Optional[PrescriptionSpec] = None
    structures: Optional[List[str]] = Field(default=None, max_length=64, description="Structures to write; null = every structure of the geometry.")
    objects: List[str] = Field(default_factory=lambda: list(OBJECT_KINDS), description="Which objects to write.")
    per_beam_dose: bool = Field(default=False, description="Also write one BEAM-summation dose per beam (an engine run per beam, cached).")
    engine: Optional[EngineSpec] = Field(default=None, description="Engine for the per-beam doses; null = the plan's dose engine.")
    drr_size_mm: Tuple[float, float] = Field(default=(300.0, 300.0))
    drr_pixel_mm: Tuple[float, float] = Field(default=(1.0, 1.0))
    rtstruct_uid: Optional[str] = Field(default=None, max_length=64, description="Reference an existing structure set instead of writing one.")
    push: bool = Field(default=False, description="Push the objects with STOW-RS to RADIARCH_DICOMWEB_URL after writing.")

    @model_validator(mode="after")
    def _one_source(self) -> "RTExportRequest":
        given = [k for k in ("sequence_id", "optimization_id", "beam_model_id") if getattr(self, k)]
        if len(given) != 1:
            raise ValueError("give exactly one of sequence_id, optimization_id or beam_model_id")
        bad = [o for o in self.objects if o not in OBJECT_KINDS]
        if bad:
            raise ValueError(f"unknown objects {bad}; choose from {list(OBJECT_KINDS)}")
        if "rtstruct" not in self.objects and "rtplan" in self.objects and not self.rtstruct_uid:
            raise ValueError("an RT Plan references a structure set: write rtstruct too or give rtstruct_uid")
        if self.per_beam_dose and "rtdose" not in self.objects:
            raise ValueError("per_beam_dose needs rtdose among the objects")
        return self


class RTObjectRef(BaseModel):
    kind: str = Field(..., description="RTSTRUCT, RTPLAN, RTIONPLAN, RTDOSE, RTIMAGE, RTRECORD or RTSUMMARY.")
    file_name: str
    path: str
    sop_class_uid: str
    sop_instance_uid: str
    series_instance_uid: str
    beam: Optional[str] = None
    summation: Optional[str] = None
    fraction_number: Optional[int] = None
    size_bytes: int = 0


class RTExportResult(ResearchArtifact):
    export_id: str
    geometry_id: str
    beam_model_id: str
    dose_id: Optional[str] = None
    plan_id: Optional[str] = None
    modality: Modality
    directory: str
    study_instance_uid: str
    frame_of_reference_uid: str
    rtstruct_uid: Optional[str] = None
    plan_sop_class_uid: Optional[str] = None
    plan_sop_instance_uid: Optional[str] = None
    beam_numbers: Dict[str, int] = Field(default_factory=dict)
    beam_metersets: Dict[str, float] = Field(default_factory=dict)
    n_fractions: int = 1
    prescription: Optional[PrescriptionSpec] = None
    machine_name: str = "RADIARCH"
    objects: List[RTObjectRef] = Field(default_factory=list)
    pushed: bool = False
    push_error: Optional[str] = None
    created_at: Optional[datetime] = None


class SessionSpec(BaseModel):
    fraction_number: int = Field(..., ge=1)
    treatment_date: str = Field(..., pattern=r"^\d{8}$", description="YYYYMMDD")
    treatment_time: str = Field(default="120000", pattern=r"^\d{6}$")
    delivered: float = Field(default=1.0, ge=0.0, le=1.0, description="Share of every specified meterset delivered.")
    termination: str = Field(default="NORMAL", pattern=r"^(NORMAL|OPERATOR|MACHINE|UNKNOWN)$")
    verification: str = Field(default="VERIFIED", pattern=r"^(VERIFIED|VERIFIED_OVR|NOT_VERIFIED)$")
    machine_name: Optional[str] = Field(default=None, max_length=16)
    beam_delivered: Dict[str, float] = Field(default_factory=dict, description="Per beam name, overrides `delivered`.")
    couch_vertical_mm: Optional[float] = None
    couch_longitudinal_mm: Optional[float] = None
    couch_lateral_mm: Optional[float] = None


class RTRecordRequest(BaseModel):
    sessions: List[SessionSpec] = Field(..., min_length=1, max_length=200)
    summary: bool = Field(default=True, description="Also write the RT Treatment Summary Record of the course so far.")
    status: Optional[str] = Field(default=None, pattern=r"^(NOT_STARTED|ON_TREATMENT|ON_BREAK|SUSPENDED|STOPPED|COMPLETED)$",
                                  description="Summary status; null = COMPLETED when every planned fraction is delivered, else ON_TREATMENT.")
    comment: str = Field(default="", max_length=200)
    push: bool = False


class RTRecordResult(ResearchArtifact):
    export_id: str
    objects: List[RTObjectRef]
    fractions_delivered: int
    fractions_planned: int
    status: str
    pushed: bool = False
    push_error: Optional[str] = None


class RTPushRequest(BaseModel):
    url: Optional[str] = Field(default=None, max_length=512, description="STOW-RS base URL; null = RADIARCH_DICOMWEB_URL.")
    username: Optional[str] = None
    password: Optional[str] = None
    kinds: Optional[List[str]] = Field(default=None, description="Object kinds to push; null = all.")


class RTPushResult(BaseModel):
    export_id: str
    pushed: int
    url: str
    error: Optional[str] = None


__all__ = ["OBJECT_KINDS", "PrescriptionSpec", "RTExportRequest", "RTObjectRef", "RTExportResult", "SessionSpec",
           "RTRecordRequest", "RTRecordResult", "RTPushRequest", "RTPushResult"]
