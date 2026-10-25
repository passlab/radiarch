"""Validation cases of roadmap R9: deformable registration on a public 4DCT with contours on every phase.

``registration_4d``: for each patient, one breathing phase (the moving image) is registered to another (the
fixed image); the moving phase's contours are propagated through the registration and compared with the
contours drawn on the fixed phase (Dice, HD95, mean surface distance), and the fiducial markers and the carina
contoured on every phase give landmark errors (the markers graded as point landmarks, the carina, a contoured
region whose centroid moves with the extent drawn, informative). The contours of the fixed phase are the reference; they are a
clinician's, so their own variability (a few mm) bounds what any registration can reach. The same comparison
without registration and after the rigid step alone are the baselines. The graded limits are AAPM TG-132's
tolerances (landmark error within 2 mm, Dice 0.8 to 0.9, mean distance to agreement within 2 to 3 mm).
A patient whose two phases carry the same image is skipped: its contours move without the image.

``run.py`` registers :data:`KINDS_R9`; the cases are YAML files in ``cases/`` like the others.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .cases_r7 import _services
from .common import CaseResult, Context, Skip, data_root


def _phases(pdir: Path) -> Dict[int, Tuple[Path, Path]]:
    """``phase % → (CT series dir, RTSTRUCT dir)`` of the contoured 4DCT: the series each structure set references."""
    import pydicom

    out: Dict[int, Tuple[Path, Path]] = {}
    for d in sorted(pdir.glob("RTSTRUCT_*")):
        f = next(d.glob("*.dcm"), None)
        if f is None:
            continue
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(ds.get("SeriesDescription", "")))
        try:
            ref = ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0].RTReferencedSeriesSequence[0].SeriesInstanceUID
        except (AttributeError, IndexError):
            continue
        ct = pdir / f"CT_{ref}"
        if m and ct.is_dir():
            out[int(round(float(m.group(1))))] = (ct, d)
    return out


def _phase_geometry(ctx: Context, pid: str, phase: int, ct_dir: Path, rs_dir: Path, spacing: float):
    """A geometry of one phase: its CT slices and its structure set linked into a case directory."""
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..services.geometry import GeometryService

    case_dir = ctx.workdir / f"4d-{pid}-{phase:02d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    for f in list(ct_dir.glob("*.dcm")) + list(rs_dir.glob("*.dcm")):
        dst = case_dir / (f"RS_{f.name}" if f.parent == rs_dir else f.name)
        if not dst.exists():
            os.symlink(f, dst)
    return GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"4d-{pid}-{phase:02d}"),
                                                        data_root_override=str(case_dir), grid_spec=GridSpec(spacing_mm=(spacing,) * 3)))


def _named(index: Dict[str, int], base: str, phase: int) -> Optional[str]:
    """The structure ``{base}_c{phase:02d}`` (the collection's naming), case-insensitively."""
    want = f"{base}_c{phase:02d}".lower()
    return next((n for n in index if n.lower() == want), None)


def run_registration_4d(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.registration import DeformableMethod, LandmarkPair, PropagateRequest, RegistrationRequest
    from ..services.contour_metrics import compare
    from ..services.geometry_bundle import load_geometry_arrays
    from ..services.registration import RegistrationService

    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    s = ctx.spacing(spec.get("spacing_mm", 2.0))
    fixed_phase, moving_phase = int(spec.get("fixed_phase", 0)), int(spec.get("moving_phase", 50))
    organs: List[str] = list(spec.get("structures", ["Tumor", "RLung", "LLung", "Heart", "Esophagus", "Cord"]))
    markers: List[str] = list(spec.get("markers", ["MarkerA", "MarkerB", "MarkerC"]))                 # point landmarks: graded
    anatomical: List[str] = list(spec.get("anatomical_landmarks", ["Carina"]))                       # contoured regions: informative
    markers_and_anatomy = markers + anatomical
    limits: Dict[str, dict] = dict(spec.get("limits", {}))
    methods = [DeformableMethod(m) for m in spec.get("methods", ["demons", "bspline"])]
    graded = DeformableMethod(spec.get("graded_method", "demons"))
    svc = RegistrationService()

    for pid in patients:
        phases = _phases(root / pid)
        if fixed_phase not in phases or moving_phase not in phases:
            res.notes.append(f"{pid}: phases {fixed_phase} and {moving_phase} with contours not found ({sorted(phases)})"); continue
        fixed = _phase_geometry(ctx, pid, fixed_phase, *phases[fixed_phase], s)
        moving = _phase_geometry(ctx, pid, moving_phase, *phases[moving_phase], s)
        pairs = [(o, _named(fixed.structure_index, o, fixed_phase), _named(moving.structure_index, o, moving_phase)) for o in organs + markers_and_anatomy]
        pairs = [(o, f, m) for o, f, m in pairs if f and m]
        landmarks = [LandmarkPair(fixed_structure=f, moving_structure=m) for o, f, m in pairs if o in markers_and_anatomy]
        compared = [(o, f, m) for o, f, m in pairs if o in organs]
        fa = load_geometry_arrays(fixed)
        sp = tuple(fa.spacing_mm[::-1])
        # without registration: the two phases share a frame of reference and, here, a grid
        ma = load_geometry_arrays(moving)
        same_grid = tuple(moving.grid_spec.size) == tuple(fixed.grid_spec.size) and np.allclose(ma.origin_mm, fa.origin_mm)
        base = {o: compare(ma.mask_zyx(ma.structure_index[m]), fa.mask_zyx(fa.structure_index[f]), sp) for o, f, m in compared} if same_grid else {}

        for method in [DeformableMethod.none] + methods:
            reg = svc.register(RegistrationRequest(fixed_geometry_id=fixed.geometry_id, moving_geometry_id=moving.geometry_id,
                                                   deformable=method, working_spacing_mm=float(spec.get("working_spacing_mm", 3.0)),
                                                   landmarks=landmarks))
            if method is DeformableMethod.none and reg.quality.before.ncc > 0.999:
                # the two phases' images are the same: their contours differ without image motion
                res.notes.append(f"{pid}: phases {fixed_phase} and {moving_phase} have the same image (NCC {reg.quality.before.ncc:.4f}); skipped")
                break
            g = svc.propagate(reg.registration_id, PropagateRequest(structures=[m for _, _, m in compared], suffix="_prop"))
            ga = load_geometry_arrays(g)
            q = reg.quality
            tag = "rigid only" if method is DeformableMethod.none else method.value
            is_graded = method is graded
            res.metrics.setdefault(pid, {})[tag] = {"seconds": reg.seconds, "ncc": [q.before.ncc, q.after.ncc], "max_displacement_mm": q.max_displacement_mm,
                                                     "jacobian": q.jacobian.model_dump() if q.jacobian else None,
                                                     "landmarks": [l.model_dump() for l in q.landmarks]}
            for o, f, m in compared:
                c = compare(ga.mask_zyx(ga.structure_index[m + "_prop"]), fa.mask_zyx(fa.structure_index[f]), sp)
                b = base.get(o)
                res.metrics[pid][tag][o] = {"after": c, "unregistered": b}
                lim = limits.get(o, {})
                name = f"{pid}: {o} {moving_phase} % → {fixed_phase} %, {tag}"
                if is_graded and "dice" in lim:
                    res.add(f"{name}: Dice", round(c["dice"], 3), f">= {lim['dice']}", c["dice"] >= lim["dice"])
                else:
                    res.add(f"{name}: Dice", round(c["dice"], 3), "informative", None)
                for key, label in (("msd_mm", "mean surface distance (mm)"), ("hd95_mm", "HD95 (mm)")):
                    if c[key] is not None:
                        ok = c[key] <= lim[key] if is_graded and key in lim else None
                        res.add(f"{name}: {label}", round(c[key], 1), f"<= {lim[key]}" if ok is not None else "informative", ok)
                if is_graded and b is not None and o == spec.get("moved_structure", "Tumor"):
                    res.add(f"{name}: Dice above no registration ({b['dice']:.3f})", round(c["dice"], 3), f"> {b['dice']:.3f}", c["dice"] > b["dice"])
            for group, graded_group in ((markers, True), (anatomical, False)):
                errs = [l for l in q.landmarks if l.fixed_structure.rsplit("_c", 1)[0] in group]
                if not errs:
                    continue
                before = float(np.mean([l.before_mm for l in errs]))
                after = float(np.mean([l.after_mm for l in errs]))
                lim = limits.get("markers", {})
                ok = after <= lim["mean_mm"] if is_graded and graded_group and "mean_mm" in lim else None
                names = ", ".join(l.fixed_structure.rsplit("_c", 1)[0] for l in errs)
                res.add(f"{pid}: {'markers' if graded_group else 'anatomical landmarks'} ({names}) {moving_phase} % → {fixed_phase} %, {tag}: "
                        f"mean centroid error (mm, {before:.1f} before)", round(after, 2),
                        f"<= {lim['mean_mm']}" if ok is not None else "informative", ok)
            if q.jacobian is not None:
                ok = q.jacobian.fraction_nonpositive == 0.0 if is_graded else None
                res.add(f"{pid}: {tag}: body voxels where the field folds (%)", round(100 * q.jacobian.fraction_nonpositive, 3),
                        "0" if ok is not None else "informative", ok)
    if not res.checks:
        raise Skip("no patient had the two contoured phases")
    return res


# ---------------------------------------------------------------------------
# lung_4d — plan on the average CT with an ITV; dose on every phase and accumulated on the reference phase
# ---------------------------------------------------------------------------

def run_lung_4d(spec: dict, ctx: Context) -> CaseResult:
    """The ITV approach end to end: the phases of a contoured 4DCT, their average-intensity CT, the ITV as the union of
    the tumour drawn on every phase, PTV = ITV + margin, a VMAT plan on the average CT (pb), the plan recomputed on
    every phase and accumulated through Demons on the reference phase. Graded: the tumour as drawn on each phase gets
    its dose in that phase's own dose (the ITV covers the motion), and the reference tumour in the accumulated dose."""
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.four_d import AccumulateRequest, AverageCTRequest, ITVRequest, PhaseDose, PhaseDoseRequest, PhaseStructure
    from ..models.geometry import GeometryDeriveRequest, StructureOperation
    from ..models.optimization import ObjectiveSpec
    from ..models.registration import DeformableMethod, RegistrationRequest
    from ..models.vmat import ArcSpec
    from ..services.dose_persistence import read_dose_volume
    from ..services.four_d import FourDService
    from ..services.geometry import GeometryService
    from ..services.geometry_bundle import load_geometry_arrays
    from .cases_r7 import OAR_WEIGHT, _dose_at
    from .cases_r8 import _pb_engine, _plan_vmat

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
    rx = float(spec.get("prescription_gy", 60.0)); fractions = int(spec.get("fractions", 30))
    ref_phase = int(spec.get("reference_phase", 50))
    coverage = float(spec.get("coverage_fraction", 0.95))
    arcs = [ArcSpec(**a) for a in spec["arcs"]]
    four_d = FourDService()

    for pid in patients:
        phases = _phases(root / pid)
        if ref_phase not in phases or len(phases) < 2:
            res.notes.append(f"{pid}: the reference phase {ref_phase} or other contoured phases missing ({sorted(phases)})"); continue
        geos = {p: _phase_geometry(ctx, pid, p, *phases[p], s) for p in sorted(phases)}
        tumour = {p: _named(g.structure_index, spec.get("target", "Tumor"), p) for p, g in geos.items()}
        geos = {p: g for p, g in geos.items() if tumour[p]}
        ref = geos[ref_phase]
        aip = four_d.average(AverageCTRequest(reference_geometry_id=ref.geometry_id, phase_geometry_ids=[g.geometry_id for g in geos.values()]))
        itv = four_d.itv(ITVRequest(geometry_id=aip.geometry_id, sources=[PhaseStructure(geometry_id=g.geometry_id, structure=tumour[p])
                                                                           for p, g in geos.items()]))
        organ = lambda base: _named(ref.structure_index, base, ref_phase)                     # noqa: E731
        ops = [StructureOperation(op="expand", name="PTV", source="ITV", margin_mm=float(spec.get("ptv_margin_mm", 5.0))),
               StructureOperation(op="ring", name="RingNear", source="PTV", inner_mm=3.0, outer_mm=12.0),
               StructureOperation(op="ring", name="RingFar", source="PTV", inner_mm=20.0, outer_mm=float(spec.get("ring_far_outer_mm", 45.0)))]
        names = {"SpinalCord": ["Cord"], "Esophagus": ["Esophagus"], "Heart": ["Heart"], "Lungs": ["RLung", "LLung"]}
        for new, bases in names.items():
            found = [organ(b) for b in bases if organ(b)]
            if len(found) == len(bases):
                ops.append(StructureOperation(op="union", name=new, sources=found))
        if any(o.name == "Lungs" for o in ops):
            ops.append(StructureOperation(op="subtract", name="Lungs-PTV", source="Lungs", sources=["PTV"]))
        geo = GeometryService().derive(itv.geometry_id, GeometryDeriveRequest(operations=ops))
        arrays = load_geometry_arrays(geo)
        goals = [{"structure": "PTV", "metric": "D95", "op": ">=", "gy": rx}]
        for st, (metric, lim) in spec.get("organ_goals", {}).items():
            if st in arrays.structure_index:
                goals.append({"structure": st, "metric": metric, "op": "<=", "gy": float(lim), "dmax_term": not st.startswith("Lungs")})
        extra = [ObjectiveSpec(type="DMax", structure_name="RingNear", dose_gy=float(spec.get("ring_near_fraction", 0.9)) * rx, weight=OAR_WEIGHT / 2),
                 ObjectiveSpec(type="DMax", structure_name="RingFar", dose_gy=float(spec.get("ring_far_fraction", 0.5)) * rx, weight=OAR_WEIGHT)]
        out = _plan_vmat(geo, arrays, "PTV", rx, goals, extra, arcs, beamlet, iterations, rounds, fractions, spec)
        vm, planned, k = out["vm"], out["dose"], out["k"]
        mask = lambda a, n: a.mask_zyx(a.structure_index[n])                                  # noqa: E731
        gtv_ref = mask(arrays, tumour[ref_phase])
        itv_cc = mask(arrays, "ITV").sum() * s ** 3 / 1000.0
        res.add(f"{pid}: ITV over {len(geos)} phases / reference tumour (volume)", round(itv_cc / (gtv_ref.sum() * s ** 3 / 1000.0), 2), "informative",
                None, f"ITV {itv_cc:.1f} cc; PTV = ITV + {spec.get('ptv_margin_mm', 5.0)} mm; planned on the average CT")
        res.add(f"{pid}: planned PTV D95 (Gy)", round(_dose_at(planned[mask(arrays, 'PTV')], 95), 2), "informative", None,
                f"normalised by {k:.3f}; arcs deliverable: {vm.deliverable}")

        # the plan on every phase: each phase's own tumour
        doses = four_d.phase_doses(PhaseDoseRequest(beam_model_id=vm.beam_model_id, geometry_ids=[g.geometry_id for g in geos.values()]))
        worst = None
        for (p, g), d in zip(geos.items(), doses):
            pa = load_geometry_arrays(g)
            arr = read_dose_volume(Path(d.dose_grid_uri)) * k
            d95 = _dose_at(arr[mask(pa, tumour[p])], 95)
            worst = d95 if worst is None else min(worst, d95)
            res.add(f"{pid}: phase {p} %: its tumour D95 (Gy)", round(d95, 2), f">= {coverage * rx:.1f}", d95 >= coverage * rx,
                    "the plan recomputed on this phase's CT (pb, apertures)")
        # accumulated on the reference phase through Demons
        parts = []
        for (p, g), d in zip(geos.items(), doses):
            rid = None
            if p != ref_phase:
                rid = four_d.registration_service.register(RegistrationRequest(
                    fixed_geometry_id=ref.geometry_id, moving_geometry_id=g.geometry_id, deformable=DeformableMethod.demons,
                    working_spacing_mm=float(spec.get("working_spacing_mm", 3.0)))).registration_id
            parts.append(PhaseDose(dose_id=d.dose_id, registration_id=rid))
        acc = four_d.accumulate(AccumulateRequest(reference_geometry_id=ref.geometry_id, phases=parts))
        acc_arr = read_dose_volume(Path(acc.dose_grid_uri)) * k
        ra = load_geometry_arrays(ref)
        acc_d95 = _dose_at(acc_arr[mask(ra, tumour[ref_phase])], 95)
        res.add(f"{pid}: accumulated over {len(parts)} phases: reference tumour D95 (Gy)", round(acc_d95, 2), f">= {coverage * rx:.1f}",
                acc_d95 >= coverage * rx, f"Demons to phase {ref_phase} %, equal shares; planned on the average CT "
                f"{_dose_at(planned[gtv_ref], 95):.2f} Gy, worst single phase {worst:.2f} Gy")
        for st, base in (("Lungs", ("RLung", "LLung")), ("SpinalCord", ("Cord",))):
            names_ref = [_named(ra.structure_index, b, ref_phase) for b in base]
            if st in arrays.structure_index and all(names_ref):
                m_ref = np.zeros(acc_arr.shape, bool)
                for n in names_ref:
                    m_ref |= mask(ra, n)
                metric = (lambda a: float((a >= 20.0).mean() * 100)) if st == "Lungs" else (lambda a: float(a.max()))
                label = "V20Gy (%)" if st == "Lungs" else "Dmax (Gy)"
                res.add(f"{pid}: {st} {label}, accumulated / planned", round(metric(acc_arr[m_ref]), 2), "informative", None,
                        f"planned on the average CT {metric(planned[mask(arrays, st)]):.2f}")
        res.metrics[pid] = {"phases": sorted(geos), "itv_cc": itv_cc, "k": k, "vmat_id": vm.vmat_id, "accumulated_dose_id": acc.dose_id,
                            "history": out["history"]}
    if not res.checks:
        raise Skip("no patient had a contoured 4DCT")
    return res


# ---------------------------------------------------------------------------
# replan_cbct — the planning CT registered to cone-beam CTs of treatment days, organs and dose of the day
# ---------------------------------------------------------------------------

def _pancreas_series(pdir: Path) -> Tuple[Optional[Tuple[Path, Path]], List[Tuple[Path, Path, str]], Optional[Path]]:
    """The planning CT with its structure set, the cone-beam CTs aligned to it with theirs, and the clinical RT Dose."""
    import pydicom

    def first(d: Path):
        return next(d.glob("*.dcm"), None)

    cts = {d.name.split("_", 1)[1]: d for d in pdir.glob("CT_*")}
    planning, days = None, []
    for d in pdir.glob("RTSTRUCT_*"):
        f = first(d)
        if f is None:
            continue
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        try:
            ref = ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0].RTReferencedSeriesSequence[0].SeriesInstanceUID
        except (AttributeError, IndexError):
            continue
        ct = cts.get(str(ref))
        if ct is None:
            continue
        hdr = pydicom.dcmread(first(ct), stop_before_pixels=True)
        desc = str(hdr.get("SeriesDescription", ""))
        if "aligned" in desc.lower():
            # the description repeats across a patient's days ("Aligned CT - test1" twice): the date tells them apart
            days.append((ct, d, f"{desc.strip()} {hdr.get('SeriesDate', '') or hdr.get('AcquisitionDate', '')}".strip()))
        else:
            planning = (ct, d)
    dose = next(pdir.glob("RTDOSE_*/*.dcm"), None)
    return planning, sorted(days, key=lambda t: t[2]), dose


def _d_cc(values: np.ndarray, voxel_cc: float, cc: float) -> float:
    """The minimum dose to the hottest ``cc`` of a structure (D0.03cc for cc = 0.03): at least one voxel."""
    v = np.sort(np.asarray(values, float))[::-1]
    return float(v[min(len(v), max(1, int(np.ceil(cc / voxel_cc)))) - 1]) if v.size else 0.0


def run_replan_cbct(spec: dict, ctx: Context) -> CaseResult:
    """Pancreatic-CT-CBCT-SEG: the planning CT registered to each cone-beam CT (rigidly aligned to it by the collection,
    contoured on it), rigid only and deformable; the planning stomach-duodenum and bowel propagated and compared with the
    cone-beam contours; the clinical dose mapped onto the day's anatomy. Graded: the deformable registration places the
    stomach-duodenum better than rigid alignment alone and does not fold. The organ doses of the day are informative:
    they are the numbers a replanning decision would rest on."""
    res = CaseResult(spec["name"], spec["kind"])
    from ..dicom.rtdose import read_rtdose, resample_dose_to_grid
    from ..models.registration import DeformableMethod, PropagateRequest, RegistrationRequest
    from ..services.contour_metrics import compare
    from ..services.geometry_bundle import load_geometry_arrays
    from ..services.registration import RegistrationService
    from .cases_r7 import _dose_at

    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    organs: Dict[str, str] = dict(spec.get("organs", {"Stomach_duo": "Stomach_duo", "Bowel_sm": "Bowel_sm"}))
    graded_organ = spec.get("graded_organ", "Stomach_duo")
    methods = [DeformableMethod(m) for m in spec.get("methods", ["bspline", "demons"])]
    graded = DeformableMethod(spec.get("graded_method", "bspline"))
    svc = RegistrationService()

    for pid in patients:
        planning, days, dose_path = _pancreas_series(root / pid)
        if planning is None or not days:
            res.notes.append(f"{pid}: no planning CT with contours or no contoured cone-beam CT"); continue
        plan_geo = _phase_geometry(ctx, pid, 0, planning[0], planning[1], s)
        pa = load_geometry_arrays(plan_geo)
        plan_dose = None
        if dose_path is not None:
            plan_dose = resample_dose_to_grid(read_rtdose(dose_path), pa.origin_mm, pa.spacing_mm, pa.shape_zyx)
        for n, (ct_dir, rs_dir, desc) in enumerate(days, start=1):
            day_geo = _phase_geometry(ctx, pid, n, ct_dir, rs_dir, s)
            da = load_geometry_arrays(day_geo)
            sp = tuple(da.spacing_mm[::-1])
            label = f"{pid} {desc}"
            names = {}
            for o, base in organs.items():
                pn = next((k for k in plan_geo.structure_index if k.lower() == f"{base}_planct".lower()), None)
                dn = next((k for k in day_geo.structure_index if k.lower() == f"{base}_cbct".lower()), None)
                if pn and dn:
                    names[o] = (pn, dn)
            if not names:
                res.notes.append(f"{label}: no organ contoured on both"); continue
            dice_by: Dict[str, Dict[str, float]] = {}
            for method in [DeformableMethod.none] + methods:
                reg = svc.register(RegistrationRequest(fixed_geometry_id=day_geo.geometry_id, moving_geometry_id=plan_geo.geometry_id,
                                                       deformable=method, working_spacing_mm=float(spec.get("working_spacing_mm", 3.0))))
                g = svc.propagate(reg.registration_id, PropagateRequest(structures=[pn for pn, _ in names.values()], suffix="_prop"))
                ga = load_geometry_arrays(g)
                tag = "rigid only" if method is DeformableMethod.none else method.value
                q = reg.quality
                res.metrics.setdefault(label, {})[tag] = {"seconds": reg.seconds, "ncc": [q.before.ncc, q.after.ncc],
                                                          "jacobian": q.jacobian.model_dump() if q.jacobian else None}
                mapped = None
                if plan_dose is not None:
                    mapped = svc.map_volume(reg.registration_id, plan_dose, pa.origin_mm, pa.spacing_mm)
                for o, (pn, dn) in names.items():
                    ref_mask = da.mask_zyx(da.structure_index[dn])
                    c = compare(ga.mask_zyx(ga.structure_index[pn + "_prop"]), ref_mask, sp)
                    dice_by.setdefault(o, {})[tag] = c["dice"]
                    res.metrics[label][tag][o] = c
                    res.add(f"{label}: {o} planning → cone-beam, {tag}: Dice", round(c["dice"], 3), "informative", None)
                    if c["msd_mm"] is not None:
                        res.add(f"{label}: {o} planning → cone-beam, {tag}: mean surface distance (mm)", round(c["msd_mm"], 1), "informative", None)
                    if method is graded and mapped is not None and ref_mask.any():
                        plan_mask = pa.mask_zyx(pa.structure_index[pn])
                        day_vals, plan_vals = mapped[ref_mask], plan_dose[plan_mask]
                        voxel_day, voxel_plan = float(np.prod(da.spacing_mm)) / 1000.0, float(np.prod(pa.spacing_mm)) / 1000.0
                        res.add(f"{label}: {o} D0.03cc (Gy) of the day (cone-beam contour, mapped dose)", round(_d_cc(day_vals, voxel_day, 0.03), 2),
                                "informative", None, f"planned {_d_cc(plan_vals, voxel_plan, 0.03):.2f} Gy; mean {day_vals.mean():.2f} Gy, "
                                f"planned {plan_vals.mean():.2f} Gy")
                if method is graded:
                    if q.jacobian is not None:
                        res.add(f"{label}: {tag}: body voxels where the field folds (%)", round(100 * q.jacobian.fraction_nonpositive, 3), "0",
                                q.jacobian.fraction_nonpositive == 0.0)
            if graded_organ in dice_by and graded.value in dice_by[graded_organ]:
                d_def, d_rig = dice_by[graded_organ][graded.value], dice_by[graded_organ]["rigid only"]
                res.add(f"{label}: {graded_organ} Dice, {graded.value} above rigid only ({d_rig:.3f})", round(d_def, 3), f"> {d_rig:.3f}", d_def > d_rig)
    if not res.checks:
        raise Skip("no patient had a contoured planning CT and cone-beam CT")
    return res


KINDS_R9 = {"registration_4d": run_registration_4d, "lung_4d": run_lung_4d, "replan_cbct": run_replan_cbct}

__all__ = ["KINDS_R9", "run_registration_4d", "run_lung_4d", "run_replan_cbct"]
