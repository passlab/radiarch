"""Validation cases of roadmap R10: planning protocols.

``protocol_reproduces``: a shipped protocol states, as data, what a harness case plans in code. The case checks that
it does (prescription, margins, rings, goals, arcs, the loop's settings, one check each), runs it on the harness
case's patients with the harness case's synthetic tumour, and compares the template goals with the recorded run of
the harness case.

``protocol_batch``: a shipped protocol over every LCTSC thorax through ``radiarch batch``, each with a synthetic
tumour: every case planned and deliverable, its coverage and the template's priority-1 goals met.

``run.py`` registers :data:`KINDS_R10`; the cases are YAML files in ``cases/`` like the others.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List

import numpy as np

from .cases_r7 import _case_dir_with_gtv, _services
from .common import CaseResult, Context, Skip, data_root

RADIARCH_ROOT = Path(__file__).resolve().parents[3]


def _lctsc_geometry(ctx: Context, root: Path, pid: str, tag: str, spacing: float, radius_mm: float, position: str):
    """The harness's lung case geometry: the LCTSC CT and contours with a synthetic GTV sphere (at the right lung's
    centroid, or peripheral), in one structure set beside the CT (R7, R8)."""
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..services.geometry import GeometryService
    from ..services.geometry_bundle import load_geometry_arrays
    from .cases_r8 import _peripheral_gtv_centre

    pdir = root / pid
    ct_files = sorted(next(pdir.glob("CT_*")).glob("*.dcm"))
    rs_files = list(pdir.glob("RTSTRUCT_*/*.dcm"))
    if not ct_files or not rs_files:
        return None, None, "CT or RTSTRUCT missing"
    geo0 = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"{tag}-base"), data_root_override=str(pdir),
                                                        grid_spec=GridSpec(spacing_mm=(spacing,) * 3)))
    arr0 = load_geometry_arrays(geo0)
    lung_name = next((n for n in arr0.structure_index if n.lower() in ("lung_r", "lung_right")), None)
    if lung_name is None:
        return None, None, "no right lung"
    lung = arr0.mask_zyx(arr0.structure_index[lung_name])
    if position == "centroid":
        com = np.argwhere(lung).mean(axis=0)
        centre = tuple(float(arr0.origin_mm[i] + com[2 - i] * spacing) for i in range(3))
    else:
        centre = _peripheral_gtv_centre(lung, arr0.origin_mm, spacing, radius_mm)
    case_dir = _case_dir_with_gtv(ctx, tag, ct_files, rs_files, centre, radius_mm, "synthetic GTV for the validation harness")
    return case_dir, tag, None


# ---------------------------------------------------------------------------
# protocol_reproduces — a shipped protocol against the harness case it encodes
# ---------------------------------------------------------------------------

def _protocol_matches_case(protocol, case: dict) -> List[tuple]:
    """(what, protocol's, case's) for every setting a protocol and a lung VMAT harness case share."""
    from ..models.vmat import ArcSpec
    from ..services.autoplan import OAR_WEIGHT

    rx = float(case.get("prescription_gy", 60.0))
    ops = {o.name: o for o in protocol.structures}
    ptv_src = ops["PTV"].source if "PTV" in ops else None
    goals = {(g.structure, g.metric): g for g in protocol.goals}
    extra = {o.structure_name: o for o in protocol.extra_objectives}
    arcs = [a.model_dump() for a in protocol.beams.arcs]
    out = [
        ("prescription (Gy, fractions)", (protocol.prescription.dose_gy, protocol.prescription.fractions), (rx, int(case.get("fractions", 30)))),
        ("CTV margin (mm)", ops["CTV"].margin_mm if "CTV" in ops else 0.0, float(case.get("ctv_margin_mm", 0.0))),
        ("PTV margin (mm)", ops["PTV"].margin_mm, float(case.get("ptv_margin_mm", 5.0))),
        ("PTV from", ptv_src, "CTV" if float(case.get("ctv_margin_mm", 0.0)) > 0 else "GTV"),
        ("far ring outer edge (mm)", ops["RingFar"].outer_mm, float(case.get("ring_far_outer_mm", 45.0))),
        ("near ring limit (Gy, weight)", (extra["RingNear"].dose_gy, extra["RingNear"].weight),
         (round(float(case.get("ring_near_fraction", 0.85)) * rx, 6), OAR_WEIGHT / 2)),
        ("far ring limit (Gy, weight)", (extra["RingFar"].dose_gy, extra["RingFar"].weight), (round(float(case.get("ring_far_fraction", 0.4)) * rx, 6), OAR_WEIGHT)),
        ("coverage goal", (goals[("PTV", "D95")].op, goals[("PTV", "D95")].gy), (">=", rx)),
        ("arcs", arcs, [ArcSpec(**a).model_dump() for a in case["arcs"]]),
        ("beamlet (mm), iterations, rounds", (protocol.beamlet_mm, protocol.iterations, protocol.rounds),
         (float(case.get("beamlet_mm", 5.0)), int(case.get("iterations", 150)), int(case.get("rounds", 3)))),
        ("machine, jaw margin (mm)", (protocol.machine, protocol.jaw_margin_mm), (case.get("machine", "synthetic-120"), float(case.get("jaw_margin_mm", 10.0)))),
        ("evaluation template", protocol.evaluation_template, case.get("goal_template")),
    ]
    for st, lim in (case.get("organ_limits") or {}).items():
        g = goals.get((st, "Dmax"))
        out.append((f"{st} Dmax limit", g.gy if g else None, float(lim)))
    for st, (metric, lim) in (case.get("organ_goals") or {}).items():
        g = goals.get((st, metric))
        out.append((f"{st} {metric} goal (Gy, maximum term)", (g.gy, g.dmax_term) if g else None, (float(lim), not st.startswith("Lungs"))))
    return out


def _normalise(v):
    if isinstance(v, (list, tuple)):
        return [_normalise(x) for x in v]
    if isinstance(v, dict):
        return {k: _normalise(x) for k, x in v.items()}
    return round(v, 6) if isinstance(v, float) else v


def run_protocol_reproduces(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.protocol import ProtocolRunRequest
    from ..services.autoplan import AutoplanService, load_protocol
    from ..services.evaluation import EvaluationService
    from ..services.geometry import GeometryService
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from .cases_r8 import _pb_engine
    from .run import load_cases

    protocol = load_protocol(spec["protocol"])
    case = load_cases()[spec["case"]]
    for what, ours, theirs in _protocol_matches_case(protocol, case):
        res.add(f"protocol {protocol.protocol_id} encodes {case['name']}: {what}", json.dumps(_normalise(ours)), json.dumps(_normalise(theirs)),
                _normalise(ours) == _normalise(theirs))

    _pb_engine()
    root = data_root() / Path(case["data"]).name
    if not root.is_dir():
        res.notes.append(f"data not found: {root}; only the protocol's settings were checked")
        return res
    _services(ctx)
    record = json.loads((RADIARCH_ROOT / spec["record"]).read_text(encoding="utf-8")) if spec.get("record") else None
    rec_checks = {}
    if record:
        rec = next((r for r in record["results"] if r["name"] == spec["case"]), None)
        rec_checks = {c["name"]: c for c in (rec or {}).get("checks", [])}
    patients = case["patients"][:1] if ctx.fast else case["patients"]
    s = ctx.spacing(case.get("spacing_mm", 3.0))
    for pid in patients:
        case_dir, tag, why = _lctsc_geometry(ctx, root, pid, f"{spec['name']}-{pid}", s, float(case.get("gtv_radius_mm", 20.0)),
                                             case.get("gtv_position", "peripheral"))
        if case_dir is None:
            res.notes.append(f"{pid}: {why}"); continue
        geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=tag), data_root_override=str(case_dir),
                                                           grid_spec=GridSpec(spacing_mm=(s, s, s))))
        run = AutoplanService().run(ProtocolRunRequest(geometry_id=geo.geometry_id, protocol=protocol))
        res.add(f"{pid}: protocol run deliverable", run.deliverable, "True", run.deliverable, f"normalised by {run.normalisation:.4f}")
        ev = EvaluationService().store.get_by_id(run.evaluation_id) if run.evaluation_id else None
        for g in (ev.goals.results if ev and ev.goals else []):
            if g.passed is None or g.achieved is None:
                continue
            name = f"{pid}: {g.structure} {g.metric} {g.op} {g.value}"
            res.add(f"{name} (protocol)", round(float(g.achieved), 2), f"{g.op} {g.value}", bool(g.passed) if int(g.priority) == 1 else None,
                    f"{protocol.evaluation_template} priority {g.priority}")
            recorded = rec_checks.get(name)
            if recorded is not None and not ctx.fast:
                diff = abs(float(g.achieved) - float(recorded["value"]))
                tol = max(0.01 * abs(float(recorded["value"])), 0.05)
                res.add(f"{name}: protocol against the recorded harness run", round(float(g.achieved), 2), f"{recorded['value']} ± {tol:.2f}",
                        diff <= tol, "the harness case's run in the R8 record's correction")
        res.metrics[pid] = {"run_id": run.run_id, "normalisation": run.normalisation, "seconds": run.seconds, "history": run.history,
                            "goals": [g.model_dump() for g in run.goals]}
    return res


# ---------------------------------------------------------------------------
# protocol_batch — a shipped protocol over the LCTSC thoraces through `radiarch batch`
# ---------------------------------------------------------------------------

def run_protocol_batch(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..cli import main as cli_main
    from ..services.autoplan import load_protocol
    from ..services.evaluation import EvaluationService
    from ..tasks.celery_app import celery_app
    from .cases_r8 import _pb_engine

    _pb_engine()
    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    celery_app.conf.task_always_eager = True          # the command runs the protocols in this process: jobs run at once
    protocol = load_protocol(spec["protocol"])
    patients = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))
    if spec.get("patients"):
        patients = [p for p in patients if p in spec["patients"]]
    patients = patients[:2] if ctx.fast else patients
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    rows = []
    for pid in patients:
        case_dir, tag, why = _lctsc_geometry(ctx, root, pid, f"{spec['name']}-{pid}", s, float(spec.get("gtv_radius_mm", 12.0)),
                                             spec.get("gtv_position", "peripheral"))
        if case_dir is None:
            res.notes.append(f"{pid}: {why}"); continue
        rows.append({"case_id": pid, "study_uid": tag, "data_root": str(case_dir)})
    cases = ctx.workdir / f"{spec['name']}-cases.csv"
    with open(cases, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "study_uid", "data_root"])
        w.writeheader()
        w.writerows(rows)
    out = ctx.workdir / f"{spec['name']}-out"
    code = cli_main(["batch", "--protocol", protocol.protocol_id, "--cases", str(cases), "--out", str(out), "--spacing", str(s), "--poll", "0.05"])
    summary = list(csv.DictReader(open(out / "summary.csv", encoding="utf-8")))
    res.add(f"radiarch batch over {len(rows)} LCTSC thoraces: cases planned", sum(1 for r in summary if r.get("run_id")), f"= {len(rows)}",
            all(r.get("run_id") for r in summary) and len(summary) == len(rows), f"exit code {code}")
    runs = [json.loads(line) for line in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rx = protocol.prescription
    for run in runs:
        pid = next((r["case_id"] for r, sr in zip(rows, summary) if sr.get("run_id") == run["run_id"]), run["run_id"][:8])
        res.add(f"{pid}: deliverable", run["deliverable"], "True", run["deliverable"], f"normalised by {run['normalisation']:.4f}")
        cover = next(g for g in run["goals"] if g["structure"] == rx.target and g["op"] == ">=")
        res.add(f"{pid}: {cover['structure']} {cover['metric']} (Gy)", round(cover["achieved"], 2), f">= {cover['gy']}", cover["passed"],
                "met by normalisation")
        for g in run["goals"]:
            if g is cover or g["achieved"] is None:
                continue
            res.add(f"{pid}: planning goal {g['structure']} {g['metric']} {g['op']} {g['gy']}", round(g["achieved"], 2), f"{g['op']} {g['gy']}", None,
                    "the protocol's planning goal (informative; the template grades)")
        ev = EvaluationService().store.get_by_id(run["evaluation_id"]) if run.get("evaluation_id") else None
        for g in (ev.goals.results if ev and ev.goals else []):
            if g.passed is None or g.achieved is None:
                continue
            res.add(f"{pid}: {g.structure} {g.metric} {g.op} {g.value}", round(float(g.achieved), 2), f"{g.op} {g.value}",
                    bool(g.passed) if int(g.priority) == 1 else None, f"{protocol.evaluation_template} priority {g.priority}")
        res.metrics[pid] = {"run_id": run["run_id"], "normalisation": run["normalisation"], "seconds": run["seconds"]}
    if not res.checks:
        raise Skip("no LCTSC thorax could be planned")
    return res


KINDS_R10 = {"protocol_reproduces": run_protocol_reproduces, "protocol_batch": run_protocol_batch}

__all__ = ["KINDS_R10", "run_protocol_reproduces", "run_protocol_batch"]
