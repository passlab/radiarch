"""``MCOService`` (roadmap R11.2): the Pareto set of a beam model.

The problem is assembled once by :class:`OptimizationService` (geometry, beam model, the cached dose matrix, the
trade-off objectives), the hard constraints are checked by a feasibility run, and the sandwich algorithm
(:mod:`radiarch.services.pareto`) asks for weighted-sum plans, each solved with the request's solver, under the hard
constraints when there are any, warm-started from the nearest plan. What navigation needs is stored
(``docs/reports/mco-research-and-design.md``, D4)::

    mco/
      _index.json                      cache_key → mco_id
      {mco_id}/
        meta.json                      MCOResult
        weights.npy                    plans x elements (float32)
        navigation_index.npy           flat indices of the navigation voxels on the dose grid
        navigation_dose.npy            plans x navigation voxels (float32, Gy)
        navigation_masks.npz           structure → boolean over the navigation voxels
        navigation_dose_scenarios.npy  robust (R11.6): scenarios x plans x navigation voxels, nominal first

A navigated plan's dose on those voxels is a blend of the rows of ``navigation_dose.npy``; its full dose is the
dose matrix times the same blend of the rows of ``weights.npy``, computed only when a plan is made from it.

A robust set (R11.6, D8; :mod:`radiarch.services.robust_mco`) is solved on the stacked scenario doses of the navigation
voxels: each plan minimizes the worst scenario of its weighted sum, and reports each trade-off's worst case.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.dose import dose_units_for
from ..models.mco import ErrorPoint, MCORunRequest, MCOResult, MCOStage, ParetoPlan
from ..models.optimization import OptimizationRunRequest
from .hard_constraints import InfeasibleConstraintsError, infeasible_message, solve_with_hard_constraints
from .optimization import OptimizationService
from .optimization_solvers import get_solver
from .pareto import MIN_RANGE, Solved, normalize, sandwich
from .robust_mco import StackedOps, WorstCase, scenario_terms, scenario_wise

MCOProgressCallback = Callable[[MCOStage, float, str], None]


class MCOStore:
    """``{artifact_dir}/mco/{mco_id}/`` with a cache index, like the other stores."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _index(self) -> Path:
        return self.base_dir / "_index.json"

    def _load_index(self) -> Dict[str, str]:
        try:
            return json.loads(self._index.read_text(encoding="utf-8")) if self._index.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def dir(self, mco_id: str) -> Path:
        return self.base_dir / mco_id

    def get_by_id(self, mco_id: str) -> Optional[MCOResult]:
        meta = self.dir(mco_id) / "meta.json"
        if not meta.is_file():
            return None
        try:
            return MCOResult.model_validate_json(meta.read_text(encoding="utf-8"))
        except Exception:
            return None

    def lookup_by_cache_key(self, key: str) -> Optional[MCOResult]:
        mid = self._load_index().get(key)
        return self.get_by_id(mid) if mid else None

    def list_ids(self) -> List[str]:
        return sorted(d.name for d in self.base_dir.iterdir() if d.is_dir() and (d / "meta.json").is_file()) if self.base_dir.is_dir() else []

    def save_arrays(self, mco_id: str, weights: np.ndarray, index: np.ndarray, doses: np.ndarray, masks: Dict[str, np.ndarray],
                    scenario_doses: Optional[np.ndarray] = None) -> None:
        root = self.dir(mco_id)
        root.mkdir(parents=True, exist_ok=True)
        arrays = [("weights.npy", weights), ("navigation_index.npy", index), ("navigation_dose.npy", doses)]
        if scenario_doses is not None:
            arrays.append(("navigation_dose_scenarios.npy", scenario_doses))
        for name, arr in arrays:
            tmp = root / f".{name}.tmp.npy"
            np.save(tmp, arr)
            os.replace(tmp, root / name)
        tmp = root / ".navigation_masks.tmp.npz"
        np.savez_compressed(tmp, **masks)
        os.replace(tmp, root / "navigation_masks.npz")

    def save(self, result: MCOResult) -> None:
        root = self.dir(result.mco_id)
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.mco_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_i, self._index)

    def load_navigation(self, mco_id: str):
        """``(index, doses, masks)``: the navigation voxels, every plan's dose on them, the structures over them."""
        root = self.dir(mco_id)
        with np.load(root / "navigation_masks.npz") as z:
            masks = {k: z[k] for k in z.files}
        return np.load(root / "navigation_index.npy"), np.load(root / "navigation_dose.npy"), masks

    def load_weights(self, mco_id: str) -> np.ndarray:
        return np.load(self.dir(mco_id) / "weights.npy")

    def load_scenario_doses(self, mco_id: str) -> Optional[np.ndarray]:
        """A robust set's doses on the navigation voxels, scenarios x plans x voxels (memory-mapped), or None."""
        path = self.dir(mco_id) / "navigation_dose_scenarios.npy"
        return np.load(path, mmap_mode="r") if path.is_file() else None


