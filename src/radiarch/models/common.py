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


__all__ = ["RESEARCH_USE_ONLY", "NOT_FOR_CLINICAL_USE", "ResearchArtifact"]
