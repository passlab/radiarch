"""Validation cases of roadmap R11: multi-criteria optimization (docs/reports/mco-research-and-design.md, section 5).

``mco_front``: TG-119's C-shape as a two-objective Pareto set (the outer target's homogeneity against the core's EUD),
the target held at a minimum dose in every plan. The front is drawn from the computed plans and the sandwich error
bound followed as plans are added; the set is navigated automatically by TG-119's goals and made deliverable.

``mco_protocol``: the lung demo (NSCLC-Radiomics ``LUNG1-002``) planned by a protocol's ``mco`` section and by the
reweighting rounds of the protocol it extends, compared goal by goal; the navigated plan against its deliverable plans
(static fields and two arcs); plans and minutes against the error bound.

``mco_robust``: a proton phantom (a target, an organ behind it, a bone slab over half the anterior field) as a
robust Pareto set on MCsquare: worst-case and nominal values, the hard constraint in every scenario, robust plans
against the nominal set's plans in the scenarios, navigation and the deliverable spots.

Every set is checked the same way (:func:`_set_checks`): the bound never grows, no plan dominates another, each plan
is the best of the set in its own weighted sum, every hard constraint holds in every plan. ``run.py`` registers
:data:`KINDS_R11`; the cases are YAML files in ``cases/`` like the others.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import numpy as np

from .cases_r7 import _goal_value, _services
from .common import RADIARCH_ROOT, CaseResult, Context, Skip, data_root, load_reference


# ---------------------------------------------------------------------------
# What every Pareto set is checked for
# ---------------------------------------------------------------------------

def _names(mco) -> List[str]:
    return [f"{t.type}({t.structure_name})" for t in mco.tradeoffs]


def _constraint_value(dose: np.ndarray, hc) -> float:
    if hc.metric == "Dmax":
        return float(dose.max())
    if hc.metric == "Dmin":
        return float(dose.min())
    if hc.metric == "Dmean":
        return float(dose.mean())
    a = float(hc.eud_a)
    return float(np.mean(np.maximum(dose, 1e-9) ** a) ** (1.0 / a))


def _set_checks(res: CaseResult, label: str, mco, store) -> dict:
    """The algorithm's guarantees on a computed set, and its front and error history for the record."""
    errs = [p.error for p in mco.error_history]
    res.add(f"{label}: the error bound never grows as plans are added", " → ".join(f"{e:.3f}" for e in errs), "non-increasing",
            all(b <= a + 1e-6 for a, b in zip(errs, errs[1:])), f"{len(mco.plans)} plans; {mco.stop_reason}")
    # the guarantees hold for plans whose solve reached the optimum: a converged plan must not be beaten by any point of
    # the set (an unconverged plan is still an attainable point); unconverged plans are counted and left out, as the
    # error bound leaves them out
    P = np.array([p.normalized for p in mco.plans])
    conv = [k for k, p in enumerate(mco.plans) if p.converged]
    not_conv = [p.index for p in mco.plans if not p.converged]
    gains = ", ".join("-" if p.gain is None else f"{p.gain:.1e}" for p in mco.plans)
    res.add(f"{label}: plans whose solve converged", f"{len(conv)} of {len(mco.plans)}", "informative", None,
            "converged: the cost fell by at most 1e-5 of itself over the last 50 iterations (stopped falling, not proven "
            "optimal); "
            + (f"not converged: {not_conv}; the checks below and the error bound use the converged plans; " if not_conv else "")
            + f"gain still on offer per plan, over its cost at its start (a loose first-order bound, reported only): {gains}")
    # dominance is informative: an anchor weighs the other trade-offs at 1e-3, so it is optimal only to within that, and
    # a robust plan minimizes its worst scenario, not its weighted worst cases; the graded test is each plan's own sum
    dominated = [(j, k) for k in range(len(P)) for j in range(len(P)) if j != k and np.all(P[j] <= P[k] - 1e-6)]
    res.add(f"{label}: plans dominated by another plan", len(dominated), "informative", None,
            (f"pairs (better, worse) {dominated}" if dominated else "")
            + ("; in the trade-offs' worst cases over the scenarios" if mco.scenarios else ""))
    if mco.scenarios and conv:
        # each robust plan minimizes the worst scenario of its weighted sum: no plan of the set does better in it (less
        # the smoothing's slack), on the stored scenario doses
        from ..services.optimization import _objective_from_spec
        from ..services.robust_mco import smoothing_width
        tau = smoothing_width(mco.tradeoffs, mco.hard_constraints)
        scen = np.asarray(store.load_scenario_doses(mco.mco_id))                       # scenarios x plans x voxels
        _, _, nav_masks = store.load_navigation(mco.mco_id)
        objs = [_objective_from_spec(t.model_copy(update={"weight": 1.0})) for t in mco.tradeoffs]
        vals = np.array([[[o.value(scen[sc, k], nav_masks[t.structure_name].astype(float)) for o, t in zip(objs, mco.tradeoffs)]
                          for k in range(scen.shape[1])] for sc in range(scen.shape[0])])          # scenarios x plans x trade-offs
        span = np.array(mco.nadir_gy) - np.array(mco.ideal_gy)
        span = np.where(span > 1e-9, span, 1.0)
        worst, pair = 0.0, None
        for k in conv:
            w = np.array(mco.plans[k].weights)
            sw = (vals @ w).max(axis=0)                                                 # each plan's worst scenario
            gap = float((sw[k] - sw.min() - tau * w.sum() * np.log(scen.shape[0])) / (w @ span))
            if gap > worst:
                worst, pair = gap, (int(np.argmin(sw)), k)
        res.add(f"{label}: each converged plan is the best of the set in its own worst-scenario sum", round(worst, 4), "<= 0.01",
                worst <= 0.01, "the largest amount by which another plan beats a plan in that plan's own objective (normalized, less "
                "the smoothing's slack)" + (f"; plan {pair[0]} beats plan {pair[1]}" if pair else ""))
    if not mco.scenarios and conv:
        # each converged plan minimizes its own weighted sum: no plan of the set does better in it (normalized, solver tolerance)
        span = np.array(mco.nadir_gy) - np.array(mco.ideal_gy)
        span = np.where(span > 1e-9, span, 1.0)
        worst, pair = 0.0, None
        for k in conv:
            a = np.array(mco.plans[k].weights) * span
            a = a / a.sum()
            gap = float(a @ P[k] - (P @ a).min())
            if gap > worst:
                worst, pair = gap, (int(np.argmin(P @ a)), k)
        res.add(f"{label}: each converged plan is the best of the set in its own weighted sum", round(worst, 4), "<= 0.01", worst <= 0.01,
                "the largest amount by which another plan beats a plan in that plan's own weighted sum (normalized)"
                + (f"; plan {pair[0]} beats plan {pair[1]}" if pair else ""))
    if mco.hard_constraints:
        _, doses, masks = store.load_navigation(mco.mco_id)
        scen = store.load_scenario_doses(mco.mco_id)
        stack = np.asarray(scen) if scen is not None else np.asarray(doses)[None]
        for hc in mco.hard_constraints:
            if hc.structure_name not in masks:
                res.notes.append(f"{label}: {hc.structure_name} not among the navigation structures; its constraint is not checked here")
                continue
            m = masks[hc.structure_name]
            vals = np.array([[_constraint_value(stack[s, k][m], hc) for k in range(stack.shape[1])] for s in range(stack.shape[0])])
            worst = vals.max() if hc.op == "<=" else vals.min()
            ok = worst <= hc.value_gy + hc.tolerance_gy if hc.op == "<=" else worst >= hc.value_gy - hc.tolerance_gy
            where = f"in every plan and all {stack.shape[0]} scenarios" if scen is not None else "in every plan"
            res.add(f"{label}: hard constraint {hc.structure_name} {hc.metric} {hc.op} {hc.value_gy} Gy {where}", round(float(worst), 3),
                    f"{hc.op} {hc.value_gy} (tolerance {hc.tolerance_gy})", ok, "the worst plan, on the navigation voxels")
    tol = _tolerance(mco, store)
    for e in mco.error_history:
        res.add(f"{label}: error bound with {e.plans} plans", round(e.error, 4), f"tolerance {tol}", None,
                "approximate: the converged plans are taken as optimal"
                + (f"; {e.seconds / 60:.1f} min from the start" if e.seconds else ""))
    front = {"tradeoffs": _names(mco), "ideal_gy": mco.ideal_gy, "nadir_gy": mco.nadir_gy,
             "plans": [{"index": p.index, "kind": p.kind, "weights": p.weights, "converged": p.converged, "gain": p.gain, "values_gy": p.values_gy,
                        "nominal_gy": p.nominal_gy} for p in mco.plans],
             "error_history": [e.model_dump() for e in mco.error_history], "error_bound": mco.error_bound, "converged": mco.converged,
             "stop_reason": mco.stop_reason, "robust_gap": mco.robust_gap, "seconds": mco.compute_time_s, "notes": mco.notes}
    return front


