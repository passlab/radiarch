"""Versions, parents, attribution and states of radiarch's artifacts (roadmap R12).

Every artifact radiarch persists — geometry, beam model, influence matrix,
dose, optimization, aperture sequence, beam-angle search, evaluation, RT
export, legacy plan — is a *version*: content-addressed by its cache key,
derived from the versions it read (its parents), produced by a declared
capability (radiarch at a version, an engine at a version, a machine model,
an HU model) from a dataset (the CT study and series, the patient). The
lineage service builds these views from the stores; nothing here is a new
store of results.

A version has a *state*. Radiarch records state transitions, it never
decides them: approval is a human act in the clinic's record system
(smis-ois, F5.4), and radiarch keeps the record of who, under which
authority, with which reference. A version that was ever approved is
immutable: it and every version it derives from can no longer be deleted.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from .common import RESEARCH_USE_ONLY

KINDS = ("geometry", "beam_model", "influence", "dose", "optimization", "sequence", "bao", "evaluation", "rt_export", "plan")


class VersionState(str, Enum):
    draft = "draft"
    approved = "approved"
    superseded = "superseded"
    retired = "retired"


# draft → approved | retired; approved → superseded | retired; superseded → retired
TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    VersionState.draft.value: (VersionState.approved.value, VersionState.retired.value),
    VersionState.approved.value: (VersionState.superseded.value, VersionState.retired.value),
    VersionState.superseded.value: (VersionState.retired.value,),
    VersionState.retired.value: (),
}


class VersionRef(BaseModel):
    kind: str = Field(..., pattern="^(" + "|".join(KINDS) + ")$")
    id: str = Field(..., min_length=1, max_length=64)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"


class DatasetRef(BaseModel):
    """What the version was computed from, as far as radiarch knows it."""

    patient_id: str = ""
    study_instance_uid: str = ""
    ct_series_instance_uid: str = ""
    frame_of_reference_uid: str = ""
    rtstruct_uid: str = ""
    imported_plan_uid: str = Field(default="", description="The DICOM RT Plan a beam model was imported from.")


class Attribution(BaseModel):
    """The capability that produced a version (F2.5): who, with what, from what."""

    capability_id: str = "radiarch"
    capability_version: str
    engine_name: Optional[str] = None
    engine_version: Optional[str] = None
    machine_model_id: Optional[str] = None
    hu_model: Optional[str] = None
    modality: Optional[str] = None
    dataset: DatasetRef = Field(default_factory=DatasetRef)
    intended_use: str = RESEARCH_USE_ONLY


class StateRecord(BaseModel):
    """One recorded transition. ``authority`` names the system that made the decision."""

    state: VersionState
    actor: str = Field(default="", max_length=128, description="Who decided: a role or a user id in the authority's terms.")
    authority: str = Field(default="", max_length=64, description='The deciding system, e.g. "smis-ois"; never radiarch.')
    reference: str = Field(default="", max_length=256, description="The authority's record of the decision (a Task, a UPS, a signature id).")
    note: str = Field(default="", max_length=500)
    superseded_by: Optional[VersionRef] = None
    at: Optional[datetime] = None

    @model_validator(mode="after")
    def _approval_needs_an_authority(self) -> "StateRecord":
        if self.state is VersionState.approved:
            if not self.authority or not self.actor:
                raise ValueError("an approval records the authority that decided it and the actor who did")
            if self.authority.strip().lower() == "radiarch":
                raise ValueError("radiarch records approvals, it does not grant them")
        if self.state is VersionState.superseded and self.superseded_by is None:
            raise ValueError("a superseded version names the version that supersedes it")
        return self


class VersionStatus(BaseModel):
    ref: VersionRef
    state: VersionState = VersionState.draft
    locked: bool = Field(default=False, description="Immutable: this version or one derived from it was approved.")
    history: List[StateRecord] = Field(default_factory=list)


class LineageNode(BaseModel):
    ref: VersionRef
    cache_key: Optional[str] = None
    created_at: Optional[datetime] = None
    parents: List[VersionRef] = Field(default_factory=list)
    attribution: Attribution
    state: VersionState = VersionState.draft
    locked: bool = False
    summary: Dict[str, Any] = Field(default_factory=dict, description="A few identifying facts of the version.")


class LineageEdge(BaseModel):
    child: VersionRef
    parent: VersionRef


class LineageGraph(BaseModel):
    root: VersionRef
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    roots: List[VersionRef] = Field(default_factory=list, description="Versions without parents: the geometries the chain starts from.")
    missing: List[VersionRef] = Field(default_factory=list, description="Referenced versions no store holds any more.")


class DerivationRecord(BaseModel):
    """The SMIS transformation record (manifest schema member ``derivation``) of a version."""

    transformation: Dict[str, Any]
    inputs: List[Dict[str, Any]]
    outputs: Optional[Dict[str, Any]] = None


__all__ = ["KINDS", "VersionState", "TRANSITIONS", "VersionRef", "DatasetRef", "Attribution", "StateRecord", "VersionStatus",
           "LineageNode", "LineageEdge", "LineageGraph", "DerivationRecord"]
