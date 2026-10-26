"""Roadmap R10: planning protocols run end to end — aliases, derived structures, the goal-driven loop, apertures, the
plan normalised in its metersets, goals, cache, lineage, export — through the SDK, the routes and the job."""

from __future__ import annotations

import numpy as np
import pydicom
import pytest

from radiarch.sdk import ProtocolRun, Radiarch, RadiarchError

from test_r6_rt_export_service import env  # noqa: F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)

PROTOCOL = {
    "protocol_id": "test-static", "name": "test: three static fields", "site": "test",
    "prescription": {"target": "PTV", "dose_gy": 2.0, "fractions": 2},
    "structure_aliases": {"Cord": ["SpinalCord", "OAR"]},            # the patient calls it OAR
    "structures": [{"op": "ring", "name": "Ring", "source": "PTV", "inner_mm": 5.0, "outer_mm": 15.0}],
    "goals": [{"structure": "PTV", "metric": "D95", "op": ">=", "gy": 2.0},
              {"structure": "Cord", "metric": "Dmax", "op": "<=", "gy": 1.8},
              {"structure": "Liver", "metric": "Dmean", "op": "<=", "gy": 1.0}],       # a structure this patient lacks
    "extra_objectives": [{"type": "DMax", "structure_name": "Ring", "dose_gy": 1.8, "weight": 50.0}],
    "beams": {"technique": "imrt", "count": 3, "sequence_levels": 5},
    "machine": "test-120", "engine": {"name": "analytic"}, "beamlet_mm": 10.0, "jaw_margin_mm": 10.0, "iterations": 50, "rounds": 2,
}


@pytest.fixture()
def rx(env, monkeypatch):  # noqa: F811
    import radiarch.app as radiarch_app
    from radiarch.api.routes import protocols as routes

    routes._service.cache_clear()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with Radiarch.local(poll_interval=0.01) as client:
        yield client
    routes._service.cache_clear()


def test_a_protocol_plans_a_patient(rx, tmp_path):
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.lineage import LineageService
    from radiarch.models.lineage import VersionRef

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    run = geo.run_protocol(PROTOCOL)
    assert isinstance(run, ProtocolRun) and run.geometry_id == geo.id and run.sequence_id and run.vmat_id is None
    pgeo = run.geometry()
    assert {"Cord", "Ring"} <= set(pgeo.structures) and pgeo.parent_geometry_id == geo.id

    # normalised in its metersets: every segment's MU is the sequence's times the factor, and so is the dose
    store = BeamModelService().store
    seq = rx.sequence(run.sequence_id)
    src, out = store.load_plan(seq.beam_model_id), store.load_plan(run.beam_model_id)
    mu_src = np.array([s.mu for b in src.beams for s in b.segments])
    mu_out = np.array([s.mu for b in out.beams for s in b.segments])
    assert np.allclose(mu_out, mu_src * run.normalisation, rtol=1e-9) and run.normalisation > 0
    assert run.dose().statistics.max_gy == pytest.approx(seq.dose().statistics.max_gy * run.normalisation, rel=1e-5)

    goals = {g["structure"]: g for g in run.goals_table()}
    assert goals["PTV"]["achieved"] == pytest.approx(2.0 * 1.002, rel=1e-3) and goals["PTV"]["passed"]
    assert goals["Liver"]["passed"] is None and goals["Liver"]["achieved"] is None         # missing: reported, not failed
    assert run.passed == all(g["passed"] is not False for g in goals.values())
    assert [h.get("round") for h in run.history][:1] == [1]

    # the same protocol on the same patient is the cached run; the lineage reaches the sequence's plan
    assert geo.run_protocol(PROTOCOL).id == run.id
    node = LineageService().node(VersionRef(kind="beam_model", id=run.beam_model_id))
    assert f"beam_model:{seq.beam_model_id}" in {p.key for p in node.parents}

    exp = run.export(label="RESEARCH")
    rp = next(p for p in exp.download(tmp_path) if p.name == "RP.dcm")
    ds = pydicom.dcmread(rp)
    total = sum(float(b.BeamMeterset) for b in ds.FractionGroupSequence[0].ReferencedBeamSequence)
    assert total == pytest.approx(float(mu_out.sum()) / 2, rel=1e-3)        # per fraction: 2 fractions


def test_shipped_protocols_and_refusals(rx):
    shipped = {p["protocol_id"]: p for p in rx.protocols()}
    assert {"lung-60gy-30fx-vmat", "lung-sbrt-54gy-3fx-vmat", "hn-70-56gy-35fx-vmat"} <= set(shipped)
    lung = rx.protocol("lung-60gy-30fx-vmat")
    assert lung.beams.technique == "vmat" and lung.prescription.dose_gy == 60.0 and lung.evaluation_template == "rtog-0617"
    with pytest.raises(RadiarchError) as e:
        rx.protocol("no-such-protocol")
    assert e.value.status_code == 404

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    with pytest.raises(RadiarchError) as e:                       # VMAT recomputes its control points with pb only
        geo.run_protocol({**PROTOCOL, "protocol_id": "test-vmat-analytic",
                          "beams": {"technique": "vmat", "arcs": [{"arc_id": "A", "start_deg": 181.0, "stop_deg": 179.0, "direction": "CW",
                                                                   "sectors": 4, "control_point_spacing_deg": 4.0}]}})
    assert "pencil-beam" in str(e.value.detail)
    with pytest.raises(RadiarchError) as e:                       # the target must exist after the structures
        geo.run_protocol({**PROTOCOL, "protocol_id": "test-no-target", "prescription": {"target": "PTV2", "dose_gy": 2.0, "fractions": 2},
                          "goals": [{"structure": "PTV2", "metric": "D95", "op": ">=", "gy": 2.0}]})
    assert "PTV2" in str(e.value.detail)
    with pytest.raises(Exception, match="coverage goal"):
        from radiarch.models.protocol import PlanningProtocol
        PlanningProtocol(**{**PROTOCOL, "goals": [{"structure": "Cord", "metric": "Dmax", "op": "<=", "gy": 1.0}]})
