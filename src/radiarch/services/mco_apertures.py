"""A second Pareto set on a deliverable plan's apertures (roadmap R11.11; option B1 of
``docs/reports/mco-deliverable-options.md``; Bokrantz, Med Phys 39:6712, 2012).

The deliverable plan of a navigated state keeps the apertures cut from the navigated fluence (static segments, or an
arc's control points), but its dose departs from the navigated plan's: the apertures cannot reproduce the fluence they
were cut from. A second, small Pareto set is generated over that plan's metersets, the segment MU of static fields or
the interval MU of arcs, with the first set's trade-offs. Every plan in it has the same apertures, so a blend of its
plans is a meterset vector on those apertures: the plan navigation shows is a plan a machine can deliver, and making
it deliverable changes nothing but the metersets.

The dose is linear in the metersets ``z``. Static fields: the open-field dose matrix times each segment's coverage of
the beamlets (:func:`~radiarch.services.sequencing.plan_coverage`), exactly the deliverable plan's dose. Arcs: the
pencil-beam dose per MU of each control-point interval, as the VMAT step's meterset solve uses; the plan made from a
blend has its dose computed by the engine with the full kernel, as the VMAT step's. Only the navigation voxels are kept
for the set.

Every meterset stays at or above the machine's minimum (a segment's minimum MU, an interval's dose-rate floor), so the
solves run on the metersets above it. The limits are the first set's hard constraints and, when the deliverable plan
was made with ``hard_coverage``, the target's gEUD (a = -10) no lower than the deliverable plan's own and its maximum
at or below ``max_dose_factor`` times the prescription. Where no metersets on these apertures meet a limit with the
others, the feasibility run from the deliverable plan says so: the limit is relaxed to what that run reaches, and a
note names it. The second set therefore always exists.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from ..models.mco import (ApertureSetRequest, DeliverableRequest, DeliverableStage, MCODeliverable, MCOResult, MCORunRequest, MCOStage,
                          NavigationState)
from ..models.optimization import HardConstraint
from ..models.photon_plan import PhotonPlan
from .hard_constraints import HardConstraintTerm, solve_with_hard_constraints
from .mco import MCOOps, MCOProgressCallback, MCOService
from .objectives import _geud
from .optimization_solvers import get_solver

METERSETS_PREFIX = "metersets:"     # a plan of a second set: metersets:{source beam model}:{mco_id}:{key} (lineage reads it)


class ApertureSetRefused(ValueError):
    """A deliverable plan that has no second set (a proton plan; a plan of a second set)."""


@dataclass
class ApertureElements:
    """A deliverable photon plan's metersets as the elements of a second set."""

    kind: str                    # "segments" (static fields) or "arc intervals"
    plan: PhotonPlan             # the deliverable plan, normalised
    machine: object              # its PhotonMachineSpec
    z0: np.ndarray               # its metersets, beam by beam
    lower: np.ndarray            # the machine's minimum for each
    fractions: int

    def with_metersets(self, z: np.ndarray) -> PhotonPlan:
        from .vmat import with_metersets

        z = np.asarray(z, dtype=np.float64)
        beams, k = [], 0
        for b in self.plan.beams:
            n = len(b.segments)
            if b.arc is not None:
                beams.append(with_metersets(b, z[k:k + n]))
            else:
                beams.append(b.model_copy(update={"segments": [s.model_copy(update={"mu": float(v)}) for s, v in zip(b.segments, z[k:k + n])]}))
            k += n
        return PhotonPlan(name=f"{self.plan.name}-metersets", beams=beams, leaf_model=self.plan.leaf_model)

    def issues(self, plan: PhotonPlan) -> List[str]:
        """The machine limits a plan with these apertures and its metersets breaks (per beam or arc)."""
        from .sequencing import deliverability
        from .vmat import arc_report

        if self.kind == "arc intervals":
            return [f"{b.beam_id}: {i}" for b in plan.beams for i in arc_report(b, self.machine, None, (), self.fractions).issues]
        return [f"{r.beam_id}: {i}" for r in deliverability(plan, self.machine) for i in r.issues]