def _tolerance(mco, store) -> float:
    import json
    path = store.dir(mco.mco_id) / "request.json"
    return float(json.loads(path.read_text(encoding="utf-8"))["error_tolerance"]) if path.is_file() else float("nan")


def _deviation_checks(res: CaseResult, label: str, d) -> None:
    tol = f"flagged when worse by more than {d.request.tolerance_gy} Gy or {d.request.tolerance_volume} % volume" if d.request else "informative"
    res.add(f"{label}: deliverable", d.deliverable, "True", d.deliverable, f"{d.technique}; normalised by {d.normalisation:.4f}")
    for r in d.deviation:
        unit = r.unit
        res.add(f"{label}: {r.name} navigated → deliverable ({unit})",
                f"{r.navigated:.2f} → {r.deliverable:.2f}" if r.navigated is not None and r.deliverable is not None else None,
                tol, None,
                ("FLAGGED: " if r.flagged else "") + (f"worse by {r.worse_by:.2f}" if r.worse_by is not None else "")
                + (f"; projected {r.projected:.2f}" if r.projected is not None else ""))
    res.add(f"{label}: flagged rows of the deviation table", d.flagged, "informative", None,
            "a flag is a row where the deliverable plan is worse than the navigated one past its tolerance")


# ---------------------------------------------------------------------------
# mco_front — TG-119's C-shape as a two-objective front
# ---------------------------------------------------------------------------

