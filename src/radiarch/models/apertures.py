"""Models of the aperture step (roadmap R4): sequencing an optimization into a deliverable plan."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .common import ResearchArtifact
from .optimization import ConstraintSpec, ConvergenceInfo, ObjectiveSpec


class SequenceRequest(BaseModel):
    """``POST /optimize/{optimization_id}/sequence``.

    The optimization's weights become step-and-shoot apertures on
    ``machine_model_id``; the segment metersets are re-optimized against
    ``objectives`` and ``constraints`` (the optimization's own, resent).
    """

    plan_id: Optional[str] = Field(default=None, max_length=36)
    objectives: List[ObjectiveSpec] = Field(..., min_length=1, max_length=256)
    constraints: List[ConstraintSpec] = Field(default_factory=list, max_length=256)
    machine_model_id: Optional[str] = Field(default=None, description="Null = the beam model's machine, else the default photon machine.")
    levels: int = Field(default=10, ge=1, le=100, description="Fluence quantization steps per beam.")
    energy_mv: Optional[float] = Field(default=None, gt=0.0)
    solver_method: str = Field(default="L-BFGS-B")
    max_iterations: int = Field(default=200, ge=1, le=100_000)

    def compute_cache_key(self, optimization_id: str) -> str:
        payload = {
            "optimization_id": optimization_id,
            "objectives": [o.hash() for o in self.objectives],
            "constraints": [c.hash() for c in self.constraints],
            "machine_model_id": self.machine_model_id,
            "levels": self.levels,
            "energy_mv": self.energy_mv,
            "solver": self.solver_method,
            "max_iterations": self.max_iterations,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class BeamDeliverabilityReport(BaseModel):
    beam_id: str
    n_segments: int
    total_mu: float
    min_segment_mu: float
    min_segment_area_mm2: float
    max_leaf_travel_mm: float
    beam_on_time_s: float
    leaf_travel_time_s: float
    issues: List[str] = Field(default_factory=list)


class SequenceResult(ResearchArtifact):
    """A deliverable plan: segments with MLC apertures and MU, its beamlet dose, the deliverability report."""

    sequence_id: str
    cache_key: str
    optimization_id: str
    geometry_id: str
    source_beam_model_id: str = Field(..., description="The open-field beam model the optimization used.")
    beam_model_id: str = Field(..., description="The new beam model holding the aperture plan.")
    dose_id: str = Field(..., description="The dose of the segments (beamlet doses × segment MU), in dose_units.")
    machine_model_id: str
    n_segments: int
    total_mu: float
    segment_mu: List[float]
    segments_per_beam: Dict[str, int]
    levels: int
    dropped_segments: int
    convergence: ConvergenceInfo
    deliverability: List[BeamDeliverabilityReport]
    deliverable: bool = Field(..., description="No deliverability issue was reported.")
    dose_units: str = "Gy"
    plan_id: Optional[str] = None
    created_at: Optional[datetime] = None


__all__ = ["SequenceRequest", "BeamDeliverabilityReport", "SequenceResult"]
