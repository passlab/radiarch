"""Multi-criteria optimization (roadmap R11): the Pareto set of a beam model.

An MCO run takes convex trade-off objectives (``ObjectiveSpec.is_tradeoff``) and hard constraints, and computes
Pareto-optimal plans: anchors, a balance plan and sandwich plans to a stated error bound
(``docs/reports/mco-research-and-design.md``, D3). It stores each plan's weights and objective values, and every
plan's dose on the *navigation voxels* (the structures the objectives, constraints and requested goals name), so
navigation needs no dose calculation (D4).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from .common import ResearchArtifact
from .dose import EngineSpec
from .job import JobState
from .optimization import HardConstraint, ObjectiveSpec, SolverConfig, check_tradeoffs

MCO_VERSION = "1"
MAX_TRADEOFFS = 8


class MCORunRequest(BaseModel):
    """Input for ``POST /api/v1/mco/run``.

    ``tradeoffs`` are the objectives the planner will trade; their ``weight`` is ignored (the algorithm sets the
    weights). ``plan_budget`` counts every plan, anchors included, and defaults to ``3 N + 1``; generation stops
    earlier when the error bound falls to ``error_tolerance`` (in the objectives normalized to ideal 0, nadir 1).
    ``navigation_structures`` adds structures whose dose navigation should show (a goal template's organs)."""

    plan_id: Optional[str] = Field(default=None, max_length=36, description="Owning plan id (not in the cache key).")
    geometry_id: str = Field(..., min_length=1, max_length=36)
    beam_model_id: str = Field(..., min_length=1, max_length=36)
    dose_engine: EngineSpec
    tradeoffs: List[ObjectiveSpec] = Field(..., min_length=2, max_length=MAX_TRADEOFFS)
    hard_constraints: List[HardConstraint] = Field(default_factory=list, max_length=64)
    solver: SolverConfig = Field(default_factory=lambda: SolverConfig(method="L-BFGS-B", max_iterations=300))
    plan_budget: Optional[int] = Field(default=None, ge=3, le=4 * MAX_TRADEOFFS + 1)
    error_tolerance: float = Field(default=0.05, gt=0.0, le=1.0)
    anchor_epsilon: float = Field(default=1e-3, gt=0.0, le=0.1,
                                  description="Weight of the other objectives in an anchor plan, so it is Pareto optimal.")
    navigation_structures: List[str] = Field(default_factory=list, max_length=64)
    rbe: Optional[float] = Field(default=None, gt=0.0, le=2.0)

    @model_validator(mode="after")
    def _tradeoffs(self) -> "MCORunRequest":
        check_tradeoffs(self.tradeoffs)
        names = [f"{o.type}({o.structure_name})" for o in self.tradeoffs]
        if len(set(names)) != len(names):
            raise ValueError("two trade-offs of the same type on the same structure")
        if self.plan_budget is not None and self.plan_budget > 4 * len(self.tradeoffs) + 1:
            raise ValueError(f"plan_budget at most 4 N + 1 = {4 * len(self.tradeoffs) + 1} for {len(self.tradeoffs)} trade-offs")
        return self

    @property
    def budget(self) -> int:
        n = len(self.tradeoffs)
        return self.plan_budget if self.plan_budget is not None else 3 * n + 1

    def compute_cache_key(self) -> str:
        payload = {
            "version": MCO_VERSION,
            "geometry_id": self.geometry_id,
            "beam_model_id": self.beam_model_id,
            "engine": {"name": self.dose_engine.name, "version": self.dose_engine.key_version(), "params": self.dose_engine.params},
            "tradeoffs": [o.model_copy(update={"weight": 1.0}).hash() for o in self.tradeoffs],
            "hard_constraints": [c.hash() for c in self.hard_constraints],
            "solver": self.solver.hash(),
            "budget": self.budget,
            "error_tolerance": round(self.error_tolerance, 9),
            "anchor_epsilon": round(self.anchor_epsilon, 12),
            "navigation_structures": sorted(set(self.navigation_structures)),
            "rbe": self.rbe,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ParetoPlan(BaseModel):
    index: int
    kind: str = Field(..., description="anchor, balance or sandwich")
    weights: List[float] = Field(..., description="The weight of each trade-off in the sum this plan minimizes.")
    values_gy: List[float] = Field(..., description="Each trade-off's value at this plan, in Gy.")
    normalized: List[float] = Field(..., description="The same, normalized to ideal 0 and nadir 1.")
    converged: bool = True


class ErrorPoint(BaseModel):
    plans: int
    error: float = Field(..., description="The sandwich bound on the distance from any Pareto point to the plans' "
                                          "convex hull, in normalized objectives.")


class MCOStage(str, Enum):
    queued = "queued"
    loading = "loading"
    feasibility = "feasibility"
    anchors = "anchors"
    sandwich = "sandwich"
    persisting = "persisting"
    done = "done"


class MCOResult(ResearchArtifact):
    mco_id: str
    cache_key: str
    geometry_id: str
    beam_model_id: str
    engine_name: str
    engine_version: str
    rbe_factor: float = 1.0
    dose_units: str = "Gy"
    tradeoffs: List[ObjectiveSpec]
    hard_constraints: List[HardConstraint] = Field(default_factory=list)
    ideal_gy: List[float] = Field(..., description="Each trade-off's best value over the anchor plans.")
    nadir_gy: List[float] = Field(..., description="Each trade-off's worst value over the anchor plans.")
    plans: List[ParetoPlan]
    error_history: List[ErrorPoint] = Field(default_factory=list)
    error_bound: float
    converged: bool = Field(..., description="The error bound reached the tolerance within the budget.")
    stop_reason: str = ""
    notes: List[str] = Field(default_factory=list)
    navigation_structures: List[str] = Field(default_factory=list, description="Structures whose voxels the stored doses cover.")
    navigation_voxels: int = 0
    weights_uri: str = Field(..., description="Every plan's element weights (.npy, plans x elements).")
    navigation_dose_uri: str = Field(..., description="Every plan's dose on the navigation voxels (.npy, plans x voxels).")
    compute_time_s: float = 0.0
    created_at: Optional[datetime] = None


class MCOJobStatus(BaseModel):
    id: str
    cache_key: str
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: Optional[MCOStage] = MCOStage.queued
    message: Optional[str] = None
    mco_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


__all__ = ["MCO_VERSION", "MAX_TRADEOFFS", "MCORunRequest", "ParetoPlan", "ErrorPoint", "MCOStage", "MCOResult", "MCOJobStatus"]