def run_mco_front(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    import pydicom

    from ..models.dose import EngineSpec
    from ..models.evaluation import GoalSetSpec
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..models.mco import AutoNavigateRequest, DeliverableRequest, MCORunRequest, NormaliseSpec
    from ..models.optimization import HardConstraint, ObjectiveSpec, SolverConfig
    from ..services.autoplan import NORMALISATION_HEADROOM, static_beam_model
    from ..services.geometry import GeometryService
    from ..services.geometry_bundle import load_geometry_arrays
    from ..services.mco import MCOService
    from ..services.mco_deliverable import DeliverableService
    from ..services.navigation import NavigationService
    from .cases_r8 import _pb_engine

    ref = load_reference("tg119_goals")
    root = data_root() / Path(spec["data"]).name / ref["phantom"]["package"].split("/")[-1]
    if not root.is_dir():
        raise Skip(f"TG-119 package not found at {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    engine = str(spec.get("engine", "ccc"))
    if engine == "pb":
        _pb_engine()
    _services(ctx)
    case = ref["cases"][spec["case"]]
    target, rx = case["target"], float(case["prescription_gy"])
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    beamlet = float(spec.get("beamlet_mm", 5.0)) * (2.0 if ctx.fast else 1.0)
    rs = pydicom.dcmread(root / case["rtstruct"], stop_before_pixels=True)
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"tg119-{case['rtstruct']}", rtstruct_uid=str(rs.SOPInstanceUID)),
                                                       data_root_override=str(root), grid_spec=GridSpec(spacing_mm=(s, s, s))))
    arrays = load_geometry_arrays(geo)
    bm = static_beam_model(geo, arrays, target, case["goals"], case["beams"], beamlet, float(spec.get("jaw_margin_mm", 20.0)),
                           spec.get("machine", "synthetic-120"))
    tradeoffs = [ObjectiveSpec(**t) for t in spec["tradeoffs"]]
    mreq = MCORunRequest(geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name=engine, params=spec.get("engine_params", {})),
                         tradeoffs=tradeoffs, hard_constraints=[HardConstraint(**h) for h in spec.get("hard_constraints", [])],
                         solver=SolverConfig(method="L-BFGS-B", max_iterations=int(spec.get("iterations", 200) / (2 if ctx.fast else 1))),
                         plan_budget=int(spec.get("plan_budget", 9)) if not ctx.fast else min(5, int(spec.get("plan_budget", 9))),
                         error_tolerance=float(spec.get("error_tolerance", 0.02)),
                         navigation_structures=[g["structure"] for g in case["goals"]])
    msvc = MCOService()
    mco = msvc.run(mreq)
    front = _set_checks(res, spec["case"], mco, msvc.store)
    res.metrics["front"] = front
    res.metrics["case"] = {"geometry_id": geo.geometry_id, "beam_model_id": bm.beam_model_id, "grid_mm": s, "beamlet_mm": beamlet,
                           "beams": case["beams"], "engine": engine}
    for p in mco.plans:
        res.add(f"plan {p.index} ({p.kind})", ", ".join(f"{n} {v:.2f}" for n, v in zip(front["tradeoffs"], p.values_gy)), "the front", None)

    # automatic navigation by TG-119's goals, then the static fields' apertures, normalised to the coverage goal
    goals = GoalSetSpec(goals=[{"structure": g["structure"], "metric": f"{g['metric']}%[Gy]" if g["metric"][1:].isdigit() else g["metric"],
                                "op": g["op"], "value": g["gy"], "priority": 1 if g["op"].startswith(">") else 2} for g in case["goals"]])
    state = NavigationService(msvc.store).auto_navigate(mco.mco_id, AutoNavigateRequest(goals=goals, prescription_gy=rx, fractions=1,
                                                                                       name="TG-119 goals"))
    res.add("automatic navigation: levels", len(state.levels), "informative", None,
            "; ".join(f"priority {lv.priority}: {lv.passed} of {lv.goals} met, shortfall {lv.shortfall_before:.3f} → {lv.shortfall:.3f}"
                      for lv in state.levels))
    for g in (state.goals.results if state.goals else []):
        res.add(f"navigated: {g.structure} {g.metric} {g.op} {g.value}", round(float(g.achieved), 2) if g.achieved is not None else None,
                f"{g.op} {g.value}", None, "the navigated blend (not yet deliverable)")
    cover = next(g for g in case["goals"] if g["op"].startswith(">"))
    d = DeliverableService(mco_service=msvc).run(mco.mco_id, DeliverableRequest(
        state_id=state.state_id, fractions=1, levels=int(spec.get("sequence_levels", 10)), machine_model_id=spec.get("machine", "synthetic-120"),
        max_iterations=int(spec.get("iterations", 200)), goals=goals, prescription_gy=rx,
        normalise=NormaliseSpec(structure=cover["structure"], metric=cover["metric"], gy=cover["gy"] * NORMALISATION_HEADROOM)))
    _deviation_checks(res, "deliverable (static fields)", d)
    res.metrics["deliverable"] = {"deliverable_id": d.deliverable_id, "dose_id": d.dose_id, "flagged": d.flagged, "normalisation": d.normalisation}

    # the deliverable plan against TG-119's goals and the institutions' results (as tg119_planning grades them)
    from ..services.dose import DoseService
    from .cases_r7 import _read_volume
    dose = _read_volume(DoseService().dose_store.get_by_id(d.dose_id).dose_grid_uri)
    pub = ref.get("published", {}).get(spec["case"], {})
    recorded = {}
    if spec.get("record") and (RADIARCH_ROOT / spec["record"]).is_file():
        import json
        prior_run = json.loads((RADIARCH_ROOT / spec["record"]).read_text(encoding="utf-8"))
        recorded = {c["name"]: c for r in prior_run["results"] if r["kind"] == "tg119_planning" for c in r["checks"]}
    for g in case["goals"]:
        st = g["structure"]
        value = _goal_value(dose[arrays.mask_zyx(arrays.structure_index[st])], g["metric"])
        op, limit = g["op"], float(g["gy"])
        met = value >= limit - 1e-6 if op.startswith(">") else value <= limit + 1e-6
        passed, target_text, note = met, f"{op} {limit}", "TG-119 planning goal"
        if f"{st} {g['metric']}" in pub:
            mean, sd = pub[f"{st} {g['metric']}"]
            bound = max(limit, mean + 2 * sd) if not op.startswith(">") else min(limit, mean - 2 * sd)
            passed = met or (value <= bound + 1e-6 if not op.startswith(">") else value >= bound - 1e-6)
            if bound != limit:
                target_text = f"{op} {limit} (or {op} {bound:.2f}: institutional mean {mean} ± 2 SD)"
            note += f"; institutional mean {mean} (SD {sd})"
        res.add(f"deliverable: {st} {g['metric']} (Gy)", round(value, 2), target_text, passed, note)
        prior = recorded.get(f"{spec['case']}: {st} {g['metric']} (Gy)")
        if prior is not None:
            res.add(f"deliverable against the recorded reweighting plan: {st} {g['metric']} (Gy)", f"{value:.2f} vs {prior['value']}", "informative", None,
                    "the tg119_planning case's plan in the record named by the case (fluence, four reweighting rounds)")
    res.notes.append("the deliverable plan's dose is recomputed by the engine from its sequenced apertures; TG-119's institutional "
                     "results are deliverable plans too")
    return res