def _noop(stage: MCOStage, fraction: float, message: str) -> None:
    pass


def projected_gradient(grad: np.ndarray, x: np.ndarray) -> float:
    """The largest component of the gradient projected on ``x >= 0`` (zero at a bound-constrained optimum)."""
    g = np.asarray(grad, dtype=np.float64)
    return float(np.max(np.abs(np.where(np.asarray(x) > 0.0, g, np.minimum(g, 0.0))))) if g.size else 0.0


@dataclass
class MCOOps:
    """What a solve on a Pareto set's problem needs. Nominal: doses on the full grid, the trade-offs as they are.
    Robust: doses stacked over the scenarios on the navigation voxels, each trade-off its worst case (:class:`WorstCase`),
    the hard constraints once per scenario."""

    objectives: list
    masks: list
    forward: Callable[[np.ndarray], np.ndarray]
    backward: Callable[[np.ndarray], np.ndarray]
    terms: list
    regs: Optional[Callable]
    index: np.ndarray                       # the navigation voxels (flat indices on the dose grid)
    structures: Dict[str, np.ndarray]       # structure → boolean over the navigation voxels
    scenarios: List[str]                    # robust: the scenario names, nominal first; else empty

    @property
    def robust(self) -> bool:
        return bool(self.scenarios)

    def navigation(self, dose: np.ndarray) -> np.ndarray:
        """A dose of :attr:`forward` on the navigation voxels, scenarios x voxels (one row when nominal)."""
        return np.asarray(dose) if self.robust else np.asarray(dose).ravel()[self.index][None, :]

    def values(self, dose: np.ndarray) -> np.ndarray:
        return np.array([o.value(dose, m) for o, m in zip(self.objectives, self.masks)])

    def nominal_values(self, dose: np.ndarray) -> np.ndarray:
        return np.array([o.nominal(dose, m) for o, m in zip(self.objectives, self.masks)]) if self.robust else self.values(dose)

    def weighted(self, raw: np.ndarray):
        """``(dose_terms, bound)`` for the weights ``raw``: the weighted sum (robust: its smoothed worst scenario) and,
        robust only, a lower bound on what any plan reaches in it (else None)."""
        if self.robust:
            return scenario_wise([o.objective for o in self.objectives], self.masks, raw)

        def dose_terms(d: np.ndarray):
            loss, grad = 0.0, np.zeros(d.shape)
            for wi, o, m in zip(raw, self.objectives, self.masks):
                v, g = o.value_and_grad(d, m)
                loss, grad = loss + wi * v, grad + wi * g
            return loss, grad
        return dose_terms, None


