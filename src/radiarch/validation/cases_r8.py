"""Validation cases of roadmap R8: the native photon pencil-beam engine against the Monte Carlo
references and against the collapsed cone, and lung SBRT VMAT plans on public CT data.

``run.py`` registers :data:`KINDS_R8`; the cases are YAML files in ``cases/`` like the others.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from . import phantoms as ph
from .cases_r7 import (
    NORMALISATION_HEADROOM, OAR_WEIGHT, _cax3, _cached_ccc_dose, _dose_at, _goal_met, _mc_reference, _normalise_to_goal,
    _objectives, _phantom_for, _read_volume, _resample_to, _services, _structure_extent_mm, _write_volume, _case_dir_with_gtv,
)
from .common import CaseResult, Context, Skip, _ccc_engine, _open_field_plan, _within, data_root


def _pb_engine():
    from ..services.dose_engines.pb import PencilBeamEngine
    eng = PencilBeamEngine()
    ok, reason = eng.availability()
    if not ok:
        raise Skip(reason)
    return eng


def _penumbra(prof: np.ndarray, x: np.ndarray) -> float:
    right = x >= 0
    order = np.argsort(prof[right])
    return float(np.interp(0.2, prof[right][order], x[right][order]) - np.interp(0.8, prof[right][order], x[right][order]))


# ---------------------------------------------------------------------------
# pb_vs_mc — the pencil-beam engine against the OpenGATE references
# ---------------------------------------------------------------------------

def run_pb_vs_mc(spec: dict, ctx: Context) -> CaseResult:
    """As ``photon_vs_mc`` for CCC: water depth dose, profile, out-of-field dose and gamma normalised at 10 cm;
    lung and bone slabs as heterogeneity correction factors (slab over water at the same depth). The pencil-beam
    engine's lateral kernel scaling (1.1.0) was fitted to the lung slabs, so their factors are a consistency check."""
    res = CaseResult(spec["name"], spec["kind"])
    from ..services.gamma import gamma_index

    eng = _pb_engine()
    tol = spec.get("tolerances", {})
    crit = spec.get("gamma", {"dose_percent": 3.0, "dta_mm": 3.0, "threshold_percent": 10.0, "pass_percent": 95.0})
    cases = [c for c in spec["cases"] if _mc_reference(c) is not None]
    if not cases:
        raise Skip("no Monte Carlo reference: run `python -m radiarch.validation.mc_reference --case <name>`")
    params = dict(spec.get("params", {}))
    water: Dict[str, np.ndarray] = {}
    for case in sorted(cases, key=lambda c: not c.startswith("water")):
        ref = _mc_reference(case)
        s = ctx.spacing(ref["spacing_mm"][0])
        phantom = _phantom_for(case, s)
        field = float(ref["provenance"].get("field_mm", 100.0))
        plan = _open_field_plan(field, spec.get("leaf_width_mm", 10.0), spec.get("beamlet_mm", 10.0))
        pb = eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params={**params, "fluence": "apertures"})
        mc = _resample_to(ref["dose"], ref["spacing_mm"], ref["origin_mm"], phantom)
        cz, cx = phantom.centre_index("z"), phantom.centre_index("x")
        y = phantom.axis_mm("y")
        j10 = phantom.depth_index(100.0)
        cax_p, cax_m = _cax3(pb, phantom), _cax3(mc, phantom)
        res.metrics[f"{case}_cax"] = {"depth_mm": y.tolist(), "pb_gy_per_mu": cax_p.tolist(), "mc_gy_per_primary": cax_m.tolist()}
        if case.startswith("water"):
            water = {"pb": cax_p, "mc": cax_m}
            t = float(tol.get("in_field_percent", 2.0))
            n_p, n_m = cax_p / cax_p[j10], cax_m / cax_m[j10]
            kp, km = int(np.argmax(n_p)), int(np.argmax(n_m))
            pdd_p, pdd_m = 100.0 / n_p[kp], 100.0 / n_m[km]
            res.add(f"{case}: PDD10 pb vs MC (%)", pdd_p, f"{pdd_m:.1f} ± {t} (MC)", abs(pdd_p - pdd_m) <= t, "MPPG 5.a basic photon, in field")
            res.add(f"{case}: d_max pb vs MC (mm)", float(y[kp]), f"{y[km]:.1f} (MC)", None, "informative: the kernel's build-up against the phantom's")
            for depth in (50.0, 150.0, 200.0, 250.0):
                j = phantom.depth_index(depth)
                r = float(n_p[j] / n_m[j])
                res.add(f"{case}: CAX dose at {depth:g} mm, pb / MC", r, f"1 ± {t / 100:.2f}", _within(r, 1.0, t / 100), "normalised at 10 cm")
            x = phantom.axis_mm("x")
            pp = pb[cz, j10, :] / pb[cz, j10, cx]
            pm = mc[cz - 1:cz + 2, j10 - 1:j10 + 2, :].mean(axis=(0, 1)); pm = pm / pm[cx]
            pen_p, pen_m = _penumbra(pp, x), _penumbra(pm, x)
            res.add(f"{case}: penumbra 80-20 % at 10 cm, pb (mm)", pen_p, f"{pen_m:.1f} ± {max(2.0, s):g} (MC)", abs(pen_p - pen_m) <= max(2.0, s),
                    "the engine's fluence penumbra (penumbra_fwhm_mm) was fitted to this reference: a consistency check, not an independent one")
            oar = 0.4 * field
            op_, om = float(np.interp(oar, x, pp)), float(np.interp(oar, x, pm))
            res.add(f"{case}: off-axis ratio at {oar:g} mm, 10 cm depth", op_, f"{om:.3f} ± 0.03 (MC)", abs(op_ - om) <= 0.03, "in-field profile")
            out = 0.5 * field * 1.1 + 20.0
            o_p, o_m = float(np.interp(out, x, pp)), float(np.interp(out, x, pm))
            res.add(f"{case}: dose 2 cm outside the field edge at 10 cm (% of CAX)", round(o_p * 100, 2), f"{o_m * 100:.2f} ± 1 (MC)",
                    abs(o_p - o_m) <= 0.01, "the 200 mm kernel's scatter tail against Monte Carlo (CCC's Dij stops at ~2 cm)")
            g = gamma_index(pb / pb[cz, j10, cx], mc / float(cax_m[j10]), spacing_mm=phantom.spacing_mm[::-1], dose_percent=crit["dose_percent"],
                            distance_mm=crit["dta_mm"], threshold_pct=crit["threshold_percent"], local=False)
            res.add(f"{case}: gamma {crit['dose_percent']:g} %/{crit['dta_mm']:g} mm pass rate (%)", float(g.pass_rate_pct), f"≥ {crit['pass_percent']}",
                    float(g.pass_rate_pct) >= float(crit["pass_percent"]), "MPPG 5.b / TG-218 criteria, normalised at 10 cm depth on the axis")
        else:
            if not water:
                res.notes.append(f"{case}: no water reference; correction factors skipped"); continue
            t = float(tol.get("heterogeneity_percent", 3.0))
            depths = spec.get("probe_depths_mm", {})
            lung = case.startswith("lung")
            for depth in (depths.get(case, [20, 50, 80, 150, 200, 250]) if isinstance(depths, dict) else depths):
                j = phantom.depth_index(depth)
                cf_p = float(cax_p[j] / water["pb"][j]); cf_m = float(cax_m[j] / water["mc"][j])
                res.metrics[f"{case}_cf_{depth:g}mm"] = {"pb": cf_p, "mc": cf_m}
                ok = abs(cf_p - cf_m) <= t / 100 * cf_m
                res.add(f"{case}: correction factor at {depth:g} mm, pb vs MC", round(cf_p, 4), f"{cf_m:.3f} ± {t / 100 * cf_m:.3f} (MC)", ok,
                        "slab dose / water dose at the same depth; MPPG 5.a / TECDOC-1583 heterogeneity 3 %"
                        + ("; the lateral kernel scaling was fitted to this slab and the 2 x 2 cm one: a consistency check" if lung else ""))
        res.notes.append(f"{case}: MC {ref['primaries']:.2e} primaries")
    _field_size_checks(res, eng, spec, ctx)
    _narrow_lung_checks(res, eng, spec, ctx)
    k = eng.kernel()
    res.notes.append(f"pb kernel {k.fingerprint} from {k.meta.get('source', {}).get('file', '?')} "
                     f"({k.meta.get('source', {}).get('primaries', 0):.1e} primaries); the same Mohan 6 MV spectrum as the references")
    return res