def deliverable_elements(d: MCODeliverable) -> ApertureElements:
    """The apertures and metersets of a deliverable photon plan (its normalised beam model) and their minimums."""
    from .beam_model import BeamModelService
    from .machine_model import PhotonMachineModel
    from .vmat import interval_timing

    if d.technique == "proton":
        raise ApertureSetRefused("a proton plan's spots are its plan: it has no apertures to navigate again")
    bms = BeamModelService()
    plan = bms.store.load_plan(d.beam_model_id)
    if not isinstance(plan, PhotonPlan):
        raise ApertureSetRefused(f"deliverable plan {d.deliverable_id} holds no photon plan")
    meta = bms.store.get_by_id(d.beam_model_id)
    machine = PhotonMachineModel.from_id(getattr(meta, "machine_model_id", None) or "default").spec
    fractions = int(d.request.fractions) if d.request is not None else 1
    z0 = np.asarray([float(s.mu) for b in plan.beams for s in b.segments])
    if any(b.arc is not None for b in plan.beams):
        lower = np.concatenate([interval_timing(b, machine, None, fractions).min_mu for b in plan.beams])
        kind = "arc intervals"
    else:
        lower = np.full(z0.size, float(machine.min_mu_per_segment))
        kind = "segments"
    return ApertureElements(kind, plan, machine, z0, lower, fractions)


def _arc_engine(mreq):
    from .dose_engines.registry import get_engine

    return get_engine(mreq.dose_engine.name), dict(mreq.dose_engine.params or {})


def _origin(geometry):
    return getattr(geometry, "origin_mm", None) or geometry.result.grid_spec.origin_mm


def element_matrix(el: ApertureElements, prob, mreq, rows: Optional[np.ndarray] = None) -> sp.csr_matrix:
    """The dose per MU of each element (voxels x elements, CSR), on the voxels ``rows`` (flat indices) or the whole grid."""
    from .sequencing import plan_coverage

    if el.kind == "segments":
        _, mat = prob.scenario_dij[prob.scenarios[0].hash()]
        mat = mat.tocsr()
        S = mat[rows] if rows is not None else mat
        return sp.csr_matrix(S @ plan_coverage(prob.beam_model.plan, el.plan))
    engine, params = _arc_engine(mreq)
    S = engine.segment_dose_matrix(prob.geometry.density, prob.geometry.spacing_mm, _origin(prob.geometry), el.plan, params=params).tocsr()
    return S[rows] if rows is not None else S


def element_dose(el: ApertureElements, z: np.ndarray, prob, mreq) -> np.ndarray:
    """The full dose of the plan with metersets ``z``: static fields through the open-field dose matrix (as the
    sequencer computes it), arcs by the engine from their apertures (as the VMAT step does)."""
    if el.kind == "segments":
        from .sequencing import plan_coverage

        _, mat = prob.scenario_dij[prob.scenarios[0].hash()]
        w = plan_coverage(prob.beam_model.plan, el.plan) @ np.asarray(z, dtype=np.float64)
        return np.asarray(mat @ w).reshape(prob.grid_shape).astype(np.float32)
    engine, params = _arc_engine(mreq)
    params["fluence"] = "apertures"
    dose = engine.compute_plan_dose(prob.geometry.density, prob.geometry.spacing_mm, _origin(prob.geometry), el.with_metersets(z), params=params)
    return np.asarray(dose, dtype=np.float32).reshape(prob.grid_shape)


def _noop(*_args) -> None:
    pass


