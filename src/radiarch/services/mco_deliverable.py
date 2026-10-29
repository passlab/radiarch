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
from typing import Callable, Dict, List, Optional

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.beam_model import Modality
from ..models.dose import dose_units_for
from ..models.mco import DeliverableRequest, DeliverableStage, DeviationRow, MCODeliverable
from ..models.optimization import ConvergenceInfo, ObjectiveSpec, OptimizationResult
from .clinical_goals import parse_metric
from .mco import MCOService
from .navigation import NavigationService

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
        return request.compute_cache_key(result.cache_key, state.blend)

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
        dose_full = forward(x)
        projected_stack = ops.navigation(ops.forward(x))

        # 2. the navigated plan as an optimization (its weights and dose): the reference, and the input of sequencing
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
                beam_model_id=result.beam_model_id, engine_name=prob.engine.name, engine_version=prob.engine.version)
            osvc.store.save(opt_id=opt_id, cache_key=opt_key, weights=x.astype(np.float32), dose=dose_full,
                            spacing_mm=prob.geometry.spacing_mm, result=opt)

        # 3. the deliverable plan
        modality = prob.beam_model.result.modality
        targets = request.targets or target_structures(result)
        mimic = [ObjectiveSpec(type="ReferenceDose", structure_name=nm, dose_gy=0.0,
                               weight=request.target_priority if nm in targets else 1.0, reference_dose_uri=opt.dose_ref_uri,
                               reference_role="target" if nm in targets else "organ") for nm in result.navigation_structures]
        sequence_id = vmat_id = dose_id = None
        if modality is Modality.photon_imrt and request.arcs:
            on(DeliverableStage.mimicking, 0.35, "arcs from the navigated sector fluence, metersets mimicking its dose")
            vm = VMATService().arcs(opt.optimization_id, ArcRequest(
                objectives=mimic, arcs=request.arcs, fractions=request.fractions, machine_model_id=request.machine_model_id,
                dose_engine=mreq.dose_engine, max_iterations=request.max_iterations))
            technique, vmat_id, beam_model_id, dose_id, deliverable = "vmat", vm.vmat_id, vm.beam_model_id, vm.dose_id, vm.deliverable
        elif modality is Modality.photon_imrt:
            on(DeliverableStage.mimicking, 0.35, "apertures from the navigated fluence, metersets mimicking its dose")
            seq = ApertureService().sequence(opt.optimization_id, SequenceRequest(
                objectives=mimic, levels=request.levels, machine_model_id=request.machine_model_id, max_iterations=request.max_iterations))
            technique, sequence_id, beam_model_id, dose_id, deliverable = "imrt", seq.sequence_id, seq.beam_model_id, seq.dose_id, seq.deliverable
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
            deliverable_id=str(uuid.uuid4()), cache_key=key, mco_id=mco_id, state_id=state.state_id, geometry_id=result.geometry_id,
            blend=state.blend, projected=projected, technique=technique, optimization_id=opt.optimization_id, sequence_id=sequence_id,
            vmat_id=vmat_id, beam_model_id=beam_model_id, dose_id=dose_id, normalisation=float(k), deliverable=bool(deliverable),
            deviation=rows, flagged=sum(r.flagged for r in rows), notes=notes, seconds=round(time.time() - t0, 1),
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


__all__ = ["DeliverableService", "DeliverableStore", "DeliverableRefused", "target_structures", "MCO_PLAN_PREFIX"]