def _cone_solid_angle(field_mm: float) -> float:
    """The solid angle the Monte Carlo source fills for a field (mc_reference.build: uniform within this cone)."""
    import math
    theta = math.radians(math.degrees(math.atan(0.75 * field_mm / 1000.0)) + 0.5)
    return 2.0 * math.pi * (1.0 - math.cos(theta))


def _field_size_checks(res: CaseResult, eng, spec: dict, ctx: Context) -> None:
    """Dose on the axis at 10 cm per unit primary fluence, 4 x 4 and 20 x 20 over 10 x 10 cm: the Monte Carlo
    against the pencil beam (graded) and CCC (reported). The Monte Carlo emits uniformly in solid angle within a
    cone that depends on the field, so its dose per primary is scaled by that cone's solid angle; there is no
    head, so this is phantom scatter (and collimator scatter) only."""
    fields = {c: _mc_reference(c) for c in ("water_4x4", "water_10x10", "water_20x20")}
    if fields["water_10x10"] is None or not any(fields[c] is not None for c in ("water_4x4", "water_20x20")):
        res.notes.append("field-size checks need the water_4x4 / water_20x20 Monte Carlo references")
        return
    tol = float(spec.get("tolerances", {}).get("field_size_percent", 2.0))
    try:
        ccc_eng = _ccc_engine()
    except Skip:
        ccc_eng = None
    vals: Dict[str, Dict[str, float]] = {}
    for case, ref in fields.items():
        if ref is None:
            continue
        s = ctx.spacing(ref["spacing_mm"][0])
        phantom = _phantom_for(case, s)
        field = float(ref["provenance"].get("field_mm", 100.0))
        plan = _open_field_plan(field, spec.get("leaf_width_mm", 10.0), spec.get("beamlet_mm", 10.0))
        j10 = phantom.depth_index(100.0)
        mc = _resample_to(ref["dose"], ref["spacing_mm"], ref["origin_mm"], phantom)
        pb = eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params={"fluence": "apertures"})
        vals[case] = {"mc": float(_cax3(mc, phantom)[j10]) * _cone_solid_angle(field), "pb": float(_cax3(pb, phantom)[j10])}
        if ccc_eng is not None:
            params = {"n_jobs": int(spec.get("n_jobs", 16))}
            if ctx.fast:
                params["calibration_spacing_mm"] = 5.0
            ccc = _cached_ccc_dose(ccc_eng, phantom, plan, params, key=f"field-size-{case}-{s:g}mm-{spec.get('beamlet_mm', 10.0)}")
            vals[case]["ccc"] = float(_cax3(ccc, phantom)[j10])
    ref10 = vals["water_10x10"]
    for case in ("water_4x4", "water_20x20"):
        if case not in vals:
            continue
        r = {k: vals[case][k] / ref10[k] for k in vals[case]}
        label = case.split("_")[1]
        res.add(f"{label} over 10x10, dose at 10 cm, pb vs MC", round(r["pb"], 4), f"{r['mc']:.3f} ± {tol / 100 * r['mc']:.3f} (MC)",
                abs(r["pb"] - r["mc"]) <= tol / 100 * r["mc"], "phantom scatter: the MC dose per primary scaled by its source cone's solid angle")
        if "ccc" in r:
            res.add(f"{label} over 10x10, dose at 10 cm, CCC vs MC", round(r["ccc"], 4), f"{r['mc']:.3f} (MC)", None,
                    "informative: CCC's shipped scatter cut-off (R8 finding)")
    res.metrics["field_size_dose_at_10cm"] = vals


