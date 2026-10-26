"""Planning protocols (roadmap R10): everything an auto-plan needs, as data.

A protocol names the site and the prescription, the structures to derive from the patient's (margins, rings, unions,
with aliases for the names centres use), the planning goals the optimizer is driven by, any extra objectives, the
beam arrangement (static fields, sequenced into apertures, or VMAT arcs), the machine and engine, the planning loop's
settings, and the goal template the finished plan is evaluated against. Running it on a geometry gives a
deliverable plan normalised to the main target's coverage goal.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .common import ResearchArtifact
from .dose import EngineSpec
from .geometry import StructureOperation
from .job import JobState
from .optimization import ObjectiveSpec
from .vmat import ArcSpec


class PlanningGoal(BaseModel):
    """A goal the planning loop drives: ``D95`` (the dose to 95 % of the volume), ``Dmax``, ``Dmean`` or ``Dxx``, in Gy."""

    structure: str = Field(..., max_length=128)
    metric: str = Field(..., pattern=r"^(D\d+(\.\d+)?|Dmax|Dmean)$")
    op: Literal[">=", "<="]
    gy: float = Field(..., ge=0.0)
    dmax_term: bool = Field(default=True, description="An organ's DVH goal also gets a maximum-dose term (off for parallel organs around the target).")


class Prescription(BaseModel):
    target: str = Field(..., max_length=128, description="The main target: the plan is normalised to its first coverage goal.")
    dose_gy: float = Field(..., gt=0.0)
    fractions: int = Field(..., ge=1, le=100)


class BeamArrangement(BaseModel):
    technique: Literal["imrt", "vmat"]
    # static fields (imrt)
    count: int = Field(default=7, ge=1, le=36)
    start_deg: float = Field(default=0.0, ge=0.0, lt=360.0)
    spacing_deg: Optional[float] = Field(default=None, gt=0.0, description="Null = 360 / count.")
    sequence_levels: int = Field(default=10, ge=1, le=100, description="Fluence levels per beam when sequencing into apertures.")
    # arcs (vmat)
    arcs: List[ArcSpec] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _arcs_for_vmat(self) -> "BeamArrangement":
        if self.technique == "vmat" and not self.arcs:
            raise ValueError("a VMAT arrangement needs its arcs")
        return self


class PlanningProtocol(BaseModel):
    protocol_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(..., max_length=200)
    site: str = Field(..., max_length=64)
    version: str = Field(default="1", max_length=16)
    description: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=500, description="Where the goals come from (a trial protocol, a guideline).")
    prescription: Prescription
    structure_aliases: Dict[str, List[str]] = Field(default_factory=dict,
                                                    description="Protocol name → names a patient's structure set may use; the first found is copied to the protocol name.")
    structures: List[StructureOperation] = Field(default_factory=list, max_length=64, description="Derivations, in order, after the aliases.")
    goals: List[PlanningGoal] = Field(..., min_length=1, max_length=64)
    extra_objectives: List[ObjectiveSpec] = Field(default_factory=list, max_length=64, description="Beyond the goals' own (rings, for instance).")
    beams: BeamArrangement
    machine: str = Field(default="synthetic-120", max_length=64)
    engine: EngineSpec = Field(default_factory=lambda: EngineSpec(name="pb"))
    beamlet_mm: float = Field(default=5.0, gt=0.0, le=20.0)
    jaw_margin_mm: float = Field(default=10.0, ge=0.0, le=50.0)
    iterations: int = Field(default=150, ge=1, le=10_000)
    rounds: int = Field(default=3, ge=1, le=10, description="Goal-driven fluence rounds.")
    arc_rounds: int = Field(default=3, ge=1, le=10, description="Goal-driven meterset rounds on the arcs (VMAT).")
    evaluation_template: Optional[str] = Field(default=None, description="A goal template the finished plan is evaluated against.")

    @model_validator(mode="after")
    def _main_target_has_coverage(self) -> "PlanningProtocol":
        t = self.prescription.target
        if not any(g.structure == t and g.op == ">=" for g in self.goals):
            raise ValueError(f"the main target {t!r} needs a coverage goal (>=) to normalise to")
        return self

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode("utf-8")).hexdigest()


class ProtocolRunRequest(BaseModel):
    geometry_id: str = Field(..., max_length=36)
    protocol_id: Optional[str] = Field(default=None, description="A shipped protocol (``GET /protocols``).")
    protocol: Optional[PlanningProtocol] = Field(default=None, description="Or one given in full.")

    @model_validator(mode="after")
    def _one_protocol(self) -> "ProtocolRunRequest":
        if bool(self.protocol_id) == bool(self.protocol):
            raise ValueError("give exactly one of protocol_id or protocol")
        return self


class GoalOutcome(BaseModel):
    structure: str
    metric: str
    op: str
    gy: float
    achieved: Optional[float] = None
    passed: Optional[bool] = Field(default=None, description="Null when the patient lacks the structure.")


class ProtocolRunResult(ResearchArtifact):
    run_id: str
    protocol: PlanningProtocol
    geometry_id: str = Field(..., description="The patient's geometry the run started from.")
    planning_geometry_id: str = Field(..., description="With the protocol's aliases and derived structures.")
    optimization_id: str
    sequence_id: Optional[str] = None
    vmat_id: Optional[str] = None
    beam_model_id: str = Field(..., description="The deliverable plan, its metersets normalised.")
    dose_id: str = Field(..., description="Its dose, normalised.")
    normalisation: float = Field(..., description="The factor the metersets were scaled by so the main target meets its coverage goal.")
    goals: List[GoalOutcome] = Field(default_factory=list)
    passed: bool = Field(..., description="Every planning goal the patient has a structure for is met.")
    deliverable: bool
    evaluation_id: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    seconds: float = 0.0
    cache_key: str
    created_at: Optional[datetime] = None


class AutoplanStage(str, Enum):
    queued = "queued"
    structures = "structures"
    planning = "planning"
    deliverable = "deliverable"
    evaluating = "evaluating"
    done = "done"


class AutoplanJobStatus(BaseModel):
    id: str
    cache_key: str
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: Optional[AutoplanStage] = AutoplanStage.queued
    message: Optional[str] = None
    run_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


__all__ = ["PlanningGoal", "Prescription", "BeamArrangement", "PlanningProtocol", "ProtocolRunRequest", "GoalOutcome",
           "ProtocolRunResult", "AutoplanStage", "AutoplanJobStatus"]
