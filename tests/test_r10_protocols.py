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
    # the structure set names each structure once, as the protocol does: Cord, not also the patient's OAR it came from
    assert run.result.aliased == {"Cord": "OAR"}
    rs = pydicom.dcmread(tmp_path / "RS.dcm")
    assert sorted(r.ROIName for r in rs.StructureSetROISequence) == ["Cord", "PTV", "Ring"]


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


def test_the_shipped_lung_protocol_encodes_its_harness_case():
    """Every setting the lung protocol shares with the R8 harness case it reproduces is equal (the validation case
    ``protocol_lung_vmat`` then runs it; this part needs no patient data)."""
    from radiarch.services.autoplan import load_protocol
    from radiarch.validation.cases_r10 import _normalise, _protocol_matches_case
    from radiarch.validation.run import load_cases

    pairs = _protocol_matches_case(load_protocol("lung-60gy-30fx-vmat"), load_cases()["lung_vmat_lctsc"])
    assert len(pairs) >= 15
    assert [what for what, ours, theirs in pairs if _normalise(ours) != _normalise(theirs)] == []


def test_planning_reports_each_round(rx):
    """A protocol job says which goal-driven round it is in: planning a patient takes minutes."""
    from radiarch.models.protocol import PlanningProtocol, ProtocolRunRequest
    from radiarch.services.autoplan import AutoplanService

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    seen = []
    protocol = PlanningProtocol(**{**PROTOCOL, "protocol_id": "test-rounds", "goals": PROTOCOL["goals"][:1] + [
        {"structure": "Cord", "metric": "Dmax", "op": "<=", "gy": 0.01}]})              # never met: every round runs
    AutoplanService().run(ProtocolRunRequest(geometry_id=geo.id, protocol=protocol),
                          progress_callback=lambda stage, fraction, message: seen.append((str(stage.value), fraction, message)))
    rounds = [m for s, f, m in seen if "round" in m]
    assert rounds == ["imrt planning, round 1 of up to 2", "imrt planning, round 2 of up to 2"]
    fractions = [f for s, f, m in seen]
    assert fractions == sorted(fractions) and seen[-1][0] == "done"


def test_an_alias_matches_one_breathing_phase_and_refuses_several(rx):
    """A 4D CT's structures carry their phase (``SpinalCord_c30``): an alias takes it when one phase's structure is
    there, and the run's alias map names it; with several phases' structures the run is refused, not guessed."""
    from radiarch.services.autoplan import _one_phase

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    protocol = {**PROTOCOL, "protocol_id": "test-phase", "structure_aliases": {"Cord": ["SpinalCord"]}}
    one = geo.derive({"op": "union", "name": "SpinalCord_c30", "sources": ["OAR"]})
    run = one.run_protocol(protocol)
    assert run.result.aliased == {"Cord": "SpinalCord_c30"} and "Cord" in run.geometry().structures
    two = one.derive({"op": "union", "name": "SPINALCORD_C40", "sources": ["OAR"]})
    with pytest.raises(RadiarchError) as e:
        two.run_protocol({**protocol, "protocol_id": "test-phases"})
    assert "several breathing phases" in str(e.value.detail) and {"SpinalCord_c30", "SPINALCORD_C40"} <= set(str(e.value.detail).replace(",", " ").replace("(", " ").replace(")", " ").split())
    # an exact name wins over the phases; the protocol's own name counts as a candidate; the suffix is two digits
    exact = two.derive({"op": "union", "name": "SpinalCord", "sources": ["OAR"]})
    assert exact.run_protocol({**protocol, "protocol_id": "test-exact"}).result.aliased == {"Cord": "SpinalCord"}
    lower = {n.lower(): n for n in ["SpinalCord", "SpinalCord_c30", "Cord_c10", "PTV_c3"]}
    assert _one_phase("Cord", ["SpinalCordX"], lower) == "Cord_c10"
    assert _one_phase("PTV", [], lower) is None
    assert _one_phase("Liver", ["Liver_c"], lower) is None