def _narrow_lung_checks(res: CaseResult, eng, spec: dict, ctx: Context) -> None:
    """A 2 x 2 cm field through the lung slab (3–11 cm deep): the dose on the axis at depths in and beyond the
    lung over the dose at 2 cm in the water above it, for Monte Carlo, the pencil beam and CCC. Lateral
    electronic disequilibrium lowers the dose inside the lung for narrow fields; a pencil beam scaled in depth only
    misses it (25 % high), the pencil beam's lateral kernel scaling (1.1.0) follows it. Graded for the pencil beam
    against the heterogeneity tolerance (a consistency check: the scaling was fitted to this reference and the 10 x 10
    cm slab); CCC is reported."""
    ref = _mc_reference("lung_slab_2x2")
    if ref is None:
        res.notes.append("the narrow-field lung check needs the lung_slab_2x2 Monte Carlo reference")
        return
    s = ctx.spacing(ref["spacing_mm"][0])
    phantom = _phantom_for("lung_slab_2x2", s)
    field = float(ref["provenance"].get("field_mm", 20.0))
    beamlet = float(spec.get("narrow_beamlet_mm", 5.0))
    plan = _open_field_plan(field, spec.get("leaf_width_mm", 10.0), beamlet)
    doses = {"mc": _resample_to(ref["dose"], ref["spacing_mm"], ref["origin_mm"], phantom),
             "pb": eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params={"fluence": "apertures"})}
    try:
        params = {"n_jobs": int(spec.get("n_jobs", 16))}
        if ctx.fast:
            params["calibration_spacing_mm"] = 5.0
        doses["ccc"] = _cached_ccc_dose(_ccc_engine(), phantom, plan, params, key=f"narrow-lung-{s:g}mm-{beamlet:g}")
    except Skip:
        pass
    t = float(spec.get("tolerances", {}).get("heterogeneity_percent", 3.0)) / 100.0
    j0 = phantom.depth_index(20.0)
    cax = {k: _cax3(d, phantom) for k, d in doses.items()}
    vals: Dict[str, Dict[str, float]] = {}
    for depth in spec.get("narrow_lung_depths_mm", [50, 80, 100, 150]):
        j = phantom.depth_index(float(depth))
        v = {k: float(c[j] / c[j0]) for k, c in cax.items()}
        vals[f"{depth:g}"] = v
        where = "in the lung" if 30.0 < depth < 110.0 else "beyond the lung"
        r_pb = v["pb"] / v["mc"]
        res.add(f"2x2 in lung: dose at {depth:g} mm ({where}) over 20 mm, pb / MC", round(r_pb, 3), f"1 ± {t:.2f}", _within(r_pb, 1.0, t),
                f"MC {v['mc']:.3f}; lateral electronic disequilibrium of a narrow field in lung; the lateral scaling was fitted to it")
        if "ccc" in v:
            res.add(f"2x2 in lung: dose at {depth:g} mm ({where}) over 20 mm, ccc / MC", round(v["ccc"] / v["mc"], 3), "informative", None,
                    f"MC {v['mc']:.3f}; CCC's shipped scatter cut-off")
    res.metrics["narrow_lung_relative_dose"] = vals
    res.notes.append(f"lung_slab_2x2: MC {ref['primaries']:.2e} primaries; {beamlet:g} mm beamlets for CCC")


# ---------------------------------------------------------------------------
# pb_vs_ccc — the two photon engines against each other
# ---------------------------------------------------------------------------

