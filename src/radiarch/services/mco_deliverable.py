"""The deliverable plan of a navigation state (roadmap R11.5, D7).

A navigated plan is a blend of fluence (or spot) maps. Fluence is not what a linac delivers: the plan is projected onto
the Pareto set (R11.4), its dose becomes a reference, and a deliverable plan is made to mimic it, as RayStation does
(RaySearch MCO white paper, 2020): static fields are sequenced into apertures (R4) and arcs swept (R8), each with
its segment or control-point metersets re-optimized against one-sided ``ReferenceDose`` objectives on every
navigation structure (an organ penalized above the reference; a target above it in its hotter half, below it in its
colder half). Proton spot weights are a plan as they stand: radiarch's proton machine model has no minimum spot
meterset, so the projected spots are the deliverable plan.

The step most reported to fail in commercial MCO is this one (Kyroudi et al. 2016; Wong et al. 2024), so every
deliverable plan carries a deviation table: each trade-off and goal, navigated against deliverable, flagged when the
deliverable plan is worse by more than a tolerance.

A robust set (R11.6) is projected with each trade-off's worst case capped, and its deviation table compares worst
cases. Only proton sets are made deliverable robustly: a sequenced photon plan would need its own scenario doses.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.beam_model import Modality
from ..models.dose import dose_units_for
from ..models.mco import DeliverableRequest, DeliverableStage, DeviationRow, MCODeliverable
from ..models.optimization import ConvergenceInfo, ObjectiveSpec, OptimizationResult, HardConstraint
from .array_backend import device_cache_key, to_host
from .clinical_goals import parse_metric
from .mco import MCOService
from .navigation import NavigationService
from .objectives import _geud

DeliverableProgressCallback = Callable[[DeliverableStage, float, str], None]
TARGET_TYPES = ("EUDMin", "RMSUnder", "UniformRMS")
MCO_PLAN_PREFIX = "mco:"          # the navigated plan's optimization record: mco:{mco_id}:{key} (lineage reads it)


class DeliverableRefused(ValueError):
    """A deliverable plan this Pareto set cannot have (a robust photon set)."""


class DeliverableStore:
    """``{artifact_dir}/mco_deliverables/{deliverable_id}/meta.json`` with a cache index."""

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

    def get_by_id(self, deliverable_id: str) -> Optional[MCODeliverable]:
        meta = self.base_dir / deliverable_id / "meta.json"
        if not meta.is_file():
            return None
        try:
            return MCODeliverable.model_validate_json(meta.read_text(encoding="utf-8"))
        except Exception:
            return None

    def lookup_by_cache_key(self, key: str) -> Optional[MCODeliverable]:
        did = self._load_index().get(key)
        return self.get_by_id(did) if did else None

    def list_ids(self) -> List[str]:
        return sorted(d.name for d in self.base_dir.iterdir() if d.is_dir() and (d / "meta.json").is_file()) if self.base_dir.is_dir() else []

    def find(self, dose_id: Optional[str] = None, beam_model_id: Optional[str] = None) -> List[MCODeliverable]:
        """The plans with this dose and beam model (either may be left out), newest first."""
        plans = [p for p in (self.get_by_id(i) for i in self.list_ids()) if p is not None
                 and (dose_id is None or p.dose_id == dose_id) and (beam_model_id is None or p.beam_model_id == beam_model_id)]
        epoch = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(plans, key=lambda p: p.created_at or epoch, reverse=True)

    def save(self, result: MCODeliverable) -> None:
        root = self.base_dir / result.deliverable_id
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.deliverable_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_i, self._index)


def planning_goals(goal_set) -> List[dict]:
    """A clinical goal set as the planner's goal rows (structure, metric, op, gy), the form ``objectives_for`` and
    ``goal_met`` take: ``D95%[Gy]`` → ``D95``, ``Dmax[Gy]`` → ``Dmax``, ``Dmean[Gy]`` → ``Dmean``. Goals in other
    metrics (``V20Gy[%]``, ``D0.03cc[Gy]``) do not drive the metersets; the deviation table still reports them."""
    from .clinical_goals import parse_metric

    rows: List[dict] = []
    for g in (goal_set.goals if goal_set is not None else []):
        try:
            m = parse_metric(g.metric)
        except ValueError:
            continue
        if m.kind != "D" or m.unit != "Gy":
            continue
        if m.stat in ("max", "mean"):
            metric = "Dmax" if m.stat == "max" else "Dmean"
        elif m.arg_unit == "%" and m.arg is not None:
            metric = f"D{m.arg:g}"
        else:
            continue
        rows.append({"structure": g.structure, "metric": metric, "op": g.op, "gy": float(g.value)})
    return rows


def capped_fluence(plan, weights: np.ndarray, peak_ratio: Optional[float]) -> Tuple[np.ndarray, List[str]]:
    """The beamlet weights with each beam's peaks capped at ``peak_ratio`` times its median nonzero weight. A map
    sequenced by equal fluence steps keeps a cell only when it holds at least half a step, so a few high beamlets
    (hard constraints push them up where a voxel is cold) close most of a beam's field; capping them keeps the field
    open, and the meterset optimization recovers what the peaks did where it can. Returns the weights and a note
    per capped beam."""
    w = np.asarray(weights, dtype=np.float64).copy()
    notes: List[str] = []
    if peak_ratio is None:
        return w, notes
    offset = 0
    for beam in plan.beams:
        n = int(beam.beamlets().shape[0])
        seg = w[offset:offset + n]
        offset += n
        nonzero = seg[seg > 0]
        if nonzero.size == 0:
            continue
        cap = float(peak_ratio) * float(np.median(nonzero))
        over = seg > cap
        if over.any():
            lost = float(seg[over].sum() - cap * over.sum()) / float(seg.sum())
            notes.append(f"beam {beam.beam_id}: {int(over.sum())} of {n} beamlets capped at {peak_ratio:g} x the median "
                         f"({cap:.3g}), {100 * lost:.1f} % of its fluence")
            seg[over] = cap
    return w, notes


def _noop(stage: DeliverableStage, fraction: float, message: str) -> None:
    pass


def target_structures(result) -> List[str]:
    """The structures a target-type trade-off (cold spots, homogeneity) or a lower-bound constraint names."""
    names = [o.structure_name for o in result.tradeoffs if o.type in TARGET_TYPES]
    names += [c.structure_name for c in result.hard_constraints if c.metric == "Dmin" or (c.metric == "gEUD" and c.op == ">=")]
    return list(dict.fromkeys(names))


class DeliverableService:
    def __init__(self, base_dir: Optional[Path] = None, mco_service: Optional[MCOService] = None) -> None:
        self.store = DeliverableStore(Path(base_dir) if base_dir else Path(get_settings().artifact_dir) / "mco_deliverables")
        self.mco = mco_service or MCOService()
        self.navigation = NavigationService(self.mco.store)

    def cache_key(self, mco_id: str, request: DeliverableRequest) -> str:
        result = self.mco.store.get_by_id(mco_id)
        if result is None:
            raise KeyError(mco_id)
        if result.scenarios and result.modality != Modality.proton_pbs.value:
            raise DeliverableRefused("a robust photon Pareto set has no deliverable plan yet: the sequenced plan would need "
                                     "its own scenario doses; robust deliverables are made for proton sets")
        state = self.navigation.get_state(mco_id, request.state_id)
        if state is None:
            raise ValueError(f"no state {request.state_id!r} in Pareto set {mco_id}")
        return device_cache_key(request.compute_cache_key(result.cache_key, state.blend))

    def run(self, mco_id: str, request: DeliverableRequest, progress_callback: Optional[DeliverableProgressCallback] = None) -> MCODeliverable:
        from .apertures import ApertureService
        from .autoplan import AutoplanService, normalise_to_goal, read_volume
        from .dose import DoseService
        from .vmat import VMATService
        from ..models.apertures import SequenceRequest
        from ..models.vmat import ArcRequest

        on = progress_callback or _noop
        key = self.cache_key(mco_id, request)
        cached = self.store.lookup_by_cache_key(key)
        if cached is not None:
            on(DeliverableStage.done, 1.0, "cache hit")
            return cached
        t0 = time.time()
        state = self.navigation.get_state(mco_id, request.state_id)
        second = self.mco.store.get_by_id(mco_id)
        if second is not None and second.source_deliverable_id:
            # a second set (R11.11): its blend is metersets on a deliverable plan's apertures, made into that plan
            from .mco_apertures import deliver_on_apertures

            return deliver_on_apertures(self, mco_id, second, request, state, key, on, t0)
        result, mreq, prob = self.mco.problem(mco_id)
        osvc = self.mco.optimization
        ops = self.mco.ops(prob, mreq)
        forward, _, _ = osvc.nominal_ops(prob)
        lam = np.asarray(state.blend, dtype=np.float64)
        x = lam @ self.mco.store.load_weights(mco_id).astype(np.float64)
        notes: List[str] = []

        # 1. projection onto the Pareto set
        projected = False
        if request.project:
            on(DeliverableStage.projecting, 0.05, "projecting the navigated plan onto the Pareto set")
            x, _, pnotes = self.mco.project_ops(result, mreq, ops, lam)
            notes += pnotes
            projected = not pnotes
        dose_full = to_host(forward(x))
        projected_stack = ops.navigation(ops.forward(x))

        # 2. the navigated plan as an optimization: its dose is the reference the deliverable plan mimics; its weights,
        #    with each beam's peaks capped, are the fluence the sequencing starts from
        modality = prob.beam_model.result.modality
        x_seq, cap_notes = x, []
        if modality is Modality.photon_imrt:
            x_seq, cap_notes = capped_fluence(prob.beam_model.plan, x, request.peak_ratio)
            notes += cap_notes
        opt_key = f"{MCO_PLAN_PREFIX}{mco_id}:{key}"
        opt = osvc.store.lookup_by_cache_key(opt_key)
        if opt is None:
            opt_id = str(uuid.uuid4())
            paths = osvc.store.prepare(opt_id)
            values = [float(o.value(dose_full, m)) for o, m in prob.obj_terms]
            opt = OptimizationResult(
                optimization_id=opt_id, cache_key=opt_key, weights_ref_uri=str(paths.weights), dose_ref_uri=str(paths.dose),
                convergence=ConvergenceInfo(success=True, iterations=0, final_cost=float(sum(values)), objective_values=values,
                                            notes=[f"the {'projected' if projected else 'navigated'} plan of state {state.state_id} "
                                                   f"of Pareto set {mco_id}"]),
                rbe_factor=prob.rbe, dose_units=dose_units_for(prob.rbe), compute_time_s=0.0, geometry_id=result.geometry_id,
                beam_model_id=result.beam_model_id, engine_name=prob.engine.name, engine_version=prob.engine.version,
                engine_digest=getattr(prob, "engine_digest", None))
            osvc.store.save(opt_id=opt_id, cache_key=opt_key, weights=x_seq.astype(np.float32), dose=dose_full,
                            spacing_mm=prob.geometry.spacing_mm, result=opt)

        # 3. the deliverable plan: apertures or arcs from the navigated fluence, their metersets optimized against the
        #    navigated dose (the mimic), each target's hot spot and the goals; goal-driven rounds as the reweighting
        #    planner's, each judged after normalisation (the record of 2026-10-31 found a mimic alone under-covering the
        #    target, the normalisation then inflating the hot spots)
        targets = request.targets or target_structures(result)
        mimic = [ObjectiveSpec(type="ReferenceDose", structure_name=nm, dose_gy=0.0,
                               weight=request.target_priority if nm in targets else 1.0, reference_dose_uri=opt.dose_ref_uri,
                               reference_role="target" if nm in targets else "organ") for nm in result.navigation_structures]
        sequence_id = vmat_id = dose_id = None
        rounds_log: List[Dict[str, Any]] = []
        if modality is Modality.photon_imrt:
            from .autoplan import goal_met, objectives_for
            from .geometry import GeometryService
            from .geometry_bundle import load_geometry_arrays

            arrays = load_geometry_arrays(GeometryService().store.get_by_id(result.geometry_id))
            d_nav = np.asarray(dose_full, dtype=np.float64)
            d_nav = d_nav.reshape(prob.grid_shape) if d_nav.size == int(np.prod(prob.grid_shape)) else d_nav
            hot: List[ObjectiveSpec] = []
            for nm in targets:
                mask = osvc._resolve_mask(prob.geometry, nm, prob.grid_shape) > 0
                if mask.shape == d_nav.shape and mask.any():
                    limit = request.hot_spot_gy or float(d_nav[mask].max()) + request.tolerance_gy
                    hot.append(ObjectiveSpec(type="DMax", structure_name=nm, dose_gy=limit, weight=30.0 * request.target_priority))
            goal_rows = [g for g in planning_goals(request.goals) if g["structure"] in arrays.structure_index]
            rx = request.prescription_gy or (request.normalise.gy if request.normalise is not None else None)
            main_target = next((nm for nm in ([request.normalise.structure] if request.normalise is not None else []) + list(targets)
                                if nm in arrays.structure_index), None)
            if goal_rows and (rx is None or main_target is None):
                notes.append("the goals did not drive the metersets: they need prescription_gy (or normalise.gy) and a target")
                goal_rows = []
            masks = {g["structure"]: arrays.mask_zyx(arrays.structure_index[g["structure"]]) for g in goal_rows}
            coverage_targets = {g["structure"] for g in goal_rows if g["op"].startswith(">")}
            hard: List[HardConstraint] = []
            cover_mask = limit_gy = None
            if request.hard_coverage and request.normalise is not None:
                # the record's lung plans: apertures that under-cover, a normalisation that scales the hot spots up with the
                # coverage (1.27 to 1.37). Coverage and the hot spot as limits of the meterset solve itself (R11.9, option A)
                cover_target, rx_max = request.normalise.structure, (rx or request.normalise.gy)
                limit_gy = round(request.max_dose_factor * rx_max, 3)          # the target's maximum once normalised
                cover_mask = osvc._resolve_mask(prob.geometry, cover_target, prob.grid_shape) > 0
                hard = [HardConstraint(structure_name=cover_target, metric="gEUD", op=">=", value_gy=float(request.normalise.gy), eud_a=-10.0,
                                       tolerance_gy=0.5),
                        HardConstraint(structure_name=cover_target, metric="Dmax", op="<=", value_gy=limit_gy, tolerance_gy=0.5)]
            scale: Dict[int, float] = {}
            level: Dict[int, float] = {}
            best = None
            for r in range(max(1, int(request.rounds))):
                objectives = mimic + hot + (objectives_for(arrays, main_target, rx, goal_rows, scale, level) if goal_rows else [])
                if request.arcs:
                    on(DeliverableStage.mimicking, 0.35 + 0.4 * r / request.rounds,
                       f"round {r + 1}: arcs from the navigated sector fluence, metersets mimicking its dose")
                    vm = VMATService().arcs(opt.optimization_id, ArcRequest(
                        objectives=objectives, arcs=request.arcs, fractions=request.fractions, machine_model_id=request.machine_model_id,
                        dose_engine=mreq.dose_engine, max_iterations=request.max_iterations, hard_constraints=hard))
                    technique, vmat_id, beam_model_id, dose_id, deliverable = "vmat", vm.vmat_id, vm.beam_model_id, vm.dose_id, vm.deliverable
                else:
                    on(DeliverableStage.mimicking, 0.35 + 0.4 * r / request.rounds,
                       f"round {r + 1}: apertures from the navigated fluence, metersets mimicking its dose")
                    levels = max(int(request.levels), int(np.ceil(2 * request.peak_ratio)) if cap_notes else 0)   # a peaked map: finer steps
                    seq = ApertureService().sequence(opt.optimization_id, SequenceRequest(
                        objectives=objectives, levels=levels, machine_model_id=request.machine_model_id,
                        max_iterations=request.max_iterations, hard_constraints=hard))
                    technique, sequence_id, beam_model_id, dose_id, deliverable = "imrt", seq.sequence_id, seq.beam_model_id, seq.dose_id, seq.deliverable
                raw = read_volume(DoseService().dose_store.get_by_id(dose_id).dose_grid_uri)
                judged, k_r = raw, 1.0
                if request.normalise is not None:
                    mask = osvc._resolve_mask(prob.geometry, request.normalise.structure, prob.grid_shape) > 0
                    judged, k_r = normalise_to_goal(raw, raw[mask], request.normalise.metric, request.normalise.gy)
                failed = [i for i, g in enumerate(goal_rows) if not goal_met(judged[masks[g["structure"]]], g)]
                conv_r = (vm if request.arcs else seq).convergence
                entry: Dict[str, Any] = {"round": r + 1, "normalisation": round(float(k_r), 4),
                                         "failed": [f"{goal_rows[i]['structure']} {goal_rows[i]['metric']}" for i in failed]}
                in_band = hot_ok = True
                if hard and cover_mask is not None and cover_mask.shape == raw.shape and cover_mask.any():
                    # each round's limits and what the metersets reached against them, before and after normalisation
                    dmax = float(raw[cover_mask].max())
                    geud = float(_geud(np.asarray(raw, np.float64), cover_mask.astype(np.float64), float(cover_mask.sum()), -10.0)[0])
                    in_band = abs(float(k_r) - 1.0) <= request.normalise_band
                    hot_ok = float(k_r) * dmax <= limit_gy + hard[1].tolerance_gy
                    entry.update({"coverage_gy": hard[0].value_gy, "max_gy": hard[1].value_gy, "geud_gy": round(geud, 3), "dmax_gy": round(dmax, 3),
                                  "dmax_normalised_gy": round(float(k_r) * dmax, 3),
                                  "hard_constraints": dict(getattr(conv_r, "constraint_violations", {}) or {})})
                rounds_log.append(entry)
                # the plan kept: a round whose goals hold before one that fails, then one whose maximum holds once normalised,
                # then the normalisation nearest 1
                rank = (bool(failed), not hot_ok, abs(float(np.log(k_r))) if k_r > 0 else float("inf"))
                if best is None or rank < best[0]:
                    best = (rank, r, technique, sequence_id, vmat_id, beam_model_id, dose_id, deliverable)
                calibrated = in_band and hot_ok
                if not failed and calibrated:
                    break
                for i in failed:
                    scale[i] = scale.get(i, 1.0) * 3.0
                    if goal_rows[i]["structure"] not in coverage_targets:
                        level[i] = level.get(i, 1.0) * 0.95
                if not in_band:
                    # the gEUD is not the coverage goal (the 4 mm lung case met gEUD >= 60 Gy and still needed 1.11 for its
                    # D95): its level moves to where this round's normalisation puts the goal, below the maximum's limit
                    hard = [hard[0].model_copy(update={"value_gy": round(min(hard[0].value_gy * float(k_r), 0.95 * hard[1].value_gy), 3)})] + hard[1:]
                elif not hot_ok:
                    # the coverage level is calibrated, but the normalisation scales the maximum past its limit (the 4 mm lung
                    # arcs: 1.029 took it to 74.3 Gy): the next round's limit is the limit divided by the normalisation
                    hard = hard[:1] + [hard[1].model_copy(update={"value_gy": round(min(hard[1].value_gy, limit_gy / float(k_r)), 3)})]
            _, kept, technique, sequence_id, vmat_id, beam_model_id, dose_id, deliverable = best
            rounds_log[kept]["kept"] = True
        else:
            technique, beam_model_id, deliverable = "proton", result.beam_model_id, True
            notes.append("proton spots are delivered as weighted: the proton machine model has no minimum spot meterset, "
                         "so the projected spot weights are the plan (export it by its optimization_id)")
        delivered = read_volume(DoseService().dose_store.get_by_id(dose_id).dose_grid_uri) if dose_id else np.asarray(dose_full, np.float32)

        # 4. normalisation (photons, R10)
        k = 1.0
        if request.normalise is not None:
            if dose_id is None:
                notes.append("not normalised: a proton plan's spot weights are not rescaled here")
            else:
                on(DeliverableStage.normalising, 0.8, "normalising the metersets")
                mask = osvc._resolve_mask(prob.geometry, request.normalise.structure, prob.grid_shape) > 0
                _, k = normalise_to_goal(delivered, delivered[mask], request.normalise.metric, request.normalise.gy)
                bm_n, dose_n, delivered = AutoplanService._scaled(beam_model_id, dose_id, k, key)
                beam_model_id, dose_id = bm_n.beam_model_id, dose_n.dose_id

        # 5. navigated against deliverable
        on(DeliverableStage.comparing, 0.9, "comparing the deliverable plan with the navigated one")
        delivered_stack = projected_stack if dose_id is None else ops.navigation(np.asarray(delivered))      # protons: the projected plan
        rows = self._deviation(mco_id, request, lam, projected_stack if projected else None, delivered_stack)
        out = MCODeliverable(
            requested_by=request.requested_by, deliverable_id=str(uuid.uuid4()), cache_key=key, mco_id=mco_id, state_id=state.state_id,
            geometry_id=result.geometry_id,
            blend=state.blend, projected=projected, technique=technique, optimization_id=opt.optimization_id, sequence_id=sequence_id,
            vmat_id=vmat_id, beam_model_id=beam_model_id, dose_id=dose_id, normalisation=float(k), deliverable=bool(deliverable),
            deviation=rows, flagged=sum(r.flagged for r in rows), request=request, rounds=rounds_log, notes=notes,
            seconds=round(time.time() - t0, 1),
            created_at=datetime.now(timezone.utc))
        self.store.save(out)
        on(DeliverableStage.done, 1.0, f"deliverable {out.deliverable_id}: {out.flagged} flagged")
        logger.info("MCO {} state {}: {} plan {}, {} deviation(s) flagged, {:.0f} s", mco_id, state.state_id, technique, beam_model_id,
                    out.flagged, out.seconds)
        return out

    def _deviation(self, mco_id: str, request: DeliverableRequest, lam: np.ndarray, projected: Optional[np.ndarray],
                   delivered: np.ndarray) -> List[DeviationRow]:
        """The deviation table from stacked doses on the navigation voxels (scenarios x voxels; one row when nominal):
        robust, each trade-off's and goal's worst case is compared."""
        nav = self.navigation.navigator(mco_id)
        d_nav = nav.stack(lam)
        rows: List[DeviationRow] = []
        v_nav, v_del = nav.values(d_nav)[0], nav.values(delivered)[0]
        v_proj = nav.values(projected)[0] if projected is not None else [None] * len(v_nav)
        for name, a, p, b in zip(nav.names, v_nav, v_proj, v_del):
            worse = float(b - a)
            rows.append(DeviationRow(name=name, kind="trade-off", unit="Gy", navigated=round(float(a), 4),
                                     projected=None if p is None else round(float(p), 4), deliverable=round(float(b), 4),
                                     worse_by=round(worse, 4), flagged=worse > request.tolerance_gy))
        if request.goals is not None:
            def grade(stack):
                return nav.grade(request.goals, stack, request.prescription_gy, request.fractions)
            g_nav, g_del = grade(d_nav), grade(delivered)
            g_proj = grade(projected) if projected is not None else None
            for i, (ra, rb) in enumerate(zip(g_nav.results, g_del.results)):
                if ra.missing:
                    continue
                unit = parse_metric(ra.metric).unit
                a, b = ra.worst_case, rb.worst_case          # the achieved value when nominal
                worse = (b - a) if ra.op in ("<=", "<") else (a - b)
                tol = request.tolerance_gy if unit == "Gy" else request.tolerance_volume
                rows.append(DeviationRow(
                    name=f"{ra.structure} {ra.metric} {ra.op} {ra.value:g}", kind="goal", unit=unit, navigated=round(a, 4),
                    projected=None if g_proj is None else round(g_proj.results[i].worst_case, 4), deliverable=round(b, 4),
                    worse_by=round(float(worse), 4), flagged=float(worse) > tol))
        return rows


__all__ = ["DeliverableService", "DeliverableStore", "DeliverableRefused", "target_structures", "planning_goals", "capped_fluence", "MCO_PLAN_PREFIX"]
