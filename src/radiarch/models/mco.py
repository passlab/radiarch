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
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .common import ResearchArtifact
from .dose import EngineSpec
from .evaluation import GoalSetSpec, GoalsReport
from .job import JobState
from .optimization import HardConstraint, ObjectiveSpec, RobustnessSpec, SolverConfig, check_tradeoffs
from .vmat import ArcSpec

MCO_VERSION = "2"          # 2 (R11.8): solves converge when their cost stops falling; unconverged plans prove no bound; the
                           # penalty starts matched to the objectives; robust smoothing follows the dose level
MAX_TRADEOFFS = 8


class MCORunRequest(BaseModel):
    """Input for ``POST /api/v1/mco/run``.

    ``tradeoffs`` are the objectives the planner will trade; their ``weight`` is ignored (the algorithm sets the
    weights). ``plan_budget`` counts every plan, anchors included, and defaults to ``3 N + 1``; generation stops
    earlier when the error bound falls to ``error_tolerance`` (in the objectives normalized to ideal 0, nadir 1).
    ``navigation_structures`` adds structures whose dose navigation should show (a goal template's organs).

    With ``robustness`` enabled (D8) each plan minimizes the worst scenario of its weighted sum, hard constraints hold
    in every scenario, and the trade-offs' values are their worst cases over the scenarios (their nominal values are
    reported too). Only the ``WORST_CASE`` aggregation applies, and it is the default here."""

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
    robustness: RobustnessSpec = Field(default_factory=RobustnessSpec)

    @model_validator(mode="after")
    def _tradeoffs(self) -> "MCORunRequest":
        check_tradeoffs(self.tradeoffs)
        if self.robustness.enabled:
            if "aggregation" not in self.robustness.model_fields_set:
                self.robustness.aggregation = "WORST_CASE"
            elif self.robustness.aggregation != "WORST_CASE":
                raise ValueError("a robust Pareto set uses the scenario-wise worst case: aggregation must be WORST_CASE")
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
        if self.robustness.enabled:          # only when on, so earlier sets keep their keys
            payload["robustness"] = self.robustness.hash()
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ParetoPlan(BaseModel):
    index: int
    kind: str = Field(..., description="anchor, balance or sandwich")
    weights: List[float] = Field(..., description="The weight of each trade-off in the sum this plan minimizes.")
    values_gy: List[float] = Field(..., description="Each trade-off's value at this plan, in Gy (robust: its worst case over the scenarios).")
    normalized: List[float] = Field(..., description="The same, normalized to ideal 0 and nadir 1.")
    nominal_gy: Optional[List[float]] = Field(default=None, description="Robust: each trade-off's value on the nominal dose.")
    converged: bool = Field(default=True, description="The solve's cost stopped falling: by at most 1e-5 of itself over its "
                                                      "last 50 iterations. Not a proof of optimality.")
    gain: Optional[float] = Field(default=None, description="The gain still on offer when the solve stopped, over its cost at its "
                                  "start: the Frank-Wolfe gap over weights up to twice the largest, the most a plan could still gain "
                                  "if an optimum lies in that box. Reported, not tested: on fluence problems the box makes it "
                                  "a valid but loose bound.")


class ErrorPoint(BaseModel):
    plans: int
    error: float = Field(..., description="The sandwich bound on the distance from any Pareto point to the plans' "
                                          "convex hull, in normalized objectives. Approximate: it takes the converged plans "
                                          "as optimal.")
    seconds: Optional[float] = Field(default=None, description="Time since the run started when the bound was computed (setup "
                                                               "and the dose matrix included).")


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
    error_bound: float = Field(..., description="The last error point's bound (approximate: converged plans are taken "
                                                "as optimal).")
    converged: bool = Field(..., description="The error bound reached the tolerance within the budget.")
    stop_reason: str = ""
    notes: List[str] = Field(default_factory=list)
    navigation_structures: List[str] = Field(default_factory=list, description="Structures whose voxels the stored doses cover.")
    navigation_voxels: int = 0
    voxel_cc: Optional[float] = Field(default=None, description="One dose-grid voxel's volume, for goals in cc.")
    weights_uri: str = Field(..., description="Every plan's element weights (.npy, plans x elements).")
    navigation_dose_uri: str = Field(..., description="Every plan's dose on the navigation voxels (.npy, plans x voxels).")
    modality: Optional[str] = Field(default=None, description="The beam model's modality.")
    scenarios: List[str] = Field(default_factory=list, description="Robust: the scenarios, nominal first (their doses on the "
                                                                   "navigation voxels: navigation_dose_scenarios.npy, scenarios x plans x voxels).")
    robust_gap: Optional[float] = Field(
        default=None, description="Robust: the largest gap, normalized, between a plan's weighted worst cases and the worst "
                                  "scenario of its weighted sum. It is part of the error bound, and more plans do not remove it.")
    compute_time_s: float = 0.0
    created_at: Optional[datetime] = None