def run_pb_vs_ccc(spec: dict, ctx: Context) -> CaseResult:
    """The cross-engine check of the roadmap. Water, 10 x 10 cm, absolute dose (both calibrated to 1 cGy per MU
    at d_max): gamma 3 %/3 mm. The beamlet-size dependence of both engines (CCC's shipped scatter cut-off
    against the pencil beam's full kernel). A lateral beam onto an off-centre isocenter, gantry 90 and 270:
    the two engines agree on which side the beam enters (IEC 61217)."""
    res = CaseResult(spec["name"], spec["kind"])
    from ..services.gamma import gamma_index

    pb_eng = _pb_engine()
    ccc_eng = _ccc_engine()
    crit = spec.get("gamma", {"dose_percent": 3.0, "dta_mm": 3.0, "threshold_percent": 10.0, "pass_percent": 95.0})
    ccc_params = {"n_jobs": int(spec.get("n_jobs", 8))}
    if ctx.fast:
        ccc_params["calibration_spacing_mm"] = 5.0
    s = ctx.spacing(spec.get("spacing_mm", 2.5))
    phantom = ph.water_box(150.0, 300.0, s)
    cz, cx = phantom.centre_index("z"), phantom.centre_index("x")
    y = phantom.axis_mm("y")
    j10 = phantom.depth_index(100.0)
    pdd: Dict[str, Dict[float, float]] = {"ccc": {}, "pb": {}}
    for beamlet in spec.get("beamlets_mm", [5.0, 10.0]):
        plan = _open_field_plan(100.0, 10.0, float(beamlet))
        ccc = _cached_ccc_dose(ccc_eng, phantom, plan, ccc_params, key=f"pb_vs_ccc-water-{s:g}mm-{beamlet:g}")
        pb = pb_eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, weights=plan.beamlet_mu())
        for name, d in (("ccc", ccc), ("pb", pb)):
            cax = d[cz, :, cx]
            pdd[name][beamlet] = float(cax[j10] / cax.max() * 100.0)
        res.metrics[f"water_{beamlet:g}mm"] = {"depth_mm": y.tolist(), "ccc": ccc[cz, :, cx].tolist(), "pb": pb[cz, :, cx].tolist()}
        g = gamma_index(pb, ccc, spacing_mm=phantom.spacing_mm[::-1], dose_percent=crit["dose_percent"], distance_mm=crit["dta_mm"],
                        threshold_pct=crit["threshold_percent"], local=False)
        graded = float(beamlet) == float(spec.get("graded_beamlet_mm", 10.0))
        res.add(f"water 10 x 10, {beamlet:g} mm beamlets: gamma {crit['dose_percent']:g} %/{crit['dta_mm']:g} mm pb vs CCC, absolute (%)",
                float(g.pass_rate_pct), f"≥ {crit['pass_percent']}", float(g.pass_rate_pct) >= float(crit["pass_percent"]) if graded else None,
                "both engines calibrated to 1 cGy/MU at d_max of this field" + ("" if graded else "; informative: CCC's shipped scatter cut-off depends on the beamlet size"))
    b = sorted(pdd["pb"])
    if len(b) >= 2:
        dp = abs(pdd["pb"][b[0]] - pdd["pb"][b[-1]])
        dc = abs(pdd["ccc"][b[0]] - pdd["ccc"][b[-1]])
        res.add(f"pb PDD10 change from {b[0]:g} to {b[-1]:g} mm beamlets (points)", round(dp, 2), "≤ 0.5", dp <= 0.5,
                "a pencil-beam dose does not depend on how the field is cut into beamlets")
        res.add(f"CCC PDD10 change from {b[0]:g} to {b[-1]:g} mm beamlets (points)", round(dc, 2), "informative", None,
                "R8 finding: the shipped scatter cut-off (~2 cm from each beamlet) loses more scatter from smaller beamlets; "
                "R7 validated CCC with 10 mm beamlets")
        res.metrics["pdd10"] = {k: {str(kk): vv for kk, vv in v.items()} for k, v in pdd.items()}
    # field size: dose on the axis at 10 cm, 4 x 4 and 6 x 6 against 10 x 10 (the phantom-scatter dependence)
    from ..services.photon_beamlets import build_photon_plan
    at10: Dict[str, Dict[float, float]] = {"ccc": {}, "pb": {}}
    for field in (40.0, 60.0, 100.0):
        h = field / 2
        plan = build_photon_plan([(0.0, 0.0)], (-h, h), (-h, h), 10.0, 1.0, (10.0, 10.0))
        for name, d in (("ccc", _cached_ccc_dose(ccc_eng, phantom, plan, ccc_params, key=f"pb_vs_ccc-field-{s:g}mm-{field:g}")),
                        ("pb", pb_eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, weights=plan.beamlet_mu()))):
            at10[name][field] = float(d[cz, j10, cx])
    for field in (40.0, 60.0):
        rc, rp = at10["ccc"][field] / at10["ccc"][100.0], at10["pb"][field] / at10["pb"][100.0]
        res.add(f"dose at 10 cm, {field / 10:g} x {field / 10:g} over 10 x 10: CCC / pb", round(rc, 3), f"{rp:.3f} (pb)", None,
                "informative until the 4 x 4 Monte Carlo reference grades it (pb_vs_mc); R8 finding: CCC's shipped scatter cut-off "
                "barely changes the central dose with field size")
    res.metrics["dose_at_10cm_gy_per_mu"] = {k: {str(kk): vv for kk, vv in v.items()} for k, v in at10.items()}
    # lateral beams onto an off-centre isocenter: gantry 90 enters 90 mm from it, gantry 270 210 mm; the ratio of the
    # two doses there depends on the side the beam enters, not on either engine's absolute output
    iso = (60.0, 100.0, 0.0)
    ii = (cz, phantom.depth_index(iso[1]), int(round((iso[0] - phantom.origin_mm[0]) / s)))
    lat: Dict[str, Dict[float, float]] = {"ccc": {}, "pb": {}}
    for gantry in (90.0, 270.0):
        plan = build_photon_plan([(gantry, 0.0)], (-30.0, 30.0), (-30.0, 30.0), 10.0, 1.0, (10.0, 10.0), isocenter_mm=iso)
        lat["ccc"][gantry] = float(_cached_ccc_dose(ccc_eng, phantom, plan, ccc_params, key=f"pb_vs_ccc-lateral-{s:g}mm-{gantry:g}-iec")[ii])
        lat["pb"][gantry] = float(pb_eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, weights=plan.beamlet_mu())[ii])
    rc, rp = lat["ccc"][90.0] / lat["ccc"][270.0], lat["pb"][90.0] / lat["pb"][270.0]
    res.add("isocenter 60 mm toward +x: dose(gantry 90) / dose(gantry 270), CCC", round(rc, 3), f"{rp:.3f} ± 5 % (pb), > 1", rp > 1.2 and _within(rc / rp, 1.0, 0.05),
            "IEC 61217: gantry 90 enters from +x (patient left), close to this isocenter; before R8 CCC turned the gantry the other way (ratio < 1)")
    res.metrics["lateral_dose_at_isocenter_gy_per_mu"] = {k: {str(kk): vv for kk, vv in v.items()} for k, v in lat.items()}
    return res


# ---------------------------------------------------------------------------
# lung_sbrt_vmat — lung SBRT with VMAT arcs on LCTSC
# ---------------------------------------------------------------------------

def _peripheral_gtv_centre(lung_zyx: np.ndarray, origin: Sequence[float], s: float, radius_mm: float, side: str = "right"):
    """A point in the lung at least ``radius + 5`` mm from its edge, as lateral as possible near the lung's
    middle slice: a peripheral tumour. Returns ``(x, y, z)`` in mm."""
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(lung_zyx, sampling=(s, s, s))
    idx = np.argwhere(lung_zyx)
    zc = idx[:, 0].mean()
    ok = (dist >= radius_mm + 5.0)
    ok[: max(0, int(zc - 30 / s))] = False
    ok[int(zc + 30 / s) + 1:] = False
    cand = np.argwhere(ok)
    if cand.size == 0:
        raise Skip("the lung is too small for the GTV")
    k = int(np.argmin(cand[:, 2])) if side == "right" else int(np.argmax(cand[:, 2]))   # LPS: patient right is -x
    z, yv, x = cand[k]
    return (origin[0] + x * s, origin[1] + yv * s, origin[2] + z * s)


