"""Roadmap R10: the scripting SDK, end to end against the app in process — geometry, derived structures, beams,
optimization, apertures, evaluation, export, lineage — and its errors."""

from __future__ import annotations

import pydicom
import pytest

from radiarch.sdk import Evaluation, Radiarch, RadiarchError, Sequence, ops

from test_r6_rt_export_service import env  # noqa: F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)


@pytest.fixture()
def rx(env, monkeypatch):  # noqa: F811
    import radiarch.app as radiarch_app

    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with Radiarch.local(poll_interval=0.01) as client:
        yield client


def test_a_plan_as_a_chain(rx, tmp_path):
    assert "RESEARCH USE ONLY" in str(rx.info())
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    assert geo.structures == ["OAR", "PTV"] and geo.id == geo.geometry_id
    assert rx.build_geometry("1.2.3", hu_model="LINEAR").id == geo.id                      # cached
    geo2 = geo.derive(ops.expand("PTV_5", "PTV", 5.0), ops.ring("Ring", "PTV", 5.0, 15.0), ops.subtract("OAR-PTV", "OAR", "PTV_5"))
    assert {"PTV_5", "Ring", "OAR-PTV"} <= set(geo2.structures) and geo2.parent_geometry_id == geo.id

    bm = geo2.photon_beams([0, 90], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    assert bm.geometry_id == geo2.id and bm.fluence_elements.total_count > 0
    objectives = [ops.uniform("PTV", 2.0, 1.0), ops.maximum("OAR", 0.5, 1.0)]
    opt = bm.optimize(objectives, engine="analytic", max_iterations=50)
    assert opt.convergence.iterations > 0 and len(opt.weights()) == bm.fluence_elements.total_count

    ev_fluence = opt.evaluate(2.0, target="PTV")
    assert isinstance(ev_fluence, Evaluation) and ev_fluence.dose_units == "Gy"
    seq = opt.sequence(objectives, levels=5, max_iterations=50)
    assert isinstance(seq, Sequence) and seq.n_segments > 0
    dose = seq.dose()
    assert dose.id == seq.dose_id and dose.statistics.max_gy > 0
    goals = {"goals": [{"structure": "PTV", "metric": "Dmean[Gy]", "op": ">=", "value": 0.5, "priority": 1},
                       {"structure": "OAR", "metric": "D0.03cc[Gy]", "op": "<=", "value": 100.0, "priority": 2}]}
    ev = dose.evaluate(2.0, goals=goals, target="PTV", fractions=2)
    assert ev.passed is True and {g["structure"] for g in ev.goals_table()} == {"PTV", "OAR"}
    assert (tmp_path / "dose.nii.gz") == dose.download(tmp_path / "dose.nii.gz") and (tmp_path / "dose.nii.gz").stat().st_size > 0

    exp = seq.export(label="RESEARCH", prescription={"dose_gy": 2.0, "fractions": 2})
    assert {"RP.dcm", "RD.dcm"} <= set(exp.files()) and any(f.startswith("RS") for f in exp.files())
    files = exp.download(tmp_path / "rt")
    plan = next(p for p in files if p.name == "RP.dcm")
    assert pydicom.dcmread(plan).PlanIntent == "RESEARCH"

    # the same objects by id, and the lineage
    assert rx.sequence(seq.id).beam_model_id == seq.beam_model_id and rx.optimization(opt.id).geometry_id == geo2.id
    graph = exp.lineage()
    assert {n["ref"]["kind"] for n in graph["nodes"]} >= {"rt_export", "sequence", "optimization", "geometry"}


def test_errors_carry_the_service_detail(rx):
    with pytest.raises(RadiarchError) as e:
        rx.geometry("no-such-geometry")
    assert e.value.status_code == 404 and "not found" in str(e.value.detail).lower()
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    with pytest.raises(RadiarchError) as e:
        geo.derive(ops.expand("X", "NoSuchStructure", 3.0))
    assert e.value.status_code == 422 and "NoSuchStructure" in str(e.value.detail)


def test_jobs_are_polled_to_their_result(rx, monkeypatch):
    """A 202 answer is followed through the service's jobs route to the result."""
    from radiarch.models.geometry import GeometryResult

    calls = []
    real = rx.request

    class _Resp:
        def __init__(self, status, data):
            self.status_code, self._data = status, data

        def json(self):
            return self._data

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")

    def fake(method, path, json=None, params=None, expect=(200, 201, 202, 204)):
        calls.append((method, path))
        if method == "POST" and path.endswith("/geometry/build"):
            return _Resp(202, {"job_id": "job-1"})
        if path.endswith("/geometry/jobs/job-1"):
            n = sum(1 for c in calls if c[1].endswith("/geometry/jobs/job-1"))
            return _Resp(200, {"state": "running"} if n < 3 else {"state": "succeeded", "geometry_id": geo.id})
        return real(method, path, json=json, params=params, expect=expect)

    monkeypatch.setattr(rx, "request", fake)
    res = rx.submit("geometry", "/geometry/build", {"patient_ref": {"dicom_study_uid": "1.2.3"}}, GeometryResult)
    assert res.geometry_id == geo.id and sum(1 for c in calls if "jobs" in c[1]) == 3

    def failing(method, path, json=None, params=None, expect=(200, 201, 202, 204)):
        if method == "POST":
            return _Resp(202, {"job_id": "job-2"})
        return _Resp(200, {"state": "failed", "message": "engine crashed"})

    monkeypatch.setattr(rx, "request", failing)
    with pytest.raises(RadiarchError, match="engine crashed"):
        rx.submit("geometry", "/geometry/build", {}, GeometryResult)