class NavigateRequest(BaseModel):
    """``POST /mco/{mco_id}/navigate``: move from a state (the balance plan by default) on the Pareto set (D5).

    Objectives are named as ``Type(Structure)`` (``MeanDose(Heart)``) or by their index. ``move`` sets one slider:
    that objective at most this value in Gy, the others sharing the cost or the gain evenly (in their normalized
    ranges). ``reference`` asks for a point: each listed objective toward its value, the others toward where they
    are. ``clamps`` are upper bounds in Gy that hold whatever else moves; ``locks`` hold objectives at no worse than
    where they are. With neither ``move`` nor ``reference`` the state is re-evaluated (for new goals or clamps)."""

    from_state: str = Field(default="balance", max_length=64)
    move: Dict[str, float] = Field(default_factory=dict, max_length=1)
    reference: Dict[str, float] = Field(default_factory=dict, max_length=MAX_TRADEOFFS)
    clamps: Dict[str, float] = Field(default_factory=dict, max_length=MAX_TRADEOFFS)
    locks: List[str] = Field(default_factory=list, max_length=MAX_TRADEOFFS)
    goals: Optional[GoalSetSpec] = None
    prescription_gy: Optional[float] = Field(default=None, gt=0.0)
    fractions: Optional[int] = Field(default=None, ge=1, le=100)
    dvh_bins: int = Field(default=60, ge=0, le=500, description="DVH points per structure (0: none).")
    name: Optional[str] = Field(default=None, max_length=128)
    save: bool = Field(default=True, description="Store the state (listed by GET /mco/{id}/states).")

    @model_validator(mode="after")
    def _one_kind(self) -> "NavigateRequest":
        if self.move and self.reference:
            raise ValueError("give a move or a reference point, not both")
        return self


class AutoNavigateRequest(BaseModel):
    """``POST /mco/{mco_id}/auto-navigate``: the blend that best meets a goal set, priority by priority (D6).

    Level 1 goals (must) first: the blend that minimizes their summed shortfall (each goal's miss over its value);
    then level 2 with every level-1 goal held: a met goal stays met, a missed one within ``slip`` (a fraction of its
    value) of what level 1 reached; then level 3; then the trade-offs' sum with every goal held. Clamps and locks hold
    throughout."""

    goals: GoalSetSpec
    prescription_gy: Optional[float] = Field(default=None, gt=0.0)
    fractions: Optional[int] = Field(default=None, ge=1, le=100)
    from_state: str = Field(default="balance", max_length=64, description="Where the search starts, and the reference for locks.")
    clamps: Dict[str, float] = Field(default_factory=dict, max_length=MAX_TRADEOFFS)
    locks: List[str] = Field(default_factory=list, max_length=MAX_TRADEOFFS)
    slip: float = Field(default=0.01, ge=0.0, le=0.5)
    dvh_bins: int = Field(default=60, ge=0, le=500)
    name: Optional[str] = Field(default=None, max_length=128)
    save: bool = True


class AutoLevel(BaseModel):
    priority: int
    goals: int
    passed: int
    shortfall_before: float = Field(..., description="Summed relative shortfall of the level's goals at the start.")
    shortfall: float = Field(..., description="The same after the level's search.")


class DVHCurve(BaseModel):
    structure: str
    dose_gy: List[float]
    volume_pct: List[float]


class NavigationState(ResearchArtifact):
    """A point on the Pareto set: a blend of its plans, its exact values and goals (D5)."""

    state_id: str
    mco_id: str
    name: Optional[str] = None
    from_state: Optional[str] = None
    blend: List[float] = Field(..., description="The weight of each Pareto plan; they sum to 1.")
    values_gy: List[float] = Field(..., description="Each trade-off's exact value on the blended dose, in Gy (robust: its worst "
                                                     "case over the scenarios).")
    nominal_gy: Optional[List[float]] = Field(default=None, description="Robust: each trade-off's value on the nominal dose.")
    bound_gy: List[float] = Field(..., description="The blend of the plans' values: an upper bound on the exact values (convexity).")
    normalized: List[float] = Field(..., description="The exact values normalized to ideal 0, nadir 1.")
    clamps: Dict[str, float] = Field(default_factory=dict, description="The upper bounds (Gy) this state holds, by objective name.")
    notes: List[str] = Field(default_factory=list)
    goals: Optional[GoalsReport] = None
    levels: List[AutoLevel] = Field(default_factory=list, description="Automatic navigation: each priority level's search.")
    dvh: List[DVHCurve] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class NormaliseSpec(BaseModel):
    """Scale the deliverable plan's metersets so a target's coverage metric meets its value (R10's normalisation)."""

    structure: str = Field(..., max_length=128)
    metric: str = Field(default="D95", pattern=r"^(D\d+(\.\d+)?|Dmax|Dmean)$")
    gy: float = Field(..., gt=0.0)