# ---------------------------------------------------------------------------
# mco_protocol — the lung demo by its mco protocol and by the reweighting rounds
# ---------------------------------------------------------------------------

def _patient_dir(ctx: Context, pdir: Path, tag: str) -> Path:
    """The patient's CT and structure set in one directory (the geometry service reads one; a SEG beside them is left out)."""
    out = ctx.workdir / tag
    out.mkdir(parents=True, exist_ok=True)
    for sub in list(pdir.glob("CT_*")) + list(pdir.glob("RTSTRUCT_*")):
        for f in sub.glob("*.dcm"):
            dst = out / f"{sub.name[:2]}_{f.name}"
            if not dst.exists():
                os.symlink(f, dst)
    return out


def _template_goals(evaluation_id: Optional[str]) -> dict:
    from ..services.evaluation import EvaluationService
    ev = EvaluationService().store.get_by_id(evaluation_id) if evaluation_id else None
    return {f"{g.structure} {g.metric} {g.op} {g.value}": g for g in (ev.goals.results if ev and ev.goals else []) if g.achieved is not None}


def run_mco_protocol(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..models.protocol import ProtocolRunRequest
    from ..services.autoplan import AutoplanService, load_protocol
    from ..services.geometry import GeometryService
    from ..services.mco import MCOService
    from ..services.mco_deliverable import DeliverableService
    from .cases_r8 import _pb_engine

    _pb_engine()
    pdir = data_root() / Path(spec["data"]).name / spec["patient"]
    if not pdir.is_dir():
        raise Skip(f"data not found: {pdir} (set RADIARCH_VALIDATION_DATA to the directory holding it; radiarch fetch-tcia fetches it)")
    _services(ctx)
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    case_dir = _patient_dir(ctx, pdir, f"{spec['name']}-{spec['patient']}")
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"{spec['name']}-{spec['patient']}"),
                                                       data_root_override=str(case_dir), grid_spec=GridSpec(spacing_mm=(s, s, s))))
    protocol, baseline = load_protocol(spec["protocol"]), load_protocol(spec["baseline"])
    if ctx.fast:
        protocol = protocol.model_copy(update={"mco": protocol.mco.model_copy(update={"plan_budget": len(protocol.mco.tradeoffs) + 2})})
    runs = {}
    for which, p in (("reweighting", baseline), ("mco", protocol)):
        runs[which] = AutoplanService().run(ProtocolRunRequest(geometry_id=geo.geometry_id, protocol=p))
        r = runs[which]
        res.add(f"{p.protocol_id}: deliverable", r.deliverable, "True", r.deliverable, f"normalised by {r.normalisation:.4f}; {r.seconds / 60:.1f} min")
    ev_b, ev_m = _template_goals(runs["reweighting"].evaluation_id), _template_goals(runs["mco"].evaluation_id)
    for name, g in ev_m.items():
        b = ev_b.get(name)
        res.add(f"{name}: MCO plan", round(float(g.achieved), 2), f"{g.op} {g.value}", bool(g.passed) if int(g.priority) == 1 else None,
                f"{protocol.evaluation_template} priority {g.priority}")
        if b is not None:
            better = (g.achieved >= b.achieved) if g.op.startswith(">") else (g.achieved <= b.achieved)
            res.add(f"{name}: MCO against the reweighting plan", f"{g.achieved:.2f} vs {b.achieved:.2f}", "informative", None,
                    ("MCO no worse" if better else "MCO worse") + f"; reweighting plan {'meets' if b.passed else 'misses'} it")
    m = runs["mco"]
    msvc = MCOService()
    mco = msvc.store.get_by_id(m.mco_id)
    res.metrics["front"] = _set_checks(res, "Pareto set", mco, msvc.store)
    res.metrics["runs"] = {k: {"run_id": r.run_id, "seconds": r.seconds, "normalisation": r.normalisation, "history": r.history,
                               "goals": [g.model_dump() for g in r.goals]} for k, r in runs.items()}
    res.metrics["goals"] = {"reweighting": {k: v.model_dump() for k, v in ev_b.items()}, "mco": {k: v.model_dump() for k, v in ev_m.items()}}
    dsvc = DeliverableService(mco_service=msvc)
    d_imrt = dsvc.store.get_by_id(m.deliverable_id)
    _deviation_checks(res, "deliverable (seven static fields)", d_imrt)
    if spec.get("arcs"):
        # arcs need a Pareto set on the arcs' sectors (a static-field set cannot be swept into arcs): the same protocol
        # with the arcs as its beams, its own set, navigation and deliverable plan
        from ..models.protocol import BeamArrangement
        vmat = protocol.model_copy(update={"protocol_id": f"{protocol.protocol_id}-arcs", "beams": BeamArrangement(technique="vmat", arcs=spec["arcs"]),
                                           "mco": protocol.mco.model_copy(update={"plan_budget": len(protocol.mco.tradeoffs) + 1 if ctx.fast
                                                                                   else int(spec.get("vmat_plan_budget", 8))})})
        try:
            rv = AutoplanService().run(ProtocolRunRequest(geometry_id=geo.geometry_id, protocol=vmat))
            res.add(f"{vmat.protocol_id}: deliverable", rv.deliverable, "True", rv.deliverable,
                    f"normalised by {rv.normalisation:.4f}; {rv.seconds / 60:.1f} min")
            mv = msvc.store.get_by_id(rv.mco_id)
            res.metrics["front_arcs"] = _set_checks(res, "Pareto set on the arcs' sectors", mv, msvc.store)
            d_vmat = dsvc.store.get_by_id(rv.deliverable_id)
            _deviation_checks(res, "deliverable (two arcs)", d_vmat)
            for name, g in _template_goals(rv.evaluation_id).items():
                res.add(f"{name}: MCO plan (two arcs)", round(float(g.achieved), 2), f"{g.op} {g.value}",
                        bool(g.passed) if int(g.priority) == 1 else None, f"{protocol.evaluation_template} priority {g.priority}")
            res.metrics["deliverable_vmat"] = {"run_id": rv.run_id, "deliverable_id": d_vmat.deliverable_id, "seconds": rv.seconds,
                                               "flagged": d_vmat.flagged}
        except Exception as exc:  # noqa: BLE001  (the static-field results above stay in the record)
            res.add("the arcs' Pareto set and deliverable plan", f"{type(exc).__name__}: {exc}"[:300], "made", False)
    res.metrics["deliverable_imrt"] = {"deliverable_id": d_imrt.deliverable_id, "seconds": d_imrt.seconds, "flagged": d_imrt.flagged}
    return res