class MCOService:
    def __init__(self, base_dir: Optional[Path] = None, optimization_service: Optional[OptimizationService] = None) -> None:
        self.store = MCOStore(Path(base_dir) if base_dir else Path(get_settings().artifact_dir) / "mco")
        self.optimization = optimization_service or OptimizationService()

    def run(self, request: MCORunRequest, progress_callback: Optional[MCOProgressCallback] = None) -> MCOResult:
        on = progress_callback or _noop
        key = request.compute_cache_key()
        cached = self.store.lookup_by_cache_key(key)
        if cached is not None:
            on(MCOStage.done, 1.0, "cache hit")
            return cached
        t0 = time.time()
        n = len(request.tradeoffs)
        on(MCOStage.loading, 0.02, "loading the geometry, beam model and dose matrix")
        osvc = self.optimization
        prob = osvc._assemble_problem(self._base(request))
        ops = self.ops(prob, request)
        solver = get_solver(request.solver.method)
        tol = request.solver.convergence_tol or 1e-10
        max_iter = request.solver.max_iterations
        notes: List[str] = []
        if ops.robust:
            notes.append(f"robust over {len(ops.scenarios)} scenarios: each plan minimizes the worst scenario of its weighted sum; "
                         f"the values are each trade-off's worst case over the scenarios, and the error bound includes the "
                         f"gap between the two")

        start = np.asarray(prob.w0, dtype=np.float64)
        if ops.terms:
            on(MCOStage.feasibility, 0.05, f"feasibility of {len(request.hard_constraints)} hard constraint(s)"
                                           + (f" in {len(ops.scenarios)} scenarios" if ops.robust else ""))
            feas = solve_with_hard_constraints(ops.terms, ops.forward, ops.backward, start, solver, max_iter, tol)
            if not feas.met:
                raise InfeasibleConstraintsError(infeasible_message(feas.outcomes))
            start = feas.weights

        plans_x: List[np.ndarray] = []

        def solve(raw: np.ndarray, warm: Optional[int]) -> Solved:
            w0 = plans_x[warm] if warm is not None else start
            dose_terms, bound = ops.weighted(raw)
            if ops.terms:
                out = solve_with_hard_constraints(ops.terms, ops.forward, ops.backward, w0, solver, max_iter, tol, dose_terms=dose_terms,
                                                  weight_terms=ops.regs)
                x, ok, dose = out.weights, out.success and out.met, out.dose
            else:
                def cost_and_grad(w: np.ndarray):
                    d = ops.forward(w)
                    loss, gd = dose_terms(d)
                    gw = ops.backward(gd)
                    if ops.regs is not None:
                        rl, rg = ops.regs(np.asarray(w, dtype=np.float64))
                        loss, gw = loss + rl, gw + rg
                    return float(loss), gw
                x, conv = solver.run(cost_and_grad, w0, max_iter, tol)
                x = np.clip(np.asarray(x, dtype=np.float64).ravel(), 0.0, None)
                # L-BFGS-B reports a failed line search at an optimum on the bound (an organ's anchor at zero
                # fluence): a vanishing projected gradient counts as converged too
                cost, g = cost_and_grad(x)
                ok, dose = conv.success or projected_gradient(g, x) <= 1e-6 * (1.0 + abs(cost)), ops.forward(x)
            plans_x.append(x)
            return Solved(x=x, values=ops.values(dose), ok=ok, bound=None if bound is None else bound(dose))

        budget = request.budget

        def on_plan(plan, count: int, err: float) -> None:
            stage = MCOStage.anchors if count <= n else MCOStage.sandwich
            bound = "" if np.isnan(err) else f", error bound {err:.3f}"
            on(stage, 0.08 + 0.82 * min(1.0, count / budget), f"{plan.kind} plan {count} of up to {budget}{bound}")

        res = sandwich(solve, n, budget, tol=request.error_tolerance, eps=request.anchor_epsilon, on_plan=on_plan)
        for i in res.flat:
            o = request.tradeoffs[i]
            notes.append(f"{o.type}({o.structure_name}) is the same in every anchor plan "
                         f"({res.ideal[i]:.3g} Gy): it trades nothing on these beams")
        notes += [f"plan {k} did not converge" for k, p in enumerate(res.plans) if not p.solved.ok]
        empty = [k for k, p in enumerate(res.plans) if float(np.sum(p.solved.x)) <= 0.0]
        if empty:
            notes.append(f"plan(s) {', '.join(map(str, empty))} deliver no dose: without a hard constraint on target coverage "
                         f"(e.g. PTV Dmin >=) an organ's anchor, and even the balance plan, can switch every beamlet off")

        gap = None
        if ops.robust:
            # how far below each plan's weighted worst cases its scenario-wise bound lies (normalized): the part of the
            # error bound that comes from protecting scenarios rather than each trade-off's own worst case
            span = np.where(res.nadir - res.ideal > MIN_RANGE, res.nadir - res.ideal, 1.0)
            gap = max(float((p.raw_weights @ p.solved.values - p.solved.bound) / (p.raw_weights @ span)) for p in res.plans)

        on(MCOStage.persisting, 0.92, "storing the plans and their doses on the navigation voxels")
        nav = np.stack([ops.navigation(ops.forward(p.solved.x)) for p in res.plans]).astype(np.float32)     # plans x scenarios x voxels
        nominal = [ops.nominal_values(ops.forward(p.solved.x)) for p in res.plans] if ops.robust else None
        weights = np.stack([p.solved.x for p in res.plans]).astype(np.float32)
        mco_id = str(uuid.uuid4())
        self.store.save_arrays(mco_id, weights, ops.index, np.ascontiguousarray(nav[:, 0]), ops.structures,
                               np.ascontiguousarray(nav.transpose(1, 0, 2)) if ops.robust else None)
        (self.store.dir(mco_id) / "request.json").write_text(request.model_dump_json(indent=1), encoding="utf-8")
        names, index = list(ops.structures), ops.index

        norm = res.normalized()
        root = self.store.dir(mco_id)
        result = MCOResult(
            mco_id=mco_id, cache_key=key, geometry_id=request.geometry_id, beam_model_id=request.beam_model_id,
            engine_name=prob.engine.name, engine_version=prob.engine.version, rbe_factor=prob.rbe, dose_units=dose_units_for(prob.rbe),
            tradeoffs=request.tradeoffs, hard_constraints=request.hard_constraints,
            ideal_gy=[round(float(v), 6) for v in res.ideal], nadir_gy=[round(float(v), 6) for v in res.nadir],
            plans=[ParetoPlan(index=k, kind=p.kind, weights=[float(w) for w in p.raw_weights],
                              values_gy=[round(float(v), 6) for v in p.solved.values], normalized=[round(float(v), 6) for v in norm[k]],
                              nominal_gy=None if nominal is None else [round(float(v), 6) for v in nominal[k]],
                              converged=p.solved.ok) for k, p in enumerate(res.plans)],
            error_history=[ErrorPoint(plans=c, error=round(e, 6)) for c, e in res.history], error_bound=round(res.error, 6),
            converged=res.error <= request.error_tolerance, stop_reason=res.stop_reason, notes=notes,
            navigation_structures=names, navigation_voxels=int(index.size),
            voxel_cc=float(np.prod(prob.geometry.spacing_mm)) / 1000.0,
            weights_uri=str(root / "weights.npy"), navigation_dose_uri=str(root / "navigation_dose.npy"),
            scenarios=list(ops.scenarios), robust_gap=None if gap is None else round(gap, 6), modality=prob.beam_model.result.modality.value,
            compute_time_s=round(time.time() - t0, 2), created_at=datetime.now(timezone.utc))
        self.store.save(result)
        on(MCOStage.done, 1.0, f"mco {mco_id}: {len(res.plans)} plans, error bound {res.error:.3f}")
        logger.info("MCO {}: {} trade-offs, {} plans, error bound {:.4f} ({}), {:.0f} s", mco_id, n, len(res.plans), res.error,
                    res.stop_reason, result.compute_time_s)
        return result


    # -----------------------------------------------------------------
    # Projection onto the Pareto set (R11.4, D6)
    # -----------------------------------------------------------------

    def problem(self, mco_id: str):
        """``(result, request, problem)``: the stored set, its request, and its optimization problem assembled again
        (the dose matrix comes from the influence cache)."""
        result = self.store.get_by_id(mco_id)
        req_path = self.store.dir(mco_id) / "request.json"
        if result is None or not req_path.is_file():
            raise ValueError(f"Pareto set {mco_id} has no stored request")
        request = MCORunRequest.model_validate_json(req_path.read_text(encoding="utf-8"))
        return result, request, self.optimization._assemble_problem(self._base(request))

    @staticmethod
    def _base(request: MCORunRequest) -> OptimizationRunRequest:
        """The optimization request whose problem a Pareto set is computed on (its hard constraints are the set's own
        terms, :meth:`ops`)."""
        return OptimizationRunRequest(
            plan_id=request.plan_id, geometry_id=request.geometry_id, beam_model_id=request.beam_model_id, dose_engine=request.dose_engine,
            objectives=[o.model_copy(update={"weight": 1.0}) for o in request.tradeoffs], solver=request.solver, rbe=request.rbe,
            robustness=request.robustness)

    def ops(self, prob, request: MCORunRequest) -> MCOOps:
        """The solve operators of a set's problem (:class:`MCOOps`); the navigation voxels are every structure the
        trade-offs, constraints and requested goals name."""
        osvc = self.optimization
        names = list(dict.fromkeys([o.structure_name for o in request.tradeoffs] + [c.structure_name for c in request.hard_constraints]
                                   + list(request.navigation_structures)))
        struct = {nm: osvc._resolve_mask(prob.geometry, nm, prob.grid_shape).ravel() > 0 for nm in names}
        union = np.zeros(int(np.prod(prob.grid_shape)), dtype=bool)
        for m in struct.values():
            union |= m
        index = np.flatnonzero(union).astype(np.int64)
        structures = {nm: m[index] for nm, m in struct.items()}
        forward, backward, weight_terms = osvc.nominal_ops(prob)
        regs = weight_terms if prob.regularizers else None
        if not request.robustness.enabled:
            return MCOOps([o for o, _ in prob.obj_terms], [m for _, m in prob.obj_terms], forward, backward,
                          osvc.hard_terms(prob, request.hard_constraints), regs, index, structures, [])
        stacked = StackedOps([prob.scenario_dij[sc.hash()][1][index] for sc in prob.scenarios])
        scenarios = [sc.name for sc in prob.scenarios]
        cmasks = [structures[c.structure_name].astype(np.float64) for c in request.hard_constraints]
        return MCOOps([WorstCase(o) for o, _ in prob.obj_terms], [np.asarray(m).ravel()[index].astype(np.float64) for _, m in prob.obj_terms],
                      stacked.forward, stacked.backward, scenario_terms(request.hard_constraints, cmasks, scenarios), regs, index,
                      structures, scenarios)

    def project(self, mco_id: str, blend) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """A navigated blend moved onto the Pareto set: the plan that lowers the trade-offs' normalized sum as far as
        it can with none of them above its value in the blend, under the run's hard constraints (a variant of Bokrantz
        & Miettinen's projection, Med Phys 42:5862, 2015, which raises every objective evenly). The blend is the start
        and meets every cap, so the projected plan is at least as good in every trade-off (robust: in every trade-off's
        worst case). Returns the plan's element weights, its nominal dose on the navigation voxels and notes."""
        result, request, prob = self.problem(mco_id)
        ops = self.ops(prob, request)
        x, dose, notes = self.project_ops(result, request, ops, blend)
        return x, ops.navigation(dose)[0], notes

    def project_ops(self, result: MCOResult, request: MCORunRequest, ops: MCOOps, blend) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """:meth:`project` on assembled operators; the dose is in :attr:`MCOOps.forward`'s form."""
        lam = np.asarray(blend, dtype=np.float64)
        x0 = lam @ self.store.load_weights(result.mco_id).astype(np.float64)
        span = np.maximum(np.asarray(result.nadir_gy) - np.asarray(result.ideal_gy), 1e-6)
        return project_blend(ops.objectives, ops.masks, ops.forward, ops.backward, ops.terms, x0, span, get_solver(request.solver.method),
                             request.solver.max_iterations, request.solver.convergence_tol or 1e-10,
                             [f"{o.type}({o.structure_name})" for o in request.tradeoffs])