def test_a_protocol_names_every_structure_the_geometry_lacks_before_planning(rx):
    """A protocol needs a derivation's sources, its target, its objectives' structures and its trade-offs': without
    them the run is refused before anything is derived, every gap named once with what needs it and the aliases tried.
    A goal's structure is not needed (``Liver`` here is reported, not failed)."""
    from radiarch.models.protocol import PlanningProtocol
    from radiarch.services.autoplan import load_protocol, missing_structures
    from radiarch.services.geometry import GeometryService

    protocol = {**PROTOCOL, "protocol_id": "test-missing", "structure_aliases": {"Cord": ["SpinalCord", "OAR"], "Lung_L": ["Lung_L", "LLung"]},
                "structures": PROTOCOL["structures"] + [{"op": "union", "name": "Lungs", "sources": ["Lung_L", "Lung_R"]},
                                                        {"op": "subtract", "name": "Lungs-PTV", "source": "Lungs", "sources": ["PTV"]}],
                "extra_objectives": PROTOCOL["extra_objectives"] + [{"type": "DMax", "structure_name": "Heart", "dose_gy": 1.0, "weight": 10.0}]}
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    before = len(GeometryService().store._load_index())
    with pytest.raises(RadiarchError) as e:
        geo.run_protocol(protocol)
    detail = str(e.value.detail)
    assert "'Lung_L' (for the union that makes 'Lungs'; no structure matches it or its aliases LLung)" in detail
    assert "'Lung_R' (for the union that makes 'Lungs')" in detail and "'Heart' (for an extra objective)" in detail
    assert "Lungs-PTV" not in detail and "Liver" not in detail and "The geometry has OAR, PTV" in detail
    assert len(GeometryService().store._load_index()) == before         # refused before the aliases' and derivations' geometry

    p = PlanningProtocol(**protocol)
    # names match without case; a structure a derivation makes is there for the later ones; the target counts after them
    assert missing_structures(p, ["ptv", "LUNG_L", "lung_r", "HEART"]) == {}
    assert missing_structures(PlanningProtocol(**{**protocol, "prescription": {**protocol["prescription"], "target": "PTV2"},
                                                  "goals": [{"structure": "PTV2", "metric": "D95", "op": ">=", "gy": 2.0}]}),
                              ["PTV", "Lung_L", "Lung_R", "Heart"]) == {"PTV2": ["the main target"]}
    # the shipped multi-criteria protocol on a phase CT without lungs or cord: its trade-offs and hard constraints too
    mco = load_protocol("demo-lung-imrt-mco")
    assert missing_structures(mco, ["GTV", "Heart", "Esophagus"]) == {
        "Lung_L": ["the union that makes 'Lungs'"], "Lung_R": ["the union that makes 'Lungs'"],
        "SpinalCord": ["a trade-off", "a hard constraint"]}


def test_a_protocol_digest_ignores_unset_directional_margins():
    """A structure step without directional margins keeps the digest it had before they existed, so repeated protocol
    runs still find their cached results; one with them gets its own."""
    import hashlib
    import json

    from radiarch.services.autoplan import PROTOCOLS_DIR, load_protocol

    for path in sorted(PROTOCOLS_DIR.glob("*.json")):
        proto = load_protocol(path.stem)
        data = proto.model_dump(mode="json")
        if data.get("mco") is None:
            data.pop("mco", None)
        for op in data["structures"]:
            assert op.pop("directional_mm") is None
        assert proto.digest() == hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest(), path.stem
    proto = load_protocol("lung-60gy-30fx-vmat")
    first = proto.structures[0]
    if first.op in ("expand", "erode"):
        moved = proto.model_copy(update={"structures": [first.model_copy(update={"margin_mm": None, "directional_mm": {"superior": 5.0}}),
                                                        *proto.structures[1:]]})
        assert moved.digest() != proto.digest()