# ---------------------------------------------------------------------------
# mco_robust — a robust proton set on a phantom
# ---------------------------------------------------------------------------

def robust_phantom(spacing_mm: float):
    """HU and masks of the robust case's phantom on a ``spacing_mm`` grid centred at the origin: water, a cylindrical
    target (radius 15 mm, 40 mm long), an organ 5 mm behind it (radius 8 mm), and a bone slab 10 mm thick over the
    anterior field's left half. Gantry 0 enters from -y, through the slab's edge and the target toward the organ."""
    half = (60.0, 60.0, 40.0)                                        # x, y, z
    n = [int(round(2 * h / spacing_mm)) + 1 for h in half]
    origin = tuple(-h for h in half)
    z, y, x = np.meshgrid(*[origin[i] + np.arange(n[i]) * spacing_mm for i in (2, 1, 0)], indexing="ij")
    hu = np.zeros(z.shape, dtype=np.int16)
    hu[(y >= -45.0) & (y <= -35.0) & (x <= 0.0)] = 800
    target = (x ** 2 + y ** 2 <= 15.0 ** 2) & (np.abs(z) <= 20.0)
    organ = (x ** 2 + (y - 28.0) ** 2 <= 8.0 ** 2) & (np.abs(z) <= 30.0)
    return hu, origin, {"CTV": target, "OAR": organ}