def project_blend(objectives, masks, forward, backward, constraint_terms, x0: np.ndarray, span: np.ndarray, solver, max_iter: int,
                  tol: float, names: List[str]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """``min sum_i f_i / span_i`` subject to ``f_i <= f_i(x0)`` and the hard constraints, from ``x0`` (see
    :meth:`MCOService.project`). Returns the weights, their full dose and notes; ``x0`` itself when the solve does
    not hold every cap."""
    from .hard_constraints import ObjectiveCap

    d0 = forward(x0)
    caps = [ObjectiveCap(o, m, o.value(d0, m), name) for o, m, name in zip(objectives, masks, names)]
    scale = 1.0 / np.asarray(span, dtype=np.float64)

    def dose_terms(d: np.ndarray):
        loss, grad = 0.0, np.zeros(d.shape)
        for s, o, m in zip(scale, objectives, masks):
            v, g = o.value_and_grad(d, m)
            loss, grad = loss + s * v, grad + s * g
        return loss, grad

    out = solve_with_hard_constraints(list(constraint_terms) + caps, forward, backward, x0, solver, max_iter, tol, dose_terms=dose_terms)
    if not out.met:
        return np.asarray(x0, dtype=np.float64), d0, ["the projection did not hold every cap; the navigated plan is kept"]
    return out.weights, out.dose, []


__all__ = ["MCOService", "MCOStore", "MCOOps", "MCOProgressCallback", "normalize", "project_blend"]