def _plan_vmat(geo, arrays, target: str, rx: float, goals: List[dict], extra: list, arcs, beamlet: float, iterations: int, rounds: int,
               fractions: int, spec: dict) -> dict:
    """Sector beams around every target (the field covers them from every angle of the arcs), fluence optimization
    with the pb Dij and goal-driven reweighting rounds, then arcs (VMAT service); the arc dose normalised so the
    main target's D95 meets its prescription. Returns bm, opt, vm, dose, k, history, objectives."""
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.dose import EngineSpec
    from ..models.optimization import OptimizationRunRequest, SolverConfig
    from ..models.vmat import ArcRequest, sector_beams
    from ..services.beam_model import BeamModelService
    from ..services.dose import DoseService
    from ..services.optimization import OptimizationService
    from ..services.vmat import VMATService

    target_mask = arrays.mask_zyx(arrays.structure_index[target])
    union = np.zeros(arrays.shape_zyx, bool)
    for t in {target} | {g["structure"] for g in goals if g["op"].startswith(">")}:
        union |= arrays.mask_zyx(arrays.structure_index[t])
    lo, hi = _structure_extent_mm(union, arrays.origin_mm, arrays.spacing_mm)
    iso = tuple(float(v) for v in (lo + hi) / 2.0)
    margin = float(spec.get("jaw_margin_mm", 10.0))
    jaw_x = float(np.hypot(hi[0] - lo[0], hi[1] - lo[1]) + 2 * margin)
    jaw_y = float(hi[2] - lo[2] + 2 * margin)
    machine = spec.get("machine", "synthetic-120")
    engine = EngineSpec(name="pb", params=dict(spec.get("pb_params", {})))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id=machine,
        beam_set=BeamSetSpec(isocenter_mm=iso, beams=[BeamSpec(beam_id=b, gantry_deg=g, couch_deg=c, collimator_deg=col)
                                                      for b, g, c, col in sector_beams(arcs)]),
        delivery_params=DeliveryParams(jaw_opening_mm=(jaw_x, jaw_y), beamlet_size_mm=(beamlet, beamlet))))
    masks = {g["structure"]: arrays.mask_zyx(arrays.structure_index[g["structure"]]) for g in goals if g["structure"] in arrays.structure_index}
    targets = {g["structure"] for g in goals if g["op"].startswith(">")}
    scale: Dict[int, float] = {}
    level: Dict[int, float] = {}
    init = None
    history: List[dict] = []
    objectives: list = []
    opt = None
    for r in range(max(1, rounds)):
        objectives = _objectives(arrays, target, rx, goals, scale, level) + list(extra)
        opt = OptimizationService().run(OptimizationRunRequest(
            geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=engine,
            objectives=objectives, solver=SolverConfig(method="L-BFGS-B", max_iterations=iterations), init_weights_uri=init))
        fmo = _read_volume(opt.dose_ref_uri)
        dose, k = _normalise_to_goal(fmo, fmo[target_mask], "D95", rx * NORMALISATION_HEADROOM)
        failed = [i for i, g in enumerate(goals) if g["structure"] in masks and not _goal_met(dose[masks[g["structure"]]], g)]
        history.append({"round": r + 1, "normalisation": k, "failed": [f"{goals[i]['structure']} {goals[i]['metric']}" for i in failed]})
        if not failed:
            break
        for i in failed:
            scale[i] = scale.get(i, 1.0) * 3.0
            if goals[i]["structure"] not in targets:
                level[i] = level.get(i, 1.0) * 0.9
        init = opt.weights_ref_uri
    # arcs: the sector fluence swept by the leaves, control-point doses recomputed, metersets re-optimized; the arcs
    # reproduce the sector fluence only approximately, so the same goal-driven rounds run on the arc metersets
    vm = arc_dose = None
    k = 1.0
    for r in range(max(1, int(spec.get("arc_rounds", 3)))):
        vm = VMATService().arcs(opt.optimization_id, ArcRequest(objectives=objectives, arcs=arcs, max_iterations=iterations, fractions=fractions,
                                                                machine_model_id=machine, dose_engine=engine))
        raw = _read_volume(DoseService().dose_store.get_by_id(vm.dose_id).dose_grid_uri)
        arc_dose, k = _normalise_to_goal(raw, raw[target_mask], "D95", rx * NORMALISATION_HEADROOM)
        failed = [i for i, g in enumerate(goals) if g["structure"] in masks and not _goal_met(arc_dose[masks[g["structure"]]], g)]
        history.append({"arc_round": r + 1, "normalisation": k, "failed": [f"{goals[i]['structure']} {goals[i]['metric']}" for i in failed]})
        if not failed:
            break
        for i in failed:
            scale[i] = scale.get(i, 1.0) * 3.0
            if goals[i]["structure"] not in targets:
                level[i] = level.get(i, 1.0) * 0.95
        objectives = _objectives(arrays, target, rx, goals, scale, level) + list(extra)
    return {"bm": bm, "opt": opt, "vm": vm, "dose": arc_dose, "k": k, "history": history, "objectives": objectives}