def _robust_against_nominal(ops, robust_plans, robust_weights, nominal_weights, n_scenarios: int):
    """The nominal plans (indices) that meet every hard constraint of ``ops`` in every scenario, and the largest amount
    by which a converged robust plan's scenario-wise weighted sum exceeds the best of theirs, less the smoothing's slack
    (-inf when there is nothing to compare). A robust plan minimizes that sum over plans that meet the constraints in
    every scenario, so only such nominal plans are its rivals."""
    stacks = [ops.forward(np.asarray(w, float)) for w in nominal_weights]
    feasible = [k for k, st in enumerate(stacks) if all(t.violation(st) <= t.spec.tolerance_gy for t in ops.terms)]
    worst_gap = -np.inf
    for p, x in zip(robust_plans, robust_weights):
        if not p.converged or not feasible:      # an unconverged plan does not minimize its objective: nothing to compare
            continue
        raw = np.array(p.weights)

        def scenario_wise(stack):
            per = np.array([o.per_scenario(stack, m) for o, m in zip(ops.objectives, ops.masks)])   # trade-offs x scenarios
            return float((raw[:, None] * per).sum(axis=0).max())
        mine = scenario_wise(ops.forward(np.asarray(x, float)))
        best_nominal = min(scenario_wise(stacks[k]) for k in feasible)
        slack = ops.smoothing_gy * raw.sum() * np.log(n_scenarios) + 1e-3 * abs(mine)
        worst_gap = max(worst_gap, mine - best_nominal - slack)
    return feasible, worst_gap


