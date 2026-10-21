"""R12: versions with parents, attribution, states and immutability over the real stores,
through the service and the API; the SMIS transformation record; the capability declaration."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from radiarch.models.lineage import KINDS, StateRecord, VersionRef, VersionState
from radiarch.models.rt_export import PrescriptionSpec, RTExportRequest

# the R6 pipeline fixture: a stub CT with PTV and OAR, photon beam model, optimization, apertures
from test_r6_rt_export_service import _photon_pipeline, env  # noqa: F401


def _export(seq):
    from radiarch.services.rt_export import RTExportService

    return RTExportService().export(RTExportRequest(sequence_id=seq.sequence_id, prescription=PrescriptionSpec(dose_gy=2.0, fractions=2),
                                                    objects=["rtstruct", "rtplan", "rtdose"]))


def test_lineage_of_an_export_reaches_the_geometry(env):  # noqa: F811
    from radiarch.services.lineage import LineageError, LineageService

    geo, bm, opt, seq = _photon_pipeline()
    exp = _export(seq)
    svc = LineageService()
    graph = svc.lineage(VersionRef(kind="rt_export", id=exp.export_id))
    kinds = {n.ref.kind for n in graph.nodes}
    assert kinds == {"rt_export", "beam_model", "dose", "geometry", "sequence", "optimization"}
    assert graph.roots == [VersionRef(kind="geometry", id=geo.geometry_id)] and not graph.missing
    by_key = {n.ref.key: n for n in graph.nodes}
    # the aperture beam model and the segment dose derive from the sequence; the sequence from the optimization and the open-field model
    assert VersionRef(kind="sequence", id=seq.sequence_id) in by_key[f"beam_model:{seq.beam_model_id}"].parents
    assert VersionRef(kind="sequence", id=seq.sequence_id) in by_key[f"dose:{seq.dose_id}"].parents
    s = by_key[f"sequence:{seq.sequence_id}"]
    assert {p.key for p in s.parents} == {f"optimization:{opt.optimization_id}", f"beam_model:{bm.beam_model_id}"}
    assert by_key[f"optimization:{opt.optimization_id}"].attribution.engine_name == "analytic"
    # attribution: capability, machine, HU model and dataset, inherited from the geometry
    a = by_key[f"rt_export:{exp.export_id}"].attribution
    assert a.capability_id == "radiarch" and a.capability_version and a.intended_use.startswith("RESEARCH USE ONLY")
    assert a.dataset.study_instance_uid == "1.2.826.0.1.3680043.8.498.6000" and a.dataset.patient_id == "R6-SVC"
    assert by_key[f"beam_model:{bm.beam_model_id}"].attribution.machine_model_id == "test-120"
    assert by_key[f"geometry:{geo.geometry_id}"].attribution.hu_model == "LINEAR"
    assert by_key[f"dose:{seq.dose_id}"].attribution.hu_model == "LINEAR"
    # descendants of the geometry: everything else
    desc = {n.ref.kind for n in svc.descendants(VersionRef(kind="geometry", id=geo.geometry_id))}
    assert desc >= {"beam_model", "optimization", "sequence", "dose", "rt_export"}
    with pytest.raises(LineageError, match="not found"):
        svc.lineage(VersionRef(kind="dose", id="nope"))


def test_states_and_immutability(env):  # noqa: F811
    from radiarch.services.geometry import GeometryService
    from radiarch.services.lineage import LineageError, LineageService, VersionLocked

    geo, bm, opt, seq = _photon_pipeline()
    svc = LineageService()
    dose = VersionRef(kind="dose", id=seq.dose_id)
    assert svc.status(dose).state is VersionState.draft and not svc.status(dose).locked

    # radiarch records approvals, it does not grant them
    with pytest.raises(ValueError, match="records approvals"):
        StateRecord(state=VersionState.approved, actor="physicist", authority="radiarch")
    with pytest.raises(ValueError, match="authority"):
        StateRecord(state=VersionState.approved)
    st = svc.transition(dose, StateRecord(state=VersionState.approved, actor="physicist:ab", authority="smis-ois", reference="Task/42"))
    assert st.state is VersionState.approved and st.locked and st.history[-1].at is not None

    # the approved dose and everything it derives from are immutable
    for ref in (dose, VersionRef(kind="geometry", id=geo.geometry_id), VersionRef(kind="beam_model", id=seq.beam_model_id),
                VersionRef(kind="sequence", id=seq.sequence_id), VersionRef(kind="optimization", id=opt.optimization_id)):
        assert svc.is_locked(ref), ref.key
        with pytest.raises(VersionLocked):
            svc.assert_deletable(ref)
    # a sibling that nothing approved derives from stays deletable
    other = GeometryService().derive(geo.geometry_id, _expand_request())
    assert not svc.is_locked(VersionRef(kind="geometry", id=other.geometry_id))

    # the state machine: approved → draft is not a transition; superseded needs the successor; retired is final
    with pytest.raises(LineageError, match="cannot become"):
        svc.transition(dose, StateRecord(state=VersionState.draft))
    with pytest.raises(ValueError, match="names the version"):
        StateRecord(state=VersionState.superseded)
    with pytest.raises(LineageError, match="not found"):
        svc.transition(dose, StateRecord(state=VersionState.superseded, superseded_by=VersionRef(kind="dose", id="later")))
    st = svc.transition(dose, StateRecord(state=VersionState.superseded, superseded_by=VersionRef(kind="geometry", id=other.geometry_id)))
    assert st.state is VersionState.superseded and st.locked              # once approved, always immutable
    st = svc.transition(dose, StateRecord(state=VersionState.retired, note="course closed"))
    assert st.state is VersionState.retired and len(st.history) == 3 and st.locked
    with pytest.raises(LineageError, match="cannot become"):
        svc.transition(dose, StateRecord(state=VersionState.approved, actor="x", authority="smis-ois"))
    # the record survives a new service instance (one JSON file under the artifact directory)
    assert LineageService().status(dose).state is VersionState.retired
    assert (Path(env) / "lineage" / "states.json").is_file()


def _expand_request():
    from radiarch.models.geometry import GeometryDeriveRequest, StructureOperation

    return GeometryDeriveRequest(operations=[StructureOperation(op="expand", name="PTV_5", source="PTV", margin_mm=5.0)])


def test_derivation_record_in_the_smis_shape(env):  # noqa: F811
    from radiarch.services.lineage import LineageService

    geo, bm, opt, seq = _photon_pipeline()
    exp = _export(seq)
    rec = LineageService().derivation_record(VersionRef(kind="rt_export", id=exp.export_id), inputs=[{"dataset_id": "lung-mock-site", "version": 3}])
    tr = rec.transformation
    assert tr["kind"] == "computation" and tr["actor"] == {"kind": "tool", "id": "radiarch", "version": tr["tool"]["version"]}
    assert tr["identifiability"] == "pseudonymized" and tr["started"] <= tr["finished"] and tr["finished"].endswith("Z")
    assert tr["parameters"]["engine_name"] == "analytic" and tr["parameters"]["roots"] == [f"geometry:{geo.geometry_id}"]
    assert rec.inputs == [{"dataset_id": "lung-mock-site", "version": 3}]
    written = rec.outputs["objects_written"]
    assert {o["modality"] for o in written} == {"RTSTRUCT", "RTPLAN", "RTDOSE"} and all(o["instance_count"] == 1 for o in written)
    assert all(o["study_uid"] == exp.study_instance_uid for o in written)
    # the record validates against the SMIS manifest schema when the schema is at hand
    schema_path = os.environ.get("SMIS_MANIFEST_SCHEMA", "/home/yyan7/SMIS/smis/packages/smis-schemas/schemas/manifest/v1.schema.json")
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None and Path(schema_path).is_file():
        schema = json.loads(Path(schema_path).read_text())
        sub = {"$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"), "$defs": schema["$defs"], "$ref": "#/$defs/derivation"}
        jsonschema.validate(json.loads(rec.model_dump_json(exclude_none=True)), sub)


def test_capability_declaration(env):  # noqa: F811
    from radiarch.services.lineage import LineageService

    cap = LineageService().capability()
    assert cap["capability_id"] == "radiarch" and cap["actor_kind"] == "tool" and "RTPLAN" in cap["writes"]
    assert any(e["name"] == "analytic" for e in cap["engines"]) and "synthetic-120" in cap["machines"]["photon"]
    assert "rtog-0617" in cap["goal_templates"] and cap["object_labeling"]["ApprovalStatus"] == "UNAPPROVED"
    assert set(cap["states"]["values"]) == {"draft", "approved", "superseded", "retired"} and "approval" in cap["never"][1]


def test_lineage_endpoints(env, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.core import store as store_module

    geo, bm, opt, seq = _photon_pipeline()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/lineage/capability").json()["capability_id"] == "radiarch"
        g = client.get(f"/api/v1/lineage/dose/{seq.dose_id}")
        assert g.status_code == 200 and {n["ref"]["kind"] for n in g.json()["nodes"]} == {"dose", "geometry", "beam_model", "sequence", "optimization"}
        assert client.get(f"/api/v1/lineage/geometry/{geo.geometry_id}/descendants").status_code == 200
        a = client.get(f"/api/v1/lineage/dose/{seq.dose_id}/attribution").json()
        assert a["engine_name"] == "analytic" and a["dataset"]["patient_id"] == "R6-SVC"
        d = client.get(f"/api/v1/lineage/dose/{seq.dose_id}/derivation", params={"dataset_id": "ds", "version": 1})
        assert d.status_code == 200 and d.json()["transformation"]["kind"] == "computation" and d.json()["outputs"] is None
        assert client.get(f"/api/v1/lineage/dose/{seq.dose_id}/state").json()["state"] == "draft"
        r = client.post(f"/api/v1/lineage/dose/{seq.dose_id}/state", json={"state": "approved", "actor": "physician:cd", "authority": "smis-ois"})
        assert r.status_code == 200 and r.json()["locked"] is True
        # approval makes the whole chain immutable at the delete routes
        assert client.delete(f"/api/v1/dose/{seq.dose_id}").status_code == 409
        assert client.delete(f"/api/v1/geometry/{geo.geometry_id}").status_code == 409
        assert client.delete(f"/api/v1/beam-model/{seq.beam_model_id}").status_code == 409
        assert client.delete(f"/api/v1/optimize/{opt.optimization_id}").status_code == 409
        assert client.post(f"/api/v1/lineage/dose/{seq.dose_id}/state", json={"state": "draft"}).status_code == 409
        assert client.post(f"/api/v1/lineage/dose/{seq.dose_id}/state", json={"state": "approved", "actor": "x", "authority": "radiarch"}).status_code == 422
        assert client.get("/api/v1/lineage/dose/missing").status_code == 404
        assert client.get("/api/v1/lineage/thing/x").status_code == 422
        # a draft with nothing approved downstream can still go
        other = client.post(f"/api/v1/geometry/{geo.geometry_id}/derive", json=json.loads(_expand_request().model_dump_json())).json()
        assert client.delete(f"/api/v1/geometry/{other['geometry_id']}").status_code == 204
    store_module.reset_store()


def test_every_kind_is_listed():
    assert set(KINDS) == {"geometry", "beam_model", "influence", "dose", "optimization", "sequence", "bao", "evaluation", "rt_export", "plan"}