def run_lung_sbrt_vmat(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.evaluation import EvaluationRequest, GoalSetSpec
    from ..models.geometry import GeometryBuildRequest, GeometryDeriveRequest, GridSpec, PatientRef, StructureOperation
    from ..models.optimization import ObjectiveSpec
    from ..models.vmat import ArcSpec
    from ..services.beam_model import BeamModelService
    from ..services.dose import DoseService
    from ..services.evaluation import EvaluationService
    from ..services.geometry import GeometryService
    from ..services.geometry_bundle import load_geometry_arrays
    from ..services.sbrt import sbrt_indices

    _pb_engine()
    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    beamlet = float(spec.get("beamlet_mm", 5.0)) * (2.0 if ctx.fast else 1.0)
    iterations = int(spec.get("iterations", 150) / (2 if ctx.fast else 1))
    rounds = int(spec.get("rounds", 3)) if not ctx.fast else 1
    rx = float(spec.get("prescription_gy", 54.0)); fractions = int(spec.get("fractions", 3))
    template = spec.get("goal_template", "sbrt-lung-54gy-3fx")
    arcs = [ArcSpec(**a) for a in spec["arcs"]]
    if ctx.fast:
        arcs = [a.model_copy(update={"sectors": max(4, a.sectors // 2)}) for a in arcs]
    radius = float(spec.get("gtv_radius_mm", 12.0))
    for pid in patients:
        pdir = root / pid
        ct_files = sorted(next(pdir.glob("CT_*")).glob("*.dcm"))
        rs_files = list(pdir.glob("RTSTRUCT_*/*.dcm"))
        if not ct_files or not rs_files:
            res.notes.append(f"{pid}: CT or RTSTRUCT missing"); continue
        geo0 = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"sbrt-{pid}-base"), data_root_override=str(pdir),
                                                            grid_spec=GridSpec(spacing_mm=(s, s, s))))
        arr0 = load_geometry_arrays(geo0)
        lung_name = next((n for n in arr0.structure_index if n.lower() in ("lung_r", "lung_right")), None)
        if lung_name is None:
            res.notes.append(f"{pid}: no right lung"); continue
        lung = arr0.mask_zyx(arr0.structure_index[lung_name])
        if spec.get("gtv_position", "peripheral") == "centroid":      # the conventional case: the right lung's centroid, as lung_e2e
            com = np.argwhere(lung).mean(axis=0)
            centre = tuple(float(arr0.origin_mm[i] + com[2 - i] * s) for i in range(3))
        else:
            centre = _peripheral_gtv_centre(lung, arr0.origin_mm, s, radius)
        tag = f"{spec['name']}-{pid}"
        case_dir = _case_dir_with_gtv(ctx, tag, ct_files, rs_files, centre, radius, "synthetic GTV for the validation harness")
        geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=tag), data_root_override=str(case_dir),
                                                           grid_spec=GridSpec(spacing_mm=(s, s, s))))
        ctv_mm, ptv_mm = float(spec.get("ctv_margin_mm", 0.0)), float(spec.get("ptv_margin_mm", 5.0))
        target_ops = ([StructureOperation(op="expand", name="CTV", source="GTV", margin_mm=ctv_mm),
                       StructureOperation(op="expand", name="PTV", source="CTV", margin_mm=ptv_mm)] if ctv_mm > 0
                      else [StructureOperation(op="expand", name="PTV", source="GTV", margin_mm=ptv_mm)])
        geo = GeometryService().derive(geo.geometry_id, GeometryDeriveRequest(operations=target_ops + [
            StructureOperation(op="ring", name="RingNear", source="PTV", inner_mm=3.0, outer_mm=12.0),
            # from 2 cm to ring_far_outer_mm: D2cm is the maximum anywhere in the body beyond 2 cm, so the far ring reaches the
            # skin, where heavily weighted narrow beamlets would otherwise put their entrance dose unchecked
            StructureOperation(op="ring", name="RingFar", source="PTV", inner_mm=20.0, outer_mm=float(spec.get("ring_far_outer_mm", 45.0))),
            StructureOperation(op="union", name="Lungs", sources=["Lung_L", "Lung_R"]),
            StructureOperation(op="subtract", name="Lungs-GTV", source="Lungs", sources=["GTV"]),
            StructureOperation(op="subtract", name="Lungs-PTV", source="Lungs", sources=["PTV"])]))
        arrays = load_geometry_arrays(geo)
        ptv_mask = arrays.mask_zyx(arrays.structure_index["PTV"])
        # the planning goals: coverage, and organ limits (Dmax shorthand or [metric, Gy])
        goals = [{"structure": "PTV", "metric": "D95", "op": ">=", "gy": rx}]
        for st, lim in spec.get("organ_limits", {}).items():
            if st in arrays.structure_index:
                goals.append({"structure": st, "metric": "Dmax", "op": "<=", "gy": float(lim)})
        for st, (metric, lim) in spec.get("organ_goals", {}).items():
            if st in arrays.structure_index:
                goals.append({"structure": st, "metric": metric, "op": "<=", "gy": float(lim), "dmax_term": not st.startswith("Lungs")})
        extra = [ObjectiveSpec(type="DMax", structure_name="RingNear", dose_gy=float(spec.get("ring_near_fraction", 0.85)) * rx, weight=OAR_WEIGHT / 2),
                 ObjectiveSpec(type="DMax", structure_name="RingFar", dose_gy=float(spec.get("ring_far_fraction", 0.4)) * rx, weight=OAR_WEIGHT)]
        plan_out = _plan_vmat(geo, arrays, "PTV", rx, goals, extra, arcs, beamlet, iterations, rounds, fractions, spec)
        bm, opt, vm, arc_dose, k, history = (plan_out[x] for x in ("bm", "opt", "vm", "dose", "k", "history"))
        dose_uri = _write_volume(ctx, f"{tag}-vmat", arc_dose, arrays)
        ev = EvaluationService().run(EvaluationRequest(dose_ref_uri=dose_uri, geometry_id=geo.geometry_id, prescription_gy=rx, target_structure="PTV",
                                                       fractions=fractions, goals=GoalSetSpec(template_id=template)))
        for g in (ev.goals.results if ev.goals else []):
            if g.passed is None:
                continue
            res.add(f"{pid}: {g.structure} {g.metric} {g.op} {g.value}", round(float(g.achieved), 2) if g.achieved is not None else None,
                    f"{g.op} {g.value}", bool(g.passed) if int(g.priority) == 1 else None,
                    f"{template} priority {g.priority}" + ("" if int(g.priority) == 1 else " (informative)"))
        body = arrays.ct_hu > -500
        lungs = arrays.mask_zyx(arrays.structure_index["Lungs-GTV"])
        ind = None
        if spec.get("sbrt_indices", True):
            ind = sbrt_indices(arc_dose, ptv_mask, body, rx, arrays.spacing_mm, lungs_zyx=lungs)
            for key, value, lim in (("R100", ind.r100, ind.limits["R100"]), ("R50", ind.r50, ind.limits["R50"]),
                                    ("D2cm", ind.d2cm_pct, ind.limits["D2cm"]), ("LungV20", ind.lung_v20_pct, ind.limits["LungV20"])):
                if value is None:
                    continue
                res.add(f"{pid}: {key} (PTV {ind.ptv_cc:.1f} cc)", round(float(value), 3), f"< {lim[0]:g} (minor ≤ {lim[1]:g})",
                        ind.deviations[key] != "major", f"RTOG 0813/0915 conformality table: {ind.deviations[key]} deviation")
        else:
            ptv = arc_dose[ptv_mask]
            res.add(f"{pid}: PTV D5 / D95 (homogeneity)", round(_dose_at(ptv, 5.0) / _dose_at(ptv, 95.0), 3), "≤ 1.15 (informative)", None,
                    f"normalised by {k:.3f} so that PTV D95 = {rx * NORMALISATION_HEADROOM:.2f} Gy")
            if ev.indices is not None:
                res.add(f"{pid}: Paddick conformity index", round(float(ev.indices.conformity_index), 3), "informative", None, "1 is ideal")
        rep = vm.arcs[0]
        res.add(f"{pid}: arcs deliverable at the machine's limits", vm.deliverable, "True", vm.deliverable,
                f"per fraction: {vm.n_control_points} control points, {rep.total_mu * k:.0f} MU after normalisation, "
                f"{sum(a.delivery_time_s for a in vm.arcs):.0f} s before it, gantry {rep.gantry_speed_deg_s[0]:.2f}-{rep.gantry_speed_deg_s[1]:.1f} deg/s")
        res.metrics[pid] = {"gtv_centre_mm": [round(float(v), 1) for v in centre], "gtv_radius_mm": radius, "rounds": history,
                            "normalisation_factor": k, "sbrt": ind.to_dict() if ind else None, "vmat": vm.model_dump(mode="json"),
                            "geometry_id": geo.geometry_id, "optimization_id": opt.optimization_id, "vmat_id": vm.vmat_id,
                            "beamlets": bm.fluence_elements.total_count}
        # the independent second engine: CCC recomputes the delivered arcs
        if spec.get("second_engine") and not ctx.fast:
            from ..services.dose_engines.ccc import CCCEngine
            from ..services.gamma import gamma_index
            plan = BeamModelService().store.load_plan(vm.beam_model_id)
            gb = DoseService()._load_geometry(geo.geometry_id)
            ccc = CCCEngine().compute_delivered_dose(gb.density, gb.spacing_mm, arrays.origin_mm, plan,
                                                     params={"n_jobs": int(spec.get("n_jobs", 16))}) * k
            g = gamma_index(ccc, arc_dose, spacing_mm=tuple(arrays.spacing_mm)[::-1], dose_percent=3.0, distance_mm=3.0, threshold_pct=10.0)
            d95c, d95p = _dose_at(ccc[ptv_mask], 95.0), _dose_at(arc_dose[ptv_mask], 95.0)
            res.add(f"{pid}: second engine (CCC) gamma 3 %/3 mm against pb (%)", round(float(g.pass_rate_pct), 1), "informative", None,
                    "independent recomputation of the delivered arcs (coverage beamlets: every aperture cell weighted by its open fraction); "
                    "CCC's shipped scatter cut-off overdoses small fields in water by up to about 10 %")
            res.add(f"{pid}: second engine PTV D95, CCC / pb", round(d95c / d95p, 3), "informative", None, "same MU, two engines")
            res.metrics[pid]["second_engine"] = {"gamma_3_3_pct": float(g.pass_rate_pct), "ptv_d95_ccc_over_pb": d95c / d95p}
            # the same arcs with the body set to water: separates the engines' lung transport from their other differences
            from ..services.dose_engines.pb import PencilBeamEngine
            water = np.where(gb.density > 0.05, 1.0, gb.density).astype(np.float32)
            ccc_w = CCCEngine().compute_delivered_dose(water, gb.spacing_mm, arrays.origin_mm, plan, params={"n_jobs": int(spec.get("n_jobs", 16))})
            pb_w = PencilBeamEngine().compute_plan_dose(water, gb.spacing_mm, arrays.origin_mm, plan, params={"fluence": "apertures"})
            ratio_w = _dose_at(ccc_w[ptv_mask], 95.0) / _dose_at(pb_w[ptv_mask], 95.0)
            res.add(f"{pid}: second engine PTV D95, CCC / pb, body as water", round(ratio_w, 3), "informative", None,
                    "the same arcs and metersets with every voxel above 0.05 g/cm³ set to water: the lung's share of the difference is the gap to the row above")
            res.metrics[pid]["second_engine"]["ptv_d95_ccc_over_pb_water"] = ratio_w
    res.notes.append(spec.get("note", "synthetic GTV in the right lung, PTV by expansion, rings for the dose fall-off")
                     + "; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed "
                     "and metersets re-optimized (R8); a research pipeline check, not a plan quality statement")
    return res


