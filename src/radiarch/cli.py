"""The ``radiarch`` command (roadmap R10): planning protocols from a shell or a workflow engine.

    radiarch protocols                                   the shipped protocols
    radiarch protocol lung-60gy-30fx-vmat                one in full (JSON)
    radiarch plan --protocol lung-60gy-30fx-vmat --study 1.2.3 --data /dicom/case1 --export rt --json run.json
    radiarch plan --protocol demo-phantom-imrt --study <uid> --push    the RT objects to the server's DICOMweb, and a viewer link
    radiarch plan --protocol demo-phantom-imrt --study <uid> --push --new-export    a marked copy ("copy 2") of an earlier export
    radiarch batch --protocol lung-60gy-30fx-vmat --cases cases.csv --out results
    radiarch fetch-tcia --collection NSCLC-Radiomics --patient LUNG1-002 --cache tcia --push    a public case into the PACS
    radiarch dose --ct /dicom/case1 --structures /dicom/case1/RS.dcm --plan /plans/RP.dcm --export rt    an RT Plan's dose recomputed

A protocol is a shipped id or a JSON file. Without ``--server`` (or ``RADIARCH_SERVER``) the planning runs in this
process; with it, on that server (``--api-key`` or ``RADIARCH_API_KEY``). ``cases.csv`` has a header with
``case_id``, ``study_uid`` and optionally ``data_root`` (relative paths against ``--data-root``) and ``spacing_mm``.
Research use only; not for clinical use.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

INTENDED_USE = "RESEARCH USE ONLY. NOT FOR CLINICAL USE."
DEFAULT_SPACING_MM = 3.0     # the dose grid the records plan on; a CT's own grid (about 1 x 1 x 3 mm) is twenty times the work


def _spacing(value: Optional[float]) -> Optional[float]:
    """The dose grid spacing to build the geometry with: None (the CT's own grid) for 0."""
    return None if value is None or float(value) <= 0 else float(value)


def _progress(service: str, job: Dict[str, Any]) -> None:
    """A job's state as it changes, on stderr: planning a patient takes minutes, and silence looks like a hang."""
    stage = job.get("stage")
    progress = job.get("progress")
    parts = [f"  {service}: {job.get('state', '')}"]
    if stage and stage != job.get("state"):
        parts.append(str(stage))
    if isinstance(progress, (int, float)) and progress > 0:
        parts.append(f"{progress:.0%}")
    if job.get("message"):
        parts.append(f"({job['message']})")
    print(" ".join(parts), file=sys.stderr, flush=True)


def _client(args):
    from .sdk import Radiarch

    server = args.server or os.environ.get("RADIARCH_SERVER")
    key = args.api_key or os.environ.get("RADIARCH_API_KEY")
    if server:
        return Radiarch(server, api_key=key, poll_interval=args.poll, on_progress=_progress)
    return Radiarch.local(poll_interval=args.poll, on_progress=_progress)


def _protocol(value: str):
    """A shipped protocol id, or a JSON file."""
    from .models.protocol import PlanningProtocol

    p = Path(value)
    if p.suffix == ".json" or p.is_file():
        return PlanningProtocol.model_validate_json(p.read_text(encoding="utf-8"))
    return value


def _goal_label(g: Dict[str, Any]) -> str:
    return f"{g['structure']} {g['metric']} {g['op']} {g['gy']:g}"


def _plan_one(rx, protocol, study_uid: str, data_root: Optional[str], spacing_mm: Optional[float]):
    geo = rx.build_geometry(study_uid, data_root=data_root, spacing_mm=spacing_mm)
    return rx.run_protocol(protocol, geo)


def _print_goals(run, out=None) -> None:
    out = out or sys.stdout
    print(f"run {run.id}: {'all goals met' if run.passed else 'GOALS NOT MET'}; normalised by {run.normalisation:.4f}; "
          f"deliverable {run.deliverable}", file=out)
    for g in run.goals_table():
        achieved = "-" if g["achieved"] is None else f"{g['achieved']:.2f}"
        state = "missing" if g["passed"] is None else ("met" if g["passed"] else "NOT MET")
        print(f"  {_goal_label(g):40s} {achieved:>8s}  {state}", file=out)


def _print_mco(rx, run, out=None) -> None:
    """An mco protocol's Pareto set, the state its plan was navigated to, and what the deliverable plan made worse."""
    out = out or sys.stdout
    r = run.result
    ps = rx.get(f"/mco/{r.mco_id}")
    print(f"Pareto set {r.mco_id}: {len(ps['plans'])} plans, error bound {ps['error_bound']:.3f}", file=out)
    print(f"  navigate from state {r.state_id} (POST /mco/{r.mco_id}/navigate, or the viewer's MCO panel)", file=out)
    plan = rx.get(f"/mco/deliverables/{r.deliverable_id}")
    print(f"  deliverable plan {r.deliverable_id}: {plan['flagged']} of {len(plan['deviation'])} deviation rows flagged", file=out)
    for row in plan["deviation"]:
        if row["flagged"]:
            print(f"    {row['name']:40s} navigated {row['navigated']:.2f}, deliverable {row['deliverable']:.2f} {row['unit']}", file=out)


def cmd_protocols(args) -> int:
    with _client(args) as rx:
        rows = rx.protocols()
    for p in rows:
        rxs = p["prescription"]
        print(f"{p['protocol_id']:28s} {p['technique']:5s} {rxs['dose_gy']:g} Gy / {rxs['fractions']}  {p['name']}")
    return 0


def cmd_protocol(args) -> int:
    with _client(args) as rx:
        print(rx.protocol(args.protocol_id).model_dump_json(indent=2))
    return 0


def cmd_plan(args) -> int:
    print(INTENDED_USE, file=sys.stderr)
    with _client(args) as rx:
        run = _plan_one(rx, _protocol(args.protocol), args.study, args.data, _spacing(args.spacing))
        _print_goals(run)
        if run.result.mco_id:
            _print_mco(rx, run)
        if args.export or args.push:
            exp = run.export(label=args.label, push=bool(args.push), new_export=bool(args.new_export))
            r = exp.result
            if r.reused:
                print(f"export {r.export_id}: the stored export of this plan, the same objects and UIDs "
                      "(--new-export writes a marked copy)", file=sys.stderr)
            elif r.copy_number > 1:
                print(f"export {r.export_id}: copy {r.copy_number}, its plan follows export {r.copy_of}'s", file=sys.stderr)
            if args.export:
                files = exp.download(args.export)
                print(f"RT objects: {', '.join(str(f) for f in files)}")
            if args.push:
                if not r.pushed:
                    print(f"push failed: {r.push_error}", file=sys.stderr)
                    return 3
                print(f"pushed {len(r.objects)} RT objects of study {r.study_instance_uid} (export {r.export_id})")
                if r.viewer_url:
                    print(f"open in the viewer: {r.viewer_url}")
        if args.json:
            Path(args.json).write_text(run.result.model_dump_json(indent=2), encoding="utf-8")
    return 0 if (run.passed or not args.strict) else 2


def cmd_fetch_tcia(args) -> int:
    """A public patient's CT and structure set from TCIA into a local cache, and optionally to the DICOMweb server."""
    from .adapters import tcia

    case = tcia.fetch_patient(args.collection, args.patient, Path(args.cache), args.modalities.split(","))
    notice = tcia.licence_notice(case)
    if notice:
        print(notice, file=sys.stderr)
    print(", ".join(f"{len(f)} {m}" for m, f in case.series.items()) + f" in {Path(args.cache) / args.collection / args.patient}",
          file=sys.stderr)
    if args.push:
        n = tcia.push(case)
        print(f"pushed {n} instances to the DICOMweb server", file=sys.stderr)
    print(case.study_instance_uid)
    return 0


def _dicom_uids(path: Path) -> Dict[str, str]:
    import pydicom

    ds = pydicom.dcmread(str(path), stop_before_pixels=True)
    return {"study": str(ds.StudyInstanceUID), "series": str(ds.SeriesInstanceUID), "sop": str(ds.SOPInstanceUID),
            "modality": str(getattr(ds, "Modality", ""))}


def _first_ct(directory: Path) -> Path:
    import pydicom

    for p in sorted(directory.rglob("*")):
        if p.is_file():
            try:
                ds = pydicom.dcmread(str(p), stop_before_pixels=True, specific_tags=["Modality"])
            except Exception:
                continue
            if str(getattr(ds, "Modality", "")) == "CT":
                return p
    raise SystemExit(f"{directory}: no CT image found")


def _the_one(path: Path, modality: str, what: str) -> Path:
    """A file as given, or the one object of ``modality`` in a folder (a workflow engine hands a series as its folder);
    a folder with none, or with more than one, is refused."""
    import pydicom

    if path.is_file():
        return path
    if not path.is_dir():
        raise SystemExit(f"{path}: {what} file or folder not found")
    found: Dict[str, Path] = {}
    for p in sorted(path.rglob("*")):
        if p.is_file():
            try:
                ds = pydicom.dcmread(str(p), stop_before_pixels=True, specific_tags=["Modality", "SOPInstanceUID"])
            except Exception:
                continue
            if str(getattr(ds, "Modality", "")) == modality:
                found.setdefault(str(getattr(ds, "SOPInstanceUID", p)), p)
    if not found:
        raise SystemExit(f"{path}: no {what} in this folder")
    if len(found) > 1:
        raise SystemExit(f"{path}: {len(found)} {what}s in this folder; name one file")
    return next(iter(found.values()))


def cmd_dose(args) -> int:
    """The dose of an RT Plan on a CT with its structures: the plan imported as a beam model with its own metersets, its
    dose recomputed by an engine, and written as an RT Dose (with the plan as radiarch re-writes it) that references the
    given structure set."""
    import tempfile

    print(INTENDED_USE, file=sys.stderr)
    ct_dir = Path(args.ct)
    if not ct_dir.is_dir():
        raise SystemExit(f"{ct_dir}: not a directory")
    plan_path = _the_one(Path(args.plan), "RTPLAN", "RT Plan")
    ct = _dicom_uids(_first_ct(ct_dir))
    rtstruct = None
    root = ct_dir
    staged = None
    if args.structures:
        rs_path = _the_one(Path(args.structures), "RTSTRUCT", "RT Structure Set")
        rtstruct = _dicom_uids(rs_path)
        if rtstruct["modality"] != "RTSTRUCT":
            raise SystemExit(f"{rs_path}: not an RT Structure Set ({rtstruct['modality'] or 'no modality'})")
        if ct_dir.resolve() not in rs_path.resolve().parents:
            # the geometry service reads one directory: the CT's files and the structure set, linked side by side
            staged = tempfile.TemporaryDirectory(prefix="radiarch-dose-")
            root = Path(staged.name)
            for i, f in enumerate(sorted(q for q in ct_dir.rglob("*") if q.is_file())):
                (root / f"{i:05d}-{f.name}").symlink_to(f.resolve())
            (root / "RS.dcm").symlink_to(rs_path.resolve())
    exp = None
    try:
        with _client(args) as rx:
            geo = rx.build_geometry(ct["study"], data_root=str(root), spacing_mm=_spacing(args.spacing), ct_series_uid=ct["series"],
                                    rtstruct_uid=rtstruct["sop"] if rtstruct else None)
            bm = geo.import_plan(str(plan_path), machine=args.machine, strict_frame=not args.any_frame)
            dose = bm.recalculate(engine=args.engine)
            d, s = dose.result, dose.result.statistics
            print(f"dose {dose.id}: {d.engine_name} {d.engine_version}, {bm.result.modality.value}, "
                  f"{bm.result.fluence_elements.total_count} fluence elements, max {s.max_gy:.2f} mean {s.mean_gy:.2f} {d.dose_units}")
            if args.export or args.push:
                objects = ["rtplan", "rtdose"] if rtstruct else ["rtstruct", "rtplan", "rtdose"]
                exp = bm.export(dose=dose, label=args.label, objects=objects, rtstruct_uid=rtstruct["sop"] if rtstruct else None,
                                push=bool(args.push))
                if args.export:
                    files = exp.download(args.export)
                    print(f"RT objects: {', '.join(str(f) for f in files)}")
                if args.push:
                    r = exp.result
                    if not r.pushed:
                        print(f"push failed: {r.push_error}", file=sys.stderr)
                        return 3
                    print(f"pushed {len(r.objects)} RT objects of study {r.study_instance_uid} (export {r.export_id})")
                    if r.viewer_url:
                        print(f"open in the viewer: {r.viewer_url}")
            if args.json:
                record = {"geometry_id": geo.id, "beam_model_id": bm.id, "dose": d.model_dump(mode="json"),
                          "export": exp.result.model_dump(mode="json") if exp is not None else None}
                Path(args.json).write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    finally:
        if staged is not None:
            staged.cleanup()
    return 0


def _read_cases(path: Path, base: Optional[Path]) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows or not {"case_id", "study_uid"} <= set(rows[0]):
        raise SystemExit(f"{path}: needs a header with case_id and study_uid (and optionally data_root, spacing_mm)")
    cases = []
    for r in rows:
        root = (r.get("data_root") or "").strip() or None
        if root and base is not None and not Path(root).is_absolute():
            root = str(base / root)
        sp = (r.get("spacing_mm") or "").strip()
        cases.append({"case_id": r["case_id"].strip(), "study_uid": r["study_uid"].strip(), "data_root": root, "spacing_mm": float(sp) if sp else None})
    return cases


def cmd_batch(args) -> int:
    """Plan every case of a list with one protocol; a summary table of goals per case; one case's failure does not stop the rest."""
    print(INTENDED_USE, file=sys.stderr)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = _read_cases(Path(args.cases), Path(args.data_root) if args.data_root else None)
    protocol = _protocol(args.protocol)
    rows: List[Dict[str, Any]] = []
    goal_cols: List[str] = []
    errors = 0
    with _client(args) as rx, open(out / "runs.jsonl", "w", encoding="utf-8") as runs:
        for i, case in enumerate(cases, start=1):
            t0 = time.time()
            print(f"[{i}/{len(cases)}] {case['case_id']}", file=sys.stderr, flush=True)
            row: Dict[str, Any] = {"case_id": case["case_id"]}
            try:
                run = _plan_one(rx, protocol, case["study_uid"], case["data_root"], _spacing(case["spacing_mm"] if case["spacing_mm"] is not None else args.spacing))
                row.update({"run_id": run.id, "passed": run.passed, "normalisation": round(run.normalisation, 4), "deliverable": run.deliverable,
                            "seconds": round(time.time() - t0, 1)})
                for g in run.goals_table():
                    label = _goal_label(g)
                    if label not in goal_cols:
                        goal_cols.append(label)
                    row[label] = None if g["achieved"] is None else round(g["achieved"], 2)
                runs.write(run.result.model_dump_json() + "\n")
                if args.export:
                    run.export(label=args.label).download(out / case["case_id"])
            except Exception as exc:        # a failed case is recorded and the batch goes on
                errors += 1
                row.update({"error": f"{type(exc).__name__}: {exc}"[:500], "seconds": round(time.time() - t0, 1)})
                print(f"  failed: {row['error']}", file=sys.stderr, flush=True)
            rows.append(row)
    cols = ["case_id", "run_id", "passed", "normalisation", "deliverable", "seconds"] + goal_cols + ["error"]
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    planned = [r for r in rows if "error" not in r]
    lines = [f"# Batch: {getattr(protocol, 'protocol_id', protocol)}", "", INTENDED_USE, "",
             f"{len(cases)} cases: {len(planned)} planned, {sum(1 for r in planned if r['passed'])} with every goal met, {errors} failed.", "",
             "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + " |" for r in rows]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"summary: {out / 'summary.csv'} ({len(planned)}/{len(cases)} planned, {errors} failed)")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--server", help="a radiarch API base URL (default: RADIARCH_SERVER, else in this process)")
    common.add_argument("--api-key", help="the server's API key (default: RADIARCH_API_KEY)")
    common.add_argument("--poll", type=float, default=2.0, help="seconds between job polls")
    p = argparse.ArgumentParser(prog="radiarch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("protocols", parents=[common], help="list the shipped protocols")
    s.set_defaults(func=cmd_protocols)
    s = sub.add_parser("protocol", parents=[common], help="show a shipped protocol")
    s.add_argument("protocol_id")
    s.set_defaults(func=cmd_protocol)
    for name, func, helptext in (("plan", cmd_plan, "plan one patient with a protocol"), ("batch", cmd_batch, "plan a list of cases with a protocol")):
        s = sub.add_parser(name, parents=[common], help=helptext)
        s.add_argument("--protocol", required=True, help="a shipped protocol id or a protocol JSON file")
        s.add_argument("--spacing", type=float, default=DEFAULT_SPACING_MM,
                       help=f"dose grid spacing (mm); default {DEFAULT_SPACING_MM:g}, 0 = the CT's own grid (slow: tens of millions of voxels)")
        s.add_argument("--label", default="RESEARCH", help="RT Plan and structure set label (default RESEARCH)")
        if name == "plan":
            s.add_argument("--study", required=True, help="the DICOM study instance UID")
            s.add_argument("--data", help="a directory with the CT series and its structure set")
            s.add_argument("--export", help="write the RT objects into this directory")
            s.add_argument("--push", action="store_true",
                           help="push the RT objects to the server's DICOMweb destination (RADIARCH_DICOMWEB_URL) and print the viewer link")
            s.add_argument("--new-export", action="store_true",
                           help="write the RT objects again as a marked copy (new UIDs, 'copy N', the earlier plan as its predecessor); "
                                "by default a plan exported before with these settings returns that export")
            s.add_argument("--json", help="write the run (plan, dose, goals) as JSON")
            s.add_argument("--strict", action="store_true", help="exit 2 when a goal is not met")
        else:
            s.add_argument("--cases", required=True, help="CSV: case_id, study_uid[, data_root, spacing_mm]")
            s.add_argument("--data-root", help="relative data_root values are resolved against this directory")
            s.add_argument("--out", required=True, help="output directory: summary.csv, summary.md, runs.jsonl")
            s.add_argument("--export", action="store_true", help="also write each case's RT objects under out/<case_id>/")
        s.set_defaults(func=func)
    s = sub.add_parser("dose", parents=[common], help="the dose of an RT Plan on a CT and its structures, recomputed by an engine")
    s.add_argument("--ct", required=True, help="a directory with the CT series (and its structure set, unless --structures)")
    s.add_argument("--structures", help="the RT Structure Set file, or a folder with exactly one; the written RT objects reference it "
                                        "(default: the set in the CT directory)")
    s.add_argument("--plan", required=True, help="the RT Plan or RT Ion Plan file, or a folder with exactly one")
    s.add_argument("--engine", default="auto", choices=["auto", "ccc", "pb", "mcsquare"],
                   help="dose engine (default auto: pb for a photon plan, mcsquare for a proton plan)")
    s.add_argument("--spacing", type=float, default=DEFAULT_SPACING_MM,
                   help=f"dose grid spacing (mm); default {DEFAULT_SPACING_MM:g}, 0 = the CT's own grid")
    s.add_argument("--machine", help="the machine model the plan is delivered on (default the photon default)")
    s.add_argument("--any-frame", action="store_true", help="accept a plan whose frame of reference is not the CT's")
    s.add_argument("--export", help="write the RT Dose and the plan as re-written into this directory")
    s.add_argument("--push", action="store_true", help="push them to the server's DICOMweb destination (RADIARCH_DICOMWEB_URL)")
    s.add_argument("--label", default="RESEARCH", help="RT Plan label (default RESEARCH)")
    s.add_argument("--json", help="write the geometry, beam model, dose and export records as JSON")
    s.set_defaults(func=cmd_dose)
    s = sub.add_parser("fetch-tcia", help="download a public patient (CT and structure set) from The Cancer Imaging Archive")
    s.add_argument("--collection", default="NSCLC-Radiomics", help="TCIA collection (default NSCLC-Radiomics)")
    s.add_argument("--patient", required=True, help="the patient ID in the collection, e.g. LUNG1-002")
    s.add_argument("--cache", required=True, help="download directory (a completed series is not downloaded again)")
    s.add_argument("--modalities", default="CT,RTSTRUCT", help="series to fetch (default CT,RTSTRUCT)")
    s.add_argument("--push", action="store_true", help="push them to the DICOMweb server (RADIARCH_DICOMWEB_URL)")
    s.set_defaults(func=cmd_fetch_tcia)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