def run_mco_robust(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.dose import EngineSpec, ScenarioSpec
    from ..models.evaluation import GoalSetSpec
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..models.mco import AutoNavigateRequest, DeliverableRequest, MCORunRequest
    from ..models.optimization import HardConstraint, ObjectiveSpec, RobustnessSpec, SolverConfig
    from ..services.beam_model import BeamModelService
    from ..services.dose_engines.mcsquare_driver import MCsquareDriver
    from ..services.geometry import GeometryService
    from ..services.mco import MCOService
    from ..services.mco_deliverable import DeliverableService
    from ..services.navigation import NavigationService
    from .phantoms import write_case

    engine = str(spec.get("engine", "mcsquare"))
    if engine == "mcsquare":
        ok, why = MCsquareDriver().availability()
        if not ok:
            raise Skip(f"MCsquare: {why}")
    _services(ctx)
    s = ctx.spacing(spec.get("spacing_mm", 2.0))
    hu, origin, masks = robust_phantom(s)
    case_dir = write_case(ctx.workdir / spec["name"], hu, s, origin, masks, spec["name"])
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=spec["name"]), data_root_override=str(case_dir),
                                                       grid_spec=GridSpec(spacing_mm=(s, s, s))))
    spot = float(spec.get("spot_spacing_mm", 5.0)) * (1.6 if ctx.fast else 1.0)
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.proton_pbs,
        beam_set=BeamSetSpec(beams=[BeamSpec(beam_id=f"G{g:g}", gantry_deg=float(g)) for g in spec.get("gantry_deg", [0.0, 90.0])]),
        delivery_params=DeliveryParams(spot_spacing_mm=spot, layer_spacing_mm=spot)))
    params = dict(spec.get("engine_params", {}))
    if ctx.fast and "nb_primaries" in params:
        params["nb_primaries"] = float(params["nb_primaries"]) / 5
    scenarios = [ScenarioSpec(**sc) for sc in spec["scenarios"]]
    rx = float(spec.get("prescription_gy", 2.0))
    base = dict(geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name=engine, params=params),
                tradeoffs=[ObjectiveSpec(**t) for t in spec["tradeoffs"]], hard_constraints=[HardConstraint(**h) for h in spec.get("hard_constraints", [])],
                solver=SolverConfig(method="L-BFGS-B", max_iterations=int(spec.get("iterations", 200)), convergence_tol=spec.get("convergence_tol")),
                plan_budget=int(spec.get("plan_budget", 7)), error_tolerance=float(spec.get("error_tolerance", 0.02)))
    msvc = MCOService()
    robust_req = MCORunRequest(**base, robustness=RobustnessSpec(enabled=True, scenarios=scenarios))
    nominal_req = MCORunRequest(**base)
    robust, nominal = msvc.run(robust_req), msvc.run(nominal_req)
    names = _names(robust)
    res.metrics["front"] = _set_checks(res, "robust set", robust, msvc.store)
    res.metrics["nominal_front"] = _set_checks(res, "nominal set", nominal, msvc.store)
    res.metrics["case"] = {"grid_mm": s, "spot_mm": spot, "spots": bm.fluence_elements.total_count, "scenarios": robust.scenarios,
                           "engine": engine, "params": params}
    res.add("robust set: scenarios", ", ".join(robust.scenarios), "nominal first", robust.scenarios[0] == "nominal")
    worse = [(p.index, i) for p in robust.plans for i, (w, n) in enumerate(zip(p.values_gy, p.nominal_gy)) if w < n - 1e-6]
    res.add("robust set: every worst case at least its nominal value", len(worse), "= 0", not worse)
    res.add("robust set: the robust gap within the error bound", robust.robust_gap, f"<= {robust.error_bound}",
            robust.robust_gap is not None and robust.robust_gap <= robust.error_bound + 1e-6,
            "the part of the bound more plans cannot remove (the scenario-wise sum against the trade-offs' own worst cases)")

    # each robust plan against every nominal plan in its own scenario-wise objective: the robust plan minimizes it over
    # the plans that meet the hard constraints in every scenario, so only nominal plans that also meet them there are
    # rivals (a nominal plan that underdoses the target in a scenario can have a lower sum; R11.8's record showed one)
    prob = msvc.optimization._assemble_problem(msvc._base(robust_req))
    ops = msvc.ops(prob, robust_req)
    w_nom = np.load(nominal.weights_uri)
    feasible, worst_gap = _robust_against_nominal(ops, robust.plans, np.load(robust.weights_uri), w_nom, len(robust.scenarios))
    res.add("nominal plans that meet the hard constraints in every scenario", f"{len(feasible)} of {len(w_nom)}", "informative", None,
            "the others underdose or overdose in some scenario, which the robust plans are built to avoid; only these are "
            "compared with the robust plans below")
    if not np.isfinite(worst_gap):
        res.add("converged robust plans protect their worst scenario better than any nominal plan", "nothing to compare", "<= 0",
                None, "no converged robust plan" if feasible else "no nominal plan meets the hard constraints in every scenario")
    else:
        res.add("converged robust plans protect their worst scenario better than any nominal plan", round(float(worst_gap), 4), "<= 0",
            bool(worst_gap <= 0.0), "max over robust plans of (its scenario-wise weighted sum − the best nominal plan's that meets "
                                    "the hard constraints in every scenario), less the smoothing's slack")
    nom_bal = next(p for p in nominal.plans if p.kind == "balance")
    rob_bal = next(p for p in robust.plans if p.kind == "balance")
    nb_worst = ops.values(ops.forward(w_nom[nom_bal.index].astype(float)))
    for i, n in enumerate(names):
        res.add(f"balance plans, {n}: robust worst case vs nominal plan's worst case (Gy)", f"{rob_bal.values_gy[i]:.3f} vs {nb_worst[i]:.3f}",
                "informative", None, f"nominal values {rob_bal.nominal_gy[i]:.3f} vs {nom_bal.values_gy[i]:.3f}")

    goals = GoalSetSpec(goals=spec["goals"])
    nav = NavigationService(msvc.store)
    state = nav.auto_navigate(robust.mco_id, AutoNavigateRequest(goals=goals, prescription_gy=rx, fractions=1, name="robust goals"))
    res.add("navigated state: worst cases within the linear bound", ", ".join(f"{v:.3f} ≤ {b:.3f}" for v, b in zip(state.values_gy, state.bound_gy)),
            "value <= bound", all(v <= b + 1e-6 for v, b in zip(state.values_gy, state.bound_gy)))
    for g in (state.goals.results if state.goals else []):
        res.add(f"navigated: {g.structure} {g.metric} {g.op} {g.value}", f"nominal {g.achieved:.3f}, worst {g.worst_case:.3f}", f"{g.op} {g.value}",
                None, "graded on the nominal dose; the worst case over the scenarios beside it")
    res.add("navigated: every goal met in every scenario", state.goals.robust_all_passed if state.goals else None, "informative", None)
    d = DeliverableService(mco_service=msvc).run(robust.mco_id, DeliverableRequest(state_id=state.state_id, goals=goals, prescription_gy=rx,
                                                                                           tolerance_gy=0.02 * rx))
    _deviation_checks(res, "deliverable (spots)", d)
    res.metrics["deliverable"] = {"deliverable_id": d.deliverable_id, "projected": d.projected, "flagged": d.flagged, "notes": d.notes}
    return res


KINDS_R11 = {"mco_front": run_mco_front, "mco_protocol": run_mco_protocol, "mco_robust": run_mco_robust}

__all__ = ["KINDS_R11", "run_mco_front", "run_mco_protocol", "run_mco_robust", "robust_phantom"]
