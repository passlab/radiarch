"""Models of the VMAT step (roadmap R8): an optimization of sector beams becomes arcs."""

from __future__ import annotations

import hashlib
import math
import json
from datetime import datetime
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from .common import ResearchArtifact
from .dose import EngineSpec
from .optimization import ConstraintSpec, ConvergenceInfo, ObjectiveSpec
from .photon_plan import arc_step_deg


class ArcSpec(BaseModel):
    """One arc: from ``start_deg`` to ``stop_deg`` turning ``direction`` (equal angles: a full turn), cut into
    ``sectors`` of equal width. The fluence optimization uses one static beam at each sector's centre
    (:meth:`sector_centres_deg`, in the order of the beam model's beams); the arc has a control point about every
    ``control_point_spacing_deg`` (adjusted so every sector holds the same number of intervals)."""

    arc_id: str = Field(..., min_length=1, max_length=48)
    start_deg: float = Field(..., ge=0.0, lt=360.0)
    stop_deg: float = Field(..., ge=0.0, lt=360.0)
    direction: Literal["CW", "CC"] = "CW"
    sectors: int = Field(default=18, ge=1, le=90)
    control_point_spacing_deg: float = Field(default=2.0, ge=1.0, le=4.0)
    couch_deg: float = Field(default=0.0, ge=-90.0, le=90.0)
    collimator_deg: float = 0.0

    @property
    def length_deg(self) -> float:
        step = abs(arc_step_deg(self.start_deg, self.stop_deg, self.direction))
        return 360.0 if step < 1e-9 else float(step)

    @property
    def intervals_per_sector(self) -> int:
        return max(1, int(math.ceil(self.length_deg / (self.sectors * self.control_point_spacing_deg) - 1e-9)))

    @property
    def spacing_deg(self) -> float:
        """The control-point spacing actually used."""
        return self.length_deg / (self.sectors * self.intervals_per_sector)

    @property
    def sign(self) -> float:
        return 1.0 if self.direction == "CW" else -1.0

    def control_point_angles_deg(self) -> List[float]:
        n = self.sectors * self.intervals_per_sector
        return [float((self.start_deg + self.sign * k * self.spacing_deg) % 360.0) for k in range(n + 1)]

    def sector_centres_deg(self) -> List[float]:
        k = self.intervals_per_sector
        return [float((self.start_deg + self.sign * (s + 0.5) * k * self.spacing_deg) % 360.0) for s in range(self.sectors)]

    def sector_beam_ids(self) -> List[str]:
        return [f"{self.arc_id}-S{s + 1:02d}" for s in range(self.sectors)]


def sector_beams(arcs: List[ArcSpec]) -> List[Tuple[str, float, float, float]]:
    """``(beam_id, gantry_deg, couch_deg, collimator_deg)`` of the static sector beams the fluence optimization of
    ``arcs`` uses (the arc's couch and collimator, so its fluence maps are in the arc's beam's-eye view)."""
    return [(bid, g, a.couch_deg, a.collimator_deg) for a in arcs for bid, g in zip(a.sector_beam_ids(), a.sector_centres_deg())]


class ArcRequest(BaseModel):
    """``POST /optimize/{optimization_id}/arcs``: the optimization's sector beams become ``arcs``; each sector's
    fluence is swept by the leaves across the sector, the control-point doses are recomputed by
    ``dose_engine`` and the control-point metersets re-optimized against ``objectives`` and ``constraints``
    (the optimization's own, resent) within the machine's gantry-speed, leaf-speed and dose-rate limits."""

    plan_id: Optional[str] = Field(default=None, max_length=36)
    objectives: List[ObjectiveSpec] = Field(..., min_length=1, max_length=256)
    constraints: List[ConstraintSpec] = Field(default_factory=list, max_length=256)
    arcs: List[ArcSpec] = Field(..., min_length=1, max_length=8)
    machine_model_id: Optional[str] = Field(default=None, description="Null = the beam model's machine, else the default photon machine.")
    energy_mv: Optional[float] = Field(default=None, gt=0.0)
    fractions: int = Field(default=1, ge=1, le=100, description="The objectives' doses are for this many fractions; the machine delivers one at a time, so its limits apply to the metersets divided by this.")
    dose_engine: EngineSpec = Field(default_factory=lambda: EngineSpec(name="pb"),
                                    description="The engine that recomputes the control-point doses; it needs segment_dose_matrix (pb).")
    solver_method: str = Field(default="L-BFGS-B")
    max_iterations: int = Field(default=200, ge=1, le=100_000)

    def compute_cache_key(self, optimization_id: str) -> str:
        payload = {
            "optimization_id": optimization_id,
            "objectives": [o.hash() for o in self.objectives],
            "constraints": [c.hash() for c in self.constraints],
            "arcs": [a.model_dump() for a in self.arcs],
            "machine_model_id": self.machine_model_id,
            "energy_mv": self.energy_mv,
            "fractions": self.fractions,
            "engine": {"name": self.dose_engine.name, "version": self.dose_engine.key_version(), "params": self.dose_engine.params},
            "solver": self.solver_method,
            "max_iterations": self.max_iterations,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


class ArcDeliverabilityReport(BaseModel):
    arc_id: str
    direction: str
    start_deg: float
    stop_deg: float
    n_control_points: int
    control_point_spacing_deg: float
    fractions: int = 1
    total_mu: float = Field(..., description="Per fraction.")
    delivery_time_s: float = Field(..., description="Per fraction, at the machine's limits: each interval takes the longest of the gantry, leaf and dose-rate times.")
    gantry_speed_deg_s: Tuple[float, float] = Field(..., description="(slowest, fastest) gantry speed over the intervals.")
    mean_dose_rate_mu_min: float
    max_leaf_travel_mm: float = Field(..., description="The largest leaf move between two control points.")
    intervals_at_dose_rate_floor: int = Field(..., description="Intervals whose meterset is the machine's minimum dose rate over the interval's time.")
    issues: List[str] = Field(default_factory=list)


class ArcResult(ResearchArtifact):
    """A VMAT plan: arcs with control points, its recomputed dose, the deliverability report."""

    vmat_id: str
    cache_key: str
    optimization_id: str
    geometry_id: str
    source_beam_model_id: str = Field(..., description="The sector beam model the optimization used.")
    beam_model_id: str = Field(..., description="The new beam model holding the arc plan.")
    dose_id: str = Field(..., description="The arc plan's dose (control-point apertures, full kernel), in dose_units.")
    machine_model_id: str
    engine_name: str
    engine_version: str
    n_control_points: int
    total_mu: float = Field(..., description="For all fractions (the plan's metersets); the arcs report per fraction.")
    fractions: int = 1
    arcs: List[ArcDeliverabilityReport]
    convergence: ConvergenceInfo
    deliverable: bool = Field(..., description="No deliverability issue was reported.")
    dose_units: str = "Gy"
    plan_id: Optional[str] = None
    created_at: Optional[datetime] = None


__all__ = ["ArcSpec", "sector_beams", "ArcRequest", "ArcDeliverabilityReport", "ArcResult"]