# ---------------------------------------------------------------------------
# hn_sib_vmat — head and neck, 70/56 Gy simultaneous integrated boost, two arcs on PDDCA
# ---------------------------------------------------------------------------

def _oropharynx_centre(arrays, offsets_mm: Sequence[float]) -> tuple:
    """A synthetic primary between the parotids: their centroids' midpoint moved by ``offsets_mm`` (x, y, z;
    LPS, so -y is anterior and -z inferior)."""
    cs = []
    for n in ("Parotid_L", "Parotid_R"):
        if n not in arrays.structure_index:
            raise Skip(f"no {n} to place the synthetic primary")
        idx = np.argwhere(arrays.mask_zyx(arrays.structure_index[n])).mean(axis=0)            # (z, y, x) voxel
        cs.append(np.asarray(arrays.origin_mm) + idx[::-1] * np.asarray(arrays.spacing_mm))
    mid = (cs[0] + cs[1]) / 2.0
    return tuple(float(v) for v in mid + np.asarray(offsets_mm, float))


def run_hn_sib_vmat(spec: dict, ctx: Context) -> CaseResult:
    """Two full arcs (clockwise and counter-clockwise, collimator 15 and -15 degrees) for a 70/56 Gy simultaneous
    integrated boost in 35 fractions on PDDCA head-and-neck CTs, with a synthetic oropharynx-like primary between
    the parotids: PTV70 = GTV + 8 mm, PTV56 = GTV + 25 mm outside PTV70 + 3 mm and the brainstem + 5 mm. Evaluated against the NCCN
    head-and-neck template (PTV_High = PTV70) and PTV56 coverage."""
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.evaluation import ClinicalGoal, EvaluationRequest, GoalSetSpec
    from ..models.geometry import GeometryBuildRequest, GeometryDeriveRequest, GridSpec, PatientRef, StructureOperation
    from ..models.vmat import ArcSpec
    from ..services.evaluation import EvaluationService
    from ..services.geometry import GeometryService
    from ..services.geometry_bundle import load_geometry_arrays

    _pb_engine()
    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    beamlet = float(spec.get("beamlet_mm", 10.0)) * (2.0 if ctx.fast else 1.0)
    iterations = int(spec.get("iterations", 150) / (2 if ctx.fast else 1))
    rounds = int(spec.get("rounds", 3)) if not ctx.fast else min(2, int(spec.get("rounds", 3)))
    rx_high, rx_low = float(spec.get("prescription_gy", 70.0)), float(spec.get("elective_gy", 56.0))
    fractions = int(spec.get("fractions", 35))
    arcs = [ArcSpec(**a) for a in spec["arcs"]]
    if ctx.fast:
        arcs = [a.model_copy(update={"sectors": max(4, a.sectors // 2)}) for a in arcs]
    radius = float(spec.get("gtv_radius_mm", 12.0))
    for pid in patients:
        pdir = root / pid
        ct_dirs = list(pdir.glob("CT_*"))
        rs_files = list(pdir.glob("RTSTRUCT_*/*.dcm"))
        if not ct_dirs or not rs_files:
            res.notes.append(f"{pid}: CT or RTSTRUCT missing"); continue
        ct_files = sorted(ct_dirs[0].glob("*.dcm"))
        geo0 = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"hn-{pid}-base"), data_root_override=str(pdir),
                                                            grid_spec=GridSpec(spacing_mm=(s, s, s))))
        centre = _oropharynx_centre(load_geometry_arrays(geo0), spec.get("gtv_offset_mm", (0.0, -15.0, -25.0)))
        case_dir = _case_dir_with_gtv(ctx, f"hn-{pid}", ct_files, rs_files, centre, radius, "synthetic oropharynx-like primary for the validation harness")
        geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"hn-{pid}"), data_root_override=str(case_dir),
                                                           grid_spec=GridSpec(spacing_mm=(s, s, s))))
        geo = GeometryService().derive(geo.geometry_id, GeometryDeriveRequest(operations=[
            StructureOperation(op="expand", name="PTV70", source="GTV", margin_mm=8.0),
            StructureOperation(op="expand", name="CTV56_full", source="GTV", margin_mm=25.0),
            StructureOperation(op="expand", name="PTV70_3mm", source="PTV70", margin_mm=3.0),
            StructureOperation(op="expand", name="Brainstem_PRV", source="Brainstem", margin_mm=5.0),
            # the elective PTV is cropped from the boost and from the brainstem's planning margin, as planners do
            StructureOperation(op="subtract", name="PTV56", source="CTV56_full", sources=["PTV70_3mm", "Brainstem_PRV"]),
            StructureOperation(op="ring", name="Ring", source="CTV56_full", inner_mm=10.0, outer_mm=30.0)]))
        arrays = load_geometry_arrays(geo)
        body = arrays.ct_hu > -500
        goals = [{"structure": "PTV70", "metric": "D95", "op": ">=", "gy": rx_high},
                 {"structure": "PTV70", "metric": "D2", "op": "<=", "gy": rx_high * 1.07},
                 # planned 2 % above its goal: normalisation fixes the boost's coverage, not the elective volume's
                 {"structure": "PTV56", "metric": "D95", "op": ">=", "gy": rx_low * 1.02}]
        for st, (metric, lim) in spec.get("organ_goals", {}).items():
            if st in arrays.structure_index and not (arrays.mask_zyx(arrays.structure_index[st]) & arrays.mask_zyx(arrays.structure_index["PTV70"])).any():
                goals.append({"structure": st, "metric": metric, "op": "<=", "gy": float(lim)})
        from ..models.optimization import ObjectiveSpec
        extra = [ObjectiveSpec(type="DMax", structure_name="Ring", dose_gy=0.8 * rx_low, weight=OAR_WEIGHT / 2)]
        out = _plan_vmat(geo, arrays, "PTV70", rx_high, goals, extra, arcs, beamlet, iterations, rounds, fractions, spec)
        vm, dose, k = out["vm"], out["dose"], out["k"]
        dose_uri = _write_volume(ctx, f"hn-{pid}-vmat", dose, arrays)
        ev = EvaluationService().run(EvaluationRequest(
            dose_ref_uri=dose_uri, geometry_id=geo.geometry_id, prescription_gy=rx_high, target_structure="PTV70", fractions=fractions,
            goals=GoalSetSpec(template_id=spec.get("goal_template", "nccn-head-neck"),
                              goals=[ClinicalGoal(structure="PTV56", metric="D95%[Gy]", op=">=", value=rx_low, priority=1, note="elective coverage")])))
        coarse = ctx.fast        # 20 mm beamlets and 90-degree sectors: a pipeline smoke test, organ goals informative
        for g in (ev.goals.results if ev.goals else []):
            if g.passed is None:
                continue
            target_goal = g.structure in ("PTV_High", "PTV70", "PTV56")
            graded = int(g.priority) == 1 and (target_goal or not coarse)
            res.add(f"{pid}: {g.structure} {g.metric} {g.op} {g.value}", round(float(g.achieved), 2) if g.achieved is not None else None,
                    f"{g.op} {g.value}", bool(g.passed) if graded else None,
                    f"{spec.get('goal_template', 'nccn-head-neck')} priority {g.priority}"
                    + ("" if graded else " (informative in fast mode: 20 mm beamlets, 90-degree sectors)" if int(g.priority) == 1 else " (informative)"))
        ptv = dose[arrays.mask_zyx(arrays.structure_index["PTV70"])]
        res.add(f"{pid}: PTV70 D5 / D95 (homogeneity)", round(_dose_at(ptv, 5.0) / _dose_at(ptv, 95.0), 3), "≤ 1.10 (informative)", None,
                f"normalised by {k:.3f} so that PTV70 D95 = {rx_high * NORMALISATION_HEADROOM:.2f} Gy")
        hot = float(dose[body & ~arrays.mask_zyx(arrays.structure_index["CTV56_full"])].max() / rx_high * 100)
        res.add(f"{pid}: hottest point outside the elective volume (% of 70 Gy)", round(hot, 1), "informative", None, "dose spill of the two arcs")
        res.add(f"{pid}: arcs deliverable at the machine's limits", vm.deliverable, "True", vm.deliverable,
                "per fraction: " + "; ".join(f"{a.arc_id} {a.n_control_points} control points, {a.total_mu * k:.0f} MU, {a.delivery_time_s:.0f} s"
                                             for a in vm.arcs))
        res.metrics[pid] = {"gtv_centre_mm": [round(float(v), 1) for v in centre], "gtv_radius_mm": radius, "rounds": out["history"],
                            "normalisation_factor": k, "vmat": vm.model_dump(mode="json"), "geometry_id": geo.geometry_id,
                            "optimization_id": out["opt"].optimization_id, "vmat_id": vm.vmat_id, "beamlets": out["bm"].fluence_elements.total_count,
                            "indices": ev.indices.model_dump() if ev.indices else None}
    res.notes.append("synthetic oropharynx-like GTV between the parotids, PTV70 +8 mm, PTV56 +25 mm outside PTV70 + 3 mm and the brainstem + 5 mm; two full arcs from "
                     "the fluence of their sector beams (pb Dij), 70/56 Gy in 35 fractions; NCCN head-and-neck template; a research pipeline "
                     "check, not a plan quality statement")
    return res


KINDS_R8 = {"pb_vs_mc": run_pb_vs_mc, "pb_vs_ccc": run_pb_vs_ccc, "lung_sbrt_vmat": run_lung_sbrt_vmat, "lung_vmat": run_lung_sbrt_vmat,
            "hn_sib_vmat": run_hn_sib_vmat}

__all__ = ["KINDS_R8", "run_pb_vs_mc", "run_pb_vs_ccc", "run_lung_sbrt_vmat", "run_hn_sib_vmat"]
