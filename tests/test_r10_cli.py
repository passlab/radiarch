"""Roadmap R10: the ``radiarch`` command — plan one patient, plan a batch (one case failing), and the CWL tool
descriptions that wrap them for workflow engines."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pydicom
import pytest
import yaml

from radiarch.cli import build_parser, main

from test_r6_rt_export_service import env  # noqa: F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)
from test_r10_protocols import PROTOCOL

CWL_DIR = Path(__file__).resolve().parents[1] / "src" / "radiarch" / "cwl"


@pytest.fixture()
def cli_env(env, monkeypatch, tmp_path):  # noqa: F811
    import radiarch.app as radiarch_app
    from radiarch.api.routes import protocols as routes
    from radiarch.services.geometry import GeometryService

    routes._service.cache_clear()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    real_load = GeometryService._load

    def load(self, req):
        if req.patient_ref.dicom_study_uid == "9.9.9-missing":
            raise ValueError("no CT series under the data root")
        return real_load(self, req)

    monkeypatch.setattr(GeometryService, "_load", load)
    monkeypatch.delenv("RADIARCH_SERVER", raising=False)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(PROTOCOL), encoding="utf-8")
    yield path
    routes._service.cache_clear()


def test_plan_one_patient(cli_env, tmp_path, capsys):
    code = main(["plan", "--protocol", str(cli_env), "--study", "1.2.3", "--export", str(tmp_path / "rt"), "--json", str(tmp_path / "run.json"),
                 "--poll", "0.01"])
    out = capsys.readouterr().out
    assert code == 0 and "PTV D95 >= 2" in out and "Liver Dmean <= 1" in out and "missing" in out
    run = json.loads((tmp_path / "run.json").read_text())
    assert run["protocol"]["protocol_id"] == "test-static" and run["normalisation"] > 0
    rp = pydicom.dcmread(tmp_path / "rt" / "RP.dcm")
    assert rp.RTPlanLabel == "RESEARCH" and int(rp.FractionGroupSequence[0].NumberOfFractionsPlanned) == 2


def test_plan_and_push_prints_the_viewer_link(cli_env, tmp_path, capsys, monkeypatch):
    from radiarch.adapters import dicomweb
    from radiarch.config import get_settings

    sent = []
    monkeypatch.setattr(dicomweb.DICOMwebNotifier, "store_instances", lambda self, paths, raise_errors=False: sent.extend(paths) or True)
    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", "http://pacs.invalid/dicom-web")
    monkeypatch.setenv("RADIARCH_VIEWER_URL", "http://localhost:3000")
    get_settings.cache_clear()
    code = main(["plan", "--protocol", str(cli_env), "--study", "1.2.3", "--push", "--poll", "0.01"])
    out = capsys.readouterr().out
    assert code == 0 and sent and "pushed" in out
    assert "open in the viewer: http://localhost:3000/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.8.498.6000" in out

    def refuse(self, paths, raise_errors=False):
        raise RuntimeError("PACS unreachable")
    monkeypatch.setattr(dicomweb.DICOMwebNotifier, "store_instances", refuse)
    code = main(["plan", "--protocol", str(cli_env), "--study", "1.2.3", "--push", "--poll", "0.01"])
    assert code == 3 and "PACS unreachable" in capsys.readouterr().err
    get_settings.cache_clear()


def test_a_rerun_pushes_the_same_objects_and_a_new_export_marks_its_copy(cli_env, capsys, monkeypatch):
    """Planning a patient again pushes the stored export, whose UIDs the archive already holds; --new-export is a copy."""
    from radiarch.adapters import dicomweb
    from radiarch.config import get_settings

    sent = []
    monkeypatch.setattr(dicomweb.DICOMwebNotifier, "store_instances",
                        lambda self, paths, raise_errors=False: sent.append(sorted(pydicom.dcmread(p).SOPInstanceUID for p in paths)) or True)
    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", "http://pacs.invalid/dicom-web")
    get_settings.cache_clear()
    args = ["plan", "--protocol", str(cli_env), "--study", "1.2.3", "--push", "--poll", "0.01"]
    assert main(args) == 0 and "stored export" not in capsys.readouterr().err
    assert main(args) == 0 and "the stored export of this plan" in capsys.readouterr().err
    assert len(sent) == 2 and sent[0] == sent[1]
    assert main(args + ["--new-export"]) == 0 and "copy 2" in capsys.readouterr().err
    assert set(sent[2]).isdisjoint(sent[0])
    get_settings.cache_clear()


def test_the_demo_protocol_ships():
    from radiarch.services.autoplan import load_protocol

    p = load_protocol("demo-phantom-imrt")
    assert p.prescription.target == "PTV" and "TargetVolume" in p.structure_aliases["Target"] and p.engine.name == "pb"


def test_batch_goes_on_past_a_failed_case(cli_env, tmp_path, capsys):
    cases = tmp_path / "cases.csv"
    cases.write_text("case_id,study_uid,data_root\nA,1.2.3,a\nB,9.9.9-missing,b\nC,1.2.4,c\n", encoding="utf-8")
    code = main(["batch", "--protocol", str(cli_env), "--cases", str(cases), "--data-root", str(tmp_path), "--out", str(tmp_path / "out"),
                 "--export", "--poll", "0.01"])
    assert code == 1                                                     # one case failed
    rows = list(csv.DictReader(open(tmp_path / "out" / "summary.csv", encoding="utf-8")))
    by = {r["case_id"]: r for r in rows}
    assert by["A"]["run_id"] and by["C"]["run_id"] and not by["A"]["error"]
    assert "no CT series" in by["B"]["error"] and not by["B"]["run_id"]
    assert "PTV D95 >= 2" in rows[0] and float(by["A"]["PTV D95 >= 2"]) == pytest.approx(2.004, abs=0.01)      # the table rounds to 0.01 Gy
    assert len((tmp_path / "out" / "runs.jsonl").read_text().splitlines()) == 2
    assert (tmp_path / "out" / "A" / "RP.dcm").is_file() and not (tmp_path / "out" / "B").exists()
    md = (tmp_path / "out" / "summary.md").read_text()
    assert "3 cases: 2 planned" in md and "RESEARCH USE ONLY" in md
    # the shipped protocols list, and one shown in full
    assert main(["protocols"]) == 0 and "lung-60gy-30fx-vmat" in capsys.readouterr().out
    assert main(["protocol", "lung-sbrt-54gy-3fx-vmat"]) == 0 and json.loads(capsys.readouterr().out)["prescription"]["fractions"] == 3


@pytest.mark.parametrize("name", ["radiarch-plan.cwl", "radiarch-batch.cwl"])
def test_cwl_tools_match_the_command(name):
    """Each CWL tool calls a real subcommand, and every input it binds is an option of that subcommand."""
    tool = yaml.safe_load((CWL_DIR / name).read_text(encoding="utf-8"))
    assert tool["cwlVersion"] == "v1.2" and tool["class"] == "CommandLineTool" and tool["baseCommand"][0] == "radiarch"
    sub = tool["baseCommand"][1]
    parser = build_parser()
    subparser = parser._subparsers._group_actions[0].choices[sub]
    options = {s for a in subparser._actions for s in a.option_strings}
    bound = [spec["inputBinding"]["prefix"] for spec in tool["inputs"].values() if "inputBinding" in spec]
    bound += [a for a in tool.get("arguments", []) if isinstance(a, str) and a.startswith("--")]
    assert bound and set(bound) <= options, set(bound) - options
    assert "RESEARCH" in tool["doc"] and tool["outputs"]


def test_a_job_reports_its_progress_while_the_command_waits(capsys):
    """Against a server, the command prints a job's state, stage and progress as they change (not every poll)."""
    import httpx

    from radiarch.cli import _progress
    from radiarch.sdk import Radiarch

    states = iter([{"state": "running", "stage": "structures", "progress": 0.05},
                   {"state": "running", "stage": "planning", "progress": 0.15, "message": "imrt planning, round 1 of up to 2"},
                   {"state": "running", "stage": "planning", "progress": 0.15, "message": "imrt planning, round 1 of up to 2"},
                   {"state": "succeeded", "stage": "done", "progress": 1.0, "geometry_id": "g1"}])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": "j1"})
        if request.url.path.endswith("/jobs/j1"):
            return httpx.Response(200, json=next(states))
        return httpx.Response(200, json={"ok": True})

    rx = Radiarch("http://radiarch/api/v1", poll_interval=0, on_progress=_progress,
                  http=httpx.Client(base_url="http://radiarch/api/v1", transport=httpx.MockTransport(handler)))
    assert rx.submit("geometry", "/geometry/build", {}, None) == {"ok": True}
    err = capsys.readouterr().err.splitlines()
    assert err == ["  geometry: running structures 5%", "  geometry: running planning 15% (imrt planning, round 1 of up to 2)",
                   "  geometry: succeeded done 100%"]


def test_a_stored_result_is_reported_as_such(capsys):
    """Planning the same patient again returns the stored run at once (200): the command says so instead of nothing."""
    import httpx

    from radiarch.cli import _progress
    from radiarch.sdk import Radiarch

    rx = Radiarch("http://radiarch/api/v1", poll_interval=0, on_progress=_progress,
                  http=httpx.Client(base_url="http://radiarch", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))))
    assert rx.submit("protocols", "/protocols/run", {}, None) == {"ok": True}
    assert capsys.readouterr().err.splitlines() == ["  protocols: done (computed before: the stored result)"]
