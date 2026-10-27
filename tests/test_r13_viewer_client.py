"""Roadmap R13.2c: the viewer's API client (viewer/radiarch-client, JavaScript) against a running radiarch.

radiarch's app is served by uvicorn in a thread, with the API key required. An export is written. The client's
Node tests then:
- find the export by DICOM UIDs;
- summarise the plan;
- evaluate the export against a goal template through the job, then from the cache.
Their evaluation is checked against the one radiarch's service returns for the same request.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

from test_r6_rt_export_service import env  # noqa: F401
from test_r13_viewer import _export

CLIENT = Path(__file__).resolve().parent.parent / "viewer" / "radiarch-client"
NODE = shutil.which("node")
KEY = "r13-test-key"
TEMPLATE = "rtog-0617"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def api(env, monkeypatch):  # noqa: F811
    import uvicorn

    import radiarch.app as radiarch_app
    from radiarch.api.routes import evaluation as evaluation_routes
    from radiarch.api.routes import rt as rt_routes
    from radiarch.config import get_settings

    monkeypatch.setenv("RADIARCH_API_KEY", KEY)
    get_settings.cache_clear()
    for cached in (rt_routes._service, evaluation_routes._service):
        cached.cache_clear()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(radiarch_app.create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started:
        assert time.time() < deadline, "radiarch did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/api/v1"
    server.should_exit = True
    thread.join(timeout=10)
    for cached in (rt_routes._service, evaluation_routes._service):
        cached.cache_clear()
    get_settings.cache_clear()


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_viewer_client_against_radiarch(api, tmp_path):
    from radiarch.models.evaluation import EvaluationRequest, GoalSetSpec
    from radiarch.services.evaluation import EvaluationService

    svc, res = _export()
    dose = next(o for o in res.objects if o.kind == "RTDOSE")
    case = {"export_id": res.export_id, "study_instance_uid": res.study_instance_uid, "plan_sop_instance_uid": res.plan_sop_instance_uid,
            "dose_series_instance_uid": dose.series_instance_uid, "beams": sorted(res.beam_numbers, key=res.beam_numbers.get),
            "beam_metersets": res.beam_metersets, "template_id": TEMPLATE}
    (tmp_path / "case.json").write_text(json.dumps(case))
    out = tmp_path / "out.json"

    proc = subprocess.run([NODE, "--test", "--test-reporter=tap", str(CLIENT / "test" / "client.test.js")], cwd=CLIENT,
                          capture_output=True, text=True, timeout=300,
                          env={**os.environ, "RADIARCH_TEST_API": api, "RADIARCH_TEST_API_KEY": KEY,
                               "RADIARCH_TEST_CASE": str(tmp_path / "case.json"), "RADIARCH_TEST_OUT": str(out)})
    report = proc.stdout + proc.stderr
    assert proc.returncode == 0, report
    assert "# skipped 0" in report and "# fail 0" in report, report

    # the client's evaluation is radiarch's for the same request
    got = json.loads(out.read_text())
    request = EvaluationRequest(geometry_id=res.geometry_id, dose_id=res.dose_id, prescription_gy=2.0, fractions=2, dvh_bins=200,
                                goals=GoalSetSpec(template_id=TEMPLATE))
    mine = EvaluationService().store.lookup_by_cache_key(request.compute_cache_key())
    assert mine is not None and got["evaluation"]["evaluation_id"] == mine.evaluation_id
    assert got["evaluation"]["goals"]["n_passed"] == mine.goals.n_passed
    assert [(r["priority"], r["structure"]) for r in got["rows"]] == sorted((g.priority, g.structure) for g in mine.goals.results)