class ApertureSetService:
    """``POST /mco/deliverables/{deliverable_id}/pareto``: the second set of a deliverable plan, stored with the Pareto
    sets (:class:`~radiarch.services.mco.MCOStore`), so that navigation, automatic navigation and the deliverable step
    work on it as on any set."""

    def __init__(self, mco_service: Optional[MCOService] = None, deliverable_service=None) -> None:
        from .mco_deliverable import DeliverableService

        self.mco = mco_service or MCOService()
        self.deliverables = deliverable_service or DeliverableService(mco_service=self.mco)

    def source(self, deliverable_id: str) -> MCODeliverable:
        d = self.deliverables.store.get_by_id(deliverable_id)
        if d is None:
            raise KeyError(deliverable_id)
        if d.technique == "proton":
            raise ApertureSetRefused("a proton plan's spots are its plan: it has no apertures to navigate again")
        first = self.mco.store.get_by_id(d.mco_id)
        if first is not None and first.source_deliverable_id:
            raise ApertureSetRefused(f"deliverable plan {deliverable_id} is a plan of a second set already: its apertures are "
                                     f"those of deliverable plan {first.source_deliverable_id}")
        return d

    def cache_key(self, deliverable_id: str, request: ApertureSetRequest) -> str:
        return request.compute_cache_key(self.source(deliverable_id).cache_key)

    def run(self, deliverable_id: str, request: ApertureSetRequest, progress_callback: Optional[MCOProgressCallback] = None) -> MCOResult:
        on = progress_callback or _noop
        d = self.source(deliverable_id)
        key = request.compute_cache_key(d.cache_key)
        cached = self.mco.store.lookup_by_cache_key(key)
        if cached is not None:
            on(MCOStage.done, 1.0, "cache hit")
            return cached
        t0 = time.time()
        on(MCOStage.loading, 0.02, "the deliverable plan's apertures and the first set's problem")
        first, mreq, prob = self.mco.problem(d.mco_id)
        el = deliverable_elements(d)
        osvc = self.mco.optimization

        # the navigation voxels: the first set's structures and the coverage target
        names = list(first.navigation_structures)
        limits: List[HardConstraint] = list(first.hard_constraints)
        req = d.request
        cover = req is not None and req.hard_coverage and req.normalise is not None
        if cover and req.normalise.structure not in names:
            names.append(req.normalise.structure)
        full = {nm: osvc._resolve_mask(prob.geometry, nm, prob.grid_shape).ravel() > 0 for nm in names}
        union = np.zeros(int(np.prod(prob.grid_shape)), dtype=bool)
        for m in full.values():
            union |= m
        index = np.flatnonzero(union).astype(np.int64)
        structures = {nm: m[index] for nm, m in full.items()}

        if el.kind == "arc intervals":
            on(MCOStage.loading, 0.05, f"the dose per MU of {el.z0.size} arc intervals")
        S = element_matrix(el, prob, mreq, index)
        ST = S.T.tocsr()
        lower = el.lower
        base = np.asarray(S @ lower, dtype=np.float64)

        def forward(y: np.ndarray) -> np.ndarray:
            return base + np.asarray(S @ np.asarray(y, dtype=np.float64).ravel())

        def backward(g: np.ndarray) -> np.ndarray:
            return np.asarray(ST @ np.asarray(g, dtype=np.float64).ravel(), dtype=np.float64)

        y0 = np.maximum(el.z0 - lower, 0.0)
        notes = [f"a second set over the metersets of the {el.z0.size} {el.kind} of deliverable plan {d.deliverable_id}: every plan "
                 f"keeps its apertures, so every blend is deliverable as navigated"
                 + (" (static fields: exactly; arcs: the pencil beam's interval doses, the plan's dose then by the full kernel)"
                    if el.kind == "arc intervals" else "")]
        if cover:
            target = req.normalise.structure
            mask = structures[target].astype(np.float64)
            g0 = float(_geud(forward(y0), mask, float(mask.sum()), -10.0)[0])
            rx = req.prescription_gy or req.normalise.gy
            top = req.max_dose_factor * rx
            # within 1 % of each level (0.6 Gy at 60 Gy): the first stage's 0.5 Gy would let a small prescription's plans
            # give up a quarter of their coverage
            limits += [HardConstraint(structure_name=target, metric="gEUD", op=">=", value_gy=round(g0, 3), eud_a=-10.0,
                                      tolerance_gy=round(max(0.01 * g0, 1e-3), 4)),
                       HardConstraint(structure_name=target, metric="Dmax", op="<=", value_gy=round(top, 3), tolerance_gy=round(max(0.01 * top, 1e-3), 4))]
            notes.append(f"{target}'s coverage held at the deliverable plan's gEUD (a = -10, {g0:.2f} Gy) and its maximum at "
                         f"{req.max_dose_factor:g} times the prescription")

        terms = [HardConstraintTerm(c, structures[c.structure_name].astype(np.float64)) for c in limits]
        if terms:
            on(MCOStage.feasibility, 0.08, f"the limits on these apertures: feasibility of {len(terms)} hard constraint(s)")
            solver = get_solver(request.solver.method)
            feas = solve_with_hard_constraints(terms, forward, backward, y0, solver, request.solver.max_iterations,
                                               request.solver.convergence_tol or 1e-10)
            relaxed: List[HardConstraint] = []
            for c, o in zip(limits, feas.outcomes):
                if o.met:
                    relaxed.append(c)
                    continue
                relaxed.append(c.model_copy(update={"value_gy": round(float(o.achieved_gy), 3)}))
                notes.append(f"{c.label} is relaxed to {o.achieved_gy:.2f} Gy: no metersets on these apertures meet it with the "
                             f"other limits (the feasibility run's best)")
            limits, y0 = relaxed, np.asarray(feas.weights, dtype=np.float64)
            terms = [HardConstraintTerm(c, structures[c.structure_name].astype(np.float64)) for c in limits]

        n = len(first.tradeoffs)
        mreq2 = MCORunRequest(requested_by=request.requested_by, geometry_id=d.geometry_id, beam_model_id=d.beam_model_id,
                              dose_engine=mreq.dose_engine, tradeoffs=first.tradeoffs, hard_constraints=limits, solver=request.solver,
                              plan_budget=request.plan_budget or 2 * n + 1, error_tolerance=request.error_tolerance,
                              anchor_epsilon=request.anchor_epsilon, navigation_structures=names, rbe=mreq.rbe)
        ops = MCOOps([o for o, _ in prob.obj_terms], [np.asarray(m).ravel()[index].astype(np.float64) for _, m in prob.obj_terms],
                     forward, backward, terms, None, index, structures, [], on_voxels=True)
        fields = dict(geometry_id=d.geometry_id, beam_model_id=d.beam_model_id, engine_name=first.engine_name, engine_version=first.engine_version,
                      rbe_factor=first.rbe_factor, dose_units=first.dose_units, voxel_cc=first.voxel_cc, modality=first.modality,
                      source_deliverable_id=d.deliverable_id, elements=el.kind)
        result = self.mco.generate(mreq2, ops, y0, key, fields, notes, on, t0, stored=lambda y: lower + np.asarray(y, dtype=np.float64))
        logger.info("Second set {} on deliverable plan {}: {} {}, {} plans, error bound {:.4f}", result.mco_id, d.deliverable_id, el.z0.size,
                    el.kind, len(result.plans), result.error_bound)
        return result


