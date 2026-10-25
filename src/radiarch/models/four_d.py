"""4D planning on a respiratory-correlated CT (roadmap R9): the average-intensity CT, the internal target volume
over the breathing phases, a plan's dose on every phase and its deformable accumulation on a reference phase.

The phases of a 4DCT share one frame of reference and, usually, one grid; a structure drawn on a phase is in the
same patient coordinates as on any other. An ITV is therefore the union of the phases' target contours where
those exist, and propagation through a registration fills in the phases where they do not.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from .dose import EngineSpec


class AverageCTRequest(BaseModel):
    """The average-intensity projection (AIP) of a 4DCT: the voxelwise mean of the phases' HU."""

    reference_geometry_id: str = Field(..., max_length=36, description="Its grid, frame of reference and structures are kept.")
    phase_geometry_ids: List[str] = Field(..., min_length=2, max_length=20, description="The phases averaged (include the reference to count it).")


class PhaseStructure(BaseModel):
    geometry_id: str = Field(..., max_length=36)
    structure: str = Field(..., max_length=128)
    registration_id: Optional[str] = Field(default=None, max_length=36,
                                           description="Fixed = the ITV's geometry, moving = this phase: the structure is propagated "
                                                       "through it instead of copied (needed when the grids differ).")


class ITVRequest(BaseModel):
    geometry_id: str = Field(..., max_length=36, description="The geometry that receives the ITV (an AIP or a reference phase).")
    sources: List[PhaseStructure] = Field(..., min_length=1, max_length=20)
    name: str = Field(default="ITV", min_length=1, max_length=64)
    threshold: float = Field(default=0.5, gt=0.0, lt=1.0, description="Partial-volume level of a propagated structure.")


class PhaseDoseRequest(BaseModel):
    """A plan with metersets (apertures and MU, or spot MU) recomputed on each phase's CT."""

    beam_model_id: str = Field(..., max_length=36)
    geometry_ids: List[str] = Field(..., min_length=1, max_length=20)
    engine: EngineSpec = Field(default_factory=lambda: EngineSpec(name="pb"))


class PhaseDose(BaseModel):
    dose_id: str = Field(..., max_length=64)
    registration_id: Optional[str] = Field(default=None, max_length=36,
                                           description="Fixed = the reference, moving = the dose's phase; null when the dose is "
                                                       "already on the reference geometry.")
    weight: Optional[float] = Field(default=None, gt=0.0, description="Share of the delivery (null = equal shares).")


class AccumulateRequest(BaseModel):
    """Doses mapped onto a reference geometry and summed. As shares (the default): the weights are normalised to sum to
    one (breathing phases). Absolute: each weight multiplies its dose as given, as for a treatment course where a
    plan's whole-course dose counts by the fraction of it delivered (fractions given / the plan's fractions)."""

    reference_geometry_id: str = Field(..., max_length=36)
    phases: List[PhaseDose] = Field(..., min_length=1, max_length=20)
    absolute: bool = Field(default=False, description="Use the weights as multipliers instead of shares (needs every weight).")
    phases_as_scenarios: bool = Field(default=False, description="Keep each mapped phase dose as a scenario of the accumulated dose, "
                                                                 "so an evaluation with include_scenarios grades the worst phase (4D robustness).")
    names: Optional[List[str]] = Field(default=None, max_length=20, description="Scenario names, one per phase (default: phase 1, 2, …).")

    @model_validator(mode="after")
    def _weights_all_or_none(self) -> "AccumulateRequest":
        given = [p.weight is not None for p in self.phases]
        if any(given) and not all(given):
            raise ValueError("give a weight for every phase or for none")
        if self.absolute and not all(given):
            raise ValueError("absolute weights need a weight for every dose")
        if self.names is not None and len(self.names) != len(self.phases):
            raise ValueError("give one name per phase")
        return self

    def weights(self) -> List[float]:
        if self.phases[0].weight is None:
            return [1.0 / len(self.phases)] * len(self.phases)
        if self.absolute:
            return [float(p.weight) for p in self.phases]
        total = sum(p.weight for p in self.phases)
        return [p.weight / total for p in self.phases]


__all__ = ["AverageCTRequest", "PhaseStructure", "ITVRequest", "PhaseDoseRequest", "PhaseDose", "AccumulateRequest"]