class DeliverableRequest(BaseModel):
    """``POST /mco/{mco_id}/deliverable``: a navigation state made into a plan a machine can deliver (D7).

    The state's blend is projected onto the Pareto set (``project``), and its dose becomes the reference the
    deliverable plan mimics: static photon fields are sequenced into apertures (R4), arcs given in ``arcs`` are swept
    (R8), and the segment or control-point metersets are re-optimized against ``ReferenceDose`` objectives on every
    navigation structure; proton spot weights are the plan as they stand. ``targets`` are mimicked as targets (default:
    the structures a target-type trade-off or a ``Dmin``/``gEUD >=`` constraint names); ``target_priority`` weighs them
    against the organs. The deviation table compares the deliverable plan with the navigated one, trade-off by
    trade-off and goal by goal; a deliverable value worse by more than ``tolerance_gy`` (doses) or
    ``tolerance_volume`` (volumes, in % or cc) is flagged."""

    state_id: str = Field(default="balance", max_length=64)
    project: bool = True
    arcs: List[ArcSpec] = Field(default_factory=list, max_length=8)
    fractions: int = Field(default=1, ge=1, le=100, description="For VMAT's machine limits, and EQD2 goals.")
    levels: int = Field(default=10, ge=1, le=100, description="Fluence levels per beam when sequencing apertures.")
    machine_model_id: Optional[str] = None
    targets: List[str] = Field(default_factory=list, max_length=32)
    target_priority: float = Field(default=1.0, gt=0.0, le=1000.0)
    max_iterations: int = Field(default=200, ge=1, le=100_000)
    normalise: Optional[NormaliseSpec] = None
    goals: Optional[GoalSetSpec] = None
    prescription_gy: Optional[float] = Field(default=None, gt=0.0)
    tolerance_gy: float = Field(default=1.0, gt=0.0)
    tolerance_volume: float = Field(default=1.0, gt=0.0)

    def compute_cache_key(self, mco_cache_key: str, blend: List[float]) -> str:
        payload = {"mco": mco_cache_key, "blend": [round(float(v), 9) for v in blend],
                   **self.model_dump(mode="json", exclude={"state_id"})}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class DeviationRow(BaseModel):
    name: str
    kind: str = Field(..., description="trade-off or goal")
    unit: str
    navigated: Optional[float] = None
    projected: Optional[float] = None
    deliverable: Optional[float] = None
    worse_by: Optional[float] = Field(default=None, description="How much worse the deliverable plan is than the navigated (negative: better).")
    flagged: bool = False


class DeliverableStage(str, Enum):
    queued = "queued"
    projecting = "projecting"
    mimicking = "mimicking"
    normalising = "normalising"
    comparing = "comparing"
    done = "done"


class MCODeliverable(ResearchArtifact):
    deliverable_id: str
    cache_key: str
    mco_id: str
    state_id: str
    geometry_id: str
    blend: List[float]
    projected: bool
    technique: str = Field(..., description="imrt (sequenced apertures), vmat (arcs) or proton (spots).")
    optimization_id: str = Field(..., description="The navigated (projected) plan's weights and dose, as an optimization.")
    sequence_id: Optional[str] = None
    vmat_id: Optional[str] = None
    beam_model_id: str = Field(..., description="The deliverable plan.")
    dose_id: Optional[str] = Field(default=None, description="Its dose (photons; a proton plan's dose is the optimization's).")
    normalisation: float = 1.0
    deliverable: bool = Field(..., description="No machine-limit issue was reported.")
    deviation: List[DeviationRow] = Field(default_factory=list)
    flagged: int = 0
    request: Optional[DeliverableRequest] = Field(default=None, description="What it was made with (a viewer makes another state "
                                                                       "deliverable the same way).")
    notes: List[str] = Field(default_factory=list)
    seconds: float = 0.0
    created_at: Optional[datetime] = None


class DeliverableJobStatus(BaseModel):
    id: str
    cache_key: str
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: Optional[DeliverableStage] = DeliverableStage.queued
    message: Optional[str] = None
    deliverable_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
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


__all__ = ["MCO_VERSION", "MAX_TRADEOFFS", "MCORunRequest", "ParetoPlan", "ErrorPoint", "MCOStage", "MCOResult", "NavigateRequest",
           "AutoNavigateRequest", "AutoLevel", "DVHCurve", "NavigationState", "NormaliseSpec", "DeliverableRequest", "DeviationRow",
           "DeliverableStage", "MCODeliverable", "DeliverableJobStatus", "MCOJobStatus"]