def deliver_on_apertures(dsvc, mco_id: str, result: MCOResult, request: DeliverableRequest, state: NavigationState, key: str,
                         on: Callable[[DeliverableStage, float, str], None], t0: float) -> MCODeliverable:
    """A state of a second set made deliverable: its blend's metersets on the first deliverable plan's apertures, the
    plan's dose, its normalisation (a check near 1), and the deviation table against the navigated blend."""
    from .autoplan import AutoplanService, normalise_to_goal
    from .beam_model import BeamModelService
    from .beam_persistence import BeamModelPaths
    from .dose import DoseService, _summary_stats
    from .dose_persistence import DOSE_FILENAME
    from ..models.beam_model import FluenceElementSet, PerBeamElements

    d = dsvc.store.get_by_id(result.source_deliverable_id)
    if d is None:
        raise ValueError(f"the second set's deliverable plan {result.source_deliverable_id} is gone")
    lam = np.asarray(state.blend, dtype=np.float64)
    z = lam @ dsvc.mco.store.load_weights(mco_id).astype(np.float64)
    _, mreq, prob = dsvc.mco.problem(d.mco_id)
    el = deliverable_elements(d)
    notes = [f"the metersets of state {state.state_id} on the apertures of deliverable plan {d.deliverable_id}"]
    if request.project:
        notes.append("not projected: a second set's blend is already a deliverable plan")
    on(DeliverableStage.metersets, 0.2, f"the blend's metersets on the {el.z0.size} {el.kind}; its dose")
    plan = el.with_metersets(z)
    dose = element_dose(el, z, prob, mreq)
    issues = el.issues(plan)
    notes += issues

    bms, ds = BeamModelService(), DoseService()
    src_bm, src_dose = bms.store.get_by_id(d.beam_model_id), ds.dose_store.get_by_id(d.dose_id)
    bm_key = f"{METERSETS_PREFIX}{d.beam_model_id}:{mco_id}:{key}"
    bm_id = str(uuid.uuid4())
    per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=b.n_beamlets, active_beamlets=b.n_beamlets) for b in plan.beams]
    bm = src_bm.model_copy(update={"beam_model_id": bm_id, "cache_key": bm_key, "plan_weights_uri": None,
                                   "fluence_elements": FluenceElementSet(total_count=plan.n_beamlets, per_beam=per_beam),
                                   "beam_model_ref_uri": str(BeamModelPaths.for_id(bms.store.base_dir, bm_id).plan)})
    bms.store.save(beam_model_id=bm_id, cache_key=bm_key, plan=plan, result=bm)
    dose_id = str(uuid.uuid4())
    dres = src_dose.model_copy(update={"dose_id": dose_id, "beam_model_id": bm_id, "cache_key": bm_key, "scenario_doses": None,
                                       "dose_grid_uri": str(ds.dose_store.base_dir / dose_id / DOSE_FILENAME), "statistics": _summary_stats(dose),
                                       "created_at": datetime.now(timezone.utc)})
    ds.dose_store.save(dose_id=dose_id, cache_key=bm_key, nominal_dose=dose, spacing_mm=tuple(prob.geometry.spacing_mm), scenario_doses=None,
                       result=dres)
    beam_model_id, delivered = bm_id, dose

    k = 1.0
    if request.normalise is not None:
        on(DeliverableStage.normalising, 0.8, "normalising the metersets")
        mask = dsvc.mco.optimization._resolve_mask(prob.geometry, request.normalise.structure, prob.grid_shape) > 0
        _, k = normalise_to_goal(delivered, delivered[mask], request.normalise.metric, request.normalise.gy)
        bm_n, dose_n, delivered = AutoplanService._scaled(beam_model_id, dose_id, k, key)
        beam_model_id, dose_id = bm_n.beam_model_id, dose_n.dose_id

    on(DeliverableStage.comparing, 0.9, "comparing the deliverable plan with the navigated one")
    index, _, _ = dsvc.mco.store.load_navigation(mco_id)
    rows = dsvc._deviation(mco_id, request, lam, None, np.asarray(delivered).ravel()[index][None, :])
    out = MCODeliverable(
        requested_by=request.requested_by, deliverable_id=str(uuid.uuid4()), cache_key=key, mco_id=mco_id, state_id=state.state_id,
        geometry_id=result.geometry_id, blend=state.blend, projected=False, technique=d.technique, optimization_id=d.optimization_id,
        sequence_id=d.sequence_id, vmat_id=d.vmat_id, beam_model_id=beam_model_id, dose_id=dose_id, normalisation=float(k),
        deliverable=bool(d.deliverable) and not issues, deviation=rows, flagged=sum(r.flagged for r in rows), request=request, rounds=[],
        notes=notes, seconds=round(time.time() - t0, 1), created_at=datetime.now(timezone.utc))
    dsvc.store.save(out)
    on(DeliverableStage.done, 1.0, f"deliverable {out.deliverable_id}: {out.flagged} flagged")
    logger.info("Second set {} state {}: {} plan {} on the apertures of {}, normalised by {:.4f}, {} flagged", mco_id, state.state_id,
                d.technique, beam_model_id, d.deliverable_id, k, out.flagged)
    return out


__all__ = ["ApertureSetService", "ApertureSetRefused", "ApertureElements", "deliverable_elements", "element_matrix", "element_dose",
           "deliver_on_apertures", "METERSETS_PREFIX"]
