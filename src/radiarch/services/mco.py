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

A navigated plan's dose on those voxels is a blend of the rows of ``navigation_dose.npy``; its full dose is the
dose matrix times the same blend of the rows of ``weights.npy``, computed only when a plan is made from it.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.dose import dose_units_for
from ..models.mco import ErrorPoint, MCORunRequest, MCOResult, MCOStage, ParetoPlan
from ..models.optimization import OptimizationRunRequest
from .hard_constraints import InfeasibleConstraintsError, infeasible_message, solve_with_hard_constraints
from .optimization import OptimizationService
from .optimization_solvers import get_solver
from .pareto import Solved, normalize, sandwich

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

    def save_arrays(self, mco_id: str, weights: np.ndarray, index: np.ndarray, doses: np.ndarray, masks: Dict[str, np.ndarray]) -> None:
        root = self.dir(mco_id)
        root.mkdir(parents=True, exist_ok=True)
        for name, arr in (("weights.npy", weights), ("navigation_index.npy", index), ("navigation_dose.npy", doses)):
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


def _noop(stage: MCOStage, fraction: float, message: str) -> None:
    pass


def projected_gradient(grad: np.ndarray, x: np.ndarray) -> float:
    """The largest component of the gradient projected on ``x >= 0`` (zero at a bound-constrained optimum)."""
    g = np.asarray(grad, dtype=np.float64)
    return float(np.max(np.abs(np.where(np.asarray(x) > 0.0, g, np.minimum(g, 0.0))))) if g.size else 0.0


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
        base = OptimizationRunRequest(
            plan_id=request.plan_id, geometry_id=request.geometry_id, beam_model_id=request.beam_model_id,
            dose_engine=request.dose_engine, objectives=[o.model_copy(update={"weight": 1.0}) for o in request.tradeoffs],
            hard_constraints=request.hard_constraints, solver=request.solver, rbe=request.rbe)
        osvc = self.optimization
        prob = osvc._assemble_problem(base)
        forward, backward, weight_terms = osvc.nominal_ops(prob)
        terms = osvc.hard_terms(prob, request.hard_constraints)
        objectives = [obj for obj, _ in prob.obj_terms]
        masks = [m for _, m in prob.obj_terms]
        solver = get_solver(request.solver.method)
        tol = request.solver.convergence_tol or 1e-10
        max_iter = request.solver.max_iterations
        regs = weight_terms if prob.regularizers else None
        notes: List[str] = []

        start = np.asarray(prob.w0, dtype=np.float64)
        if terms:
            on(MCOStage.feasibility, 0.05, f"feasibility of {len(terms)} hard constraint(s)")
            feas = solve_with_hard_constraints(terms, forward, backward, start, solver, max_iter, tol)
            if not feas.met:
                raise InfeasibleConstraintsError(infeasible_message(feas.outcomes))
            start = feas.weights

        def values(dose: np.ndarray) -> np.ndarray:
            return np.array([o.value(dose, m) for o, m in zip(objectives, masks)])

        plans_x: List[np.ndarray] = []

        def solve(raw: np.ndarray, warm: Optional[int]) -> Solved:
            w0 = plans_x[warm] if warm is not None else start

            def dose_terms(d: np.ndarray):
                loss, grad = 0.0, np.zeros(d.shape)
                for wi, o, m in zip(raw, objectives, masks):
                    v, g = o.value_and_grad(d, m)
                    loss, grad = loss + wi * v, grad + wi * g
                return loss, grad

            if terms:
                out = solve_with_hard_constraints(terms, forward, backward, w0, solver, max_iter, tol, dose_terms=dose_terms, weight_terms=regs)
                x, ok, dose = out.weights, out.success and out.met, out.dose
            else:
                def cost_and_grad(w: np.ndarray):
                    d = forward(w)
                    loss, gd = dose_terms(d)
                    gw = backward(gd)
                    if regs is not None:
                        rl, rg = regs(np.asarray(w, dtype=np.float64))
                        loss, gw = loss + rl, gw + rg
                    return float(loss), gw
                x, conv = solver.run(cost_and_grad, w0, max_iter, tol)
                x = np.clip(np.asarray(x, dtype=np.float64).ravel(), 0.0, None)
                # L-BFGS-B reports a failed line search at an optimum on the bound (an organ's anchor at zero
                # fluence): a vanishing projected gradient counts as converged too
                cost, g = cost_and_grad(x)
                ok, dose = conv.success or projected_gradient(g, x) <= 1e-6 * (1.0 + abs(cost)), forward(x)
            plans_x.append(x)
            return Solved(x=x, values=values(dose), ok=ok)

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

        # the navigation voxels: every structure the trade-offs, constraints and requested goals name
        on(MCOStage.persisting, 0.92, "storing the plans and their doses on the navigation voxels")
        names = list(dict.fromkeys([o.structure_name for o in request.tradeoffs] + [c.structure_name for c in request.hard_constraints]
                                   + list(request.navigation_structures)))
        struct = {nm: osvc._resolve_mask(prob.geometry, nm, prob.grid_shape).ravel() > 0 for nm in names}
        union = np.zeros(int(np.prod(prob.grid_shape)), dtype=bool)
        for m in struct.values():
            union |= m
        index = np.flatnonzero(union).astype(np.int64)
        doses = np.stack([forward(p.solved.x).ravel()[index] for p in res.plans]).astype(np.float32)
        weights = np.stack([p.solved.x for p in res.plans]).astype(np.float32)
        mco_id = str(uuid.uuid4())
        self.store.save_arrays(mco_id, weights, index, doses, {nm: m[index] for nm, m in struct.items()})

        norm = res.normalized()
        root = self.store.dir(mco_id)
        result = MCOResult(
            mco_id=mco_id, cache_key=key, geometry_id=request.geometry_id, beam_model_id=request.beam_model_id,
            engine_name=prob.engine.name, engine_version=prob.engine.version, rbe_factor=prob.rbe, dose_units=dose_units_for(prob.rbe),
            tradeoffs=request.tradeoffs, hard_constraints=request.hard_constraints,
            ideal_gy=[round(float(v), 6) for v in res.ideal], nadir_gy=[round(float(v), 6) for v in res.nadir],
            plans=[ParetoPlan(index=k, kind=p.kind, weights=[float(w) for w in p.raw_weights],
                              values_gy=[round(float(v), 6) for v in p.solved.values], normalized=[round(float(v), 6) for v in norm[k]],
                              converged=p.solved.ok) for k, p in enumerate(res.plans)],
            error_history=[ErrorPoint(plans=c, error=round(e, 6)) for c, e in res.history], error_bound=round(res.error, 6),
            converged=res.error <= request.error_tolerance, stop_reason=res.stop_reason, notes=notes,
            navigation_structures=names, navigation_voxels=int(index.size),
            voxel_cc=float(np.prod(prob.geometry.spacing_mm)) / 1000.0,
            weights_uri=str(root / "weights.npy"), navigation_dose_uri=str(root / "navigation_dose.npy"),
            compute_time_s=round(time.time() - t0, 2), created_at=datetime.now(timezone.utc))
        self.store.save(result)
        on(MCOStage.done, 1.0, f"mco {mco_id}: {len(res.plans)} plans, error bound {res.error:.3f}")
        logger.info("MCO {}: {} trade-offs, {} plans, error bound {:.4f} ({}), {:.0f} s", mco_id, n, len(res.plans), res.error,
                    res.stop_reason, result.compute_time_s)
        return result


__all__ = ["MCOService", "MCOStore", "MCOProgressCallback", "normalize"]
