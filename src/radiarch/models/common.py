"""Shared pieces of every result model.

Every artifact radiarch produces — JSON results, DICOM objects, reports —
carries the same intended-use statement, so that nothing coming out of the
service can be read as clinical output. Result models inherit
:class:`ResearchArtifact` to get the field; writers copy the text into the
objects they produce.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

RESEARCH_USE_ONLY = (
    "RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research "
    "treatment-planning system; its plans, doses and evaluations must not "
    "be used to treat patients."
)

# Short form for DICOM text attributes (LO is limited to 64 characters).
NOT_FOR_CLINICAL_USE = "NOT FOR CLINICAL USE"


class ResearchArtifact(BaseModel):
    """Base class for result models: carries the intended-use statement."""

    disclaimer: str = Field(
        default=RESEARCH_USE_ONLY,
        description="Intended-use statement. Present on every artifact radiarch returns.",
    )


class DicomPlanProvenance(BaseModel):
    """Where an imported plan came from (roadmap R2): the DICOM identifiers a
    recomputed dose must reference and the frame of reference it must share."""

    sop_class: str = Field(default="", description='"RTPLAN" or "RTIONPLAN".')
    sop_instance_uid: str = ""
    series_instance_uid: str = ""
    study_instance_uid: str = ""
    frame_of_reference_uid: str = ""
    structure_set_uid: str = Field(default="", description="ReferencedStructureSetSequence SOP Instance UID.")
    plan_label: str = ""
    plan_name: str = ""
    approval_status: str = ""
    n_fractions: int = 1
    source_path: str = Field(default="", description="File the plan was read from, when known.")


__all__ = ["RESEARCH_USE_ONLY", "NOT_FOR_CLINICAL_USE", "ResearchArtifact", "DicomPlanProvenance"]
