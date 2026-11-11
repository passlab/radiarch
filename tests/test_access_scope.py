"""Stored results scoped by the studies a user may see (ADR 0021).

With ``RADIARCH_ACCESS_URL`` set, radiarch asks the host whether a user may see a study (``GET ?user=&study=`` with the
proxy's secret) and serves a result only to a user who may see every study it traces to. A refused id answers as an
unknown one; listings drop what the user may not see; a write that builds on a refused result is refused; a request
without a user is refused; the cache stays shared. Without the setting nothing changes (every other test).
"""

from __future__ import annotations

import os

import httpx
import pytest

from test_r6_rt_export_service import _loaded_ct, env  # noqa: F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)
from test_r10_protocols import PROTOCOL
from test_r11_pareto import rx  # noqa: F401  (the app in this process through the SDK)

USER, SECRET = "X-Forwarded-User", "X-Proxy-Secret"
STUDY_A, STUDY_B = "1.2.826.0.1.3680043.8.498.7001", "1.2.826.0.1.3680043.8.498.7002"
API = "/api/v1"


class Host:
    """A fake access endpoint: ``allowed`` holds (user, study) pairs; every call is recorded."""

    def __init__(self) -> None:
        self.allowed: set = set()
        self.calls: list = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        user, study = request.url.params.get("user"), request.url.params.get("study")
        self.calls.append((user, study, request.headers.get(SECRET)))
        if self.down == "unreachable":
            raise httpx.ConnectError("no route to host")
        if self.down:
            return httpx.Response(500)
        if request.headers.get(SECRET) != "s3cret":
            return httpx.Response(401)
        return httpx.Response(200 if (user, study) in self.allowed else 403)


@pytest.fixture()
def host(env, monkeypatch):  # noqa: F811
    """Each geometry gets the study it was built from; the access check off until ``on`` is called."""
    from radiarch.config import get_settings
    from radiarch.services import access
    from radiarch.services.geometry import GeometryService

    def load(self, req):
        loaded = _loaded_ct()
        loaded.ct.studyInstanceUID = req.patient_ref.dicom_study_uid
        return loaded

    monkeypatch.setattr(GeometryService, "_load", load)
    fake = Host()
    monkeypatch.setattr(access, "_http", lambda: httpx.Client(transport=httpx.MockTransport(fake)))

    def on(**allowed):
        fake.allowed = {(u, s) for u, studies in allowed.items() for s in studies}
        monkeypatch.setenv("RADIARCH_TRUSTED_USER_HEADER", USER)
        monkeypatch.setenv("RADIARCH_TRUSTED_PROXY_SECRET", "s3cret")
        monkeypatch.setenv("RADIARCH_ACCESS_URL", "http://host.test/access")
        get_settings.cache_clear()
        access.AccessService.forget()

    fake.on = on
    access.AccessService.forget()
    yield fake
    access.AccessService.forget()


def _as(user):
    return {USER: user, SECRET: "s3cret"} if user else {}


def test_a_result_is_read_only_by_a_user_who_may_see_its_studies(rx, host):  # noqa: F811
    # built with the check off (the SDK names no user); A and B are two patients' studies
    geo_a = rx.build_geometry(STUDY_A, hu_model="LINEAR")
    geo_b = rx.build_geometry(STUDY_B, hu_model="LINEAR")
    run = geo_a.run_protocol(PROTOCOL)
    exp = run.export(label="RESEARCH")
    joined = rx.http.post(f"{API}/four-d/average", json={"reference_geometry_id": geo_a.id, "phase_geometry_ids": [geo_a.id, geo_b.id]})
    assert joined.status_code == 200, joined.text
    joined_id = joined.json()["geometry_id"]
    host.on(alice=[STUDY_A], bob=[STUDY_A, STUDY_B])

    def get(path, user):
        return rx.http.get(f"{API}{path}", headers=_as(user))

    # reads by id: alice may see A; carol may see nothing, and her refusal reads as an unknown id
    reads = [f"/geometry/{geo_a.id}", f"/beam-model/{run.beam_model_id}", f"/dose/{run.result.dose_id}",
             f"/optimize/{run.result.optimization_id}", f"/optimize/sequences/{run.sequence_id}", f"/protocols/runs/{run.id}",
             f"/rt/exports/{exp.id}", f"/rt/exports/{exp.id}/files/RP.dcm", f"/lineage/dose/{run.result.dose_id}",
             f"/lineage/geometry/{geo_a.id}/attribution"]
    for path in reads:
        assert get(path, "alice").status_code == 200, path
        refused = get(path, "carol")
        assert (refused.status_code, refused.json()) == (404, {"detail": "not found"}), path
    unknown = get("/geometry/00000000-0000-0000-0000-000000000000", "alice")
    assert (unknown.status_code, unknown.json()) == (404, {"detail": "not found"})

    # a result that joins two studies is read only by a user who may see both
    assert get(f"/geometry/{joined_id}", "alice").status_code == 404
    assert get(f"/geometry/{joined_id}", "bob").status_code == 200
    assert get(f"/geometry/{geo_b.id}", "alice").status_code == 404

    # listings drop what the user may not see
    assert [e["export_id"] for e in get(f"/rt/exports?study_instance_uid={exp.result.study_instance_uid}", "alice").json()] == [exp.id]
    assert get(f"/rt/exports?study_instance_uid={exp.result.study_instance_uid}", "carol").json() == []
    below = lambda user: {n["ref"]["id"] for n in get(f"/lineage/geometry/{geo_a.id}/descendants", user).json()}  # noqa: E731
    assert joined_id in below("bob") and joined_id not in below("alice") and run.beam_model_id in below("alice")
    assert get(f"/lineage/geometry/{geo_a.id}/descendants", "carol").status_code == 404

    # writes: building on a refused result, or on a study the user may not see, is refused as unknown
    body = {"geometry_id": geo_a.id, "protocol": {**PROTOCOL, "protocol_id": "test-static"}}
    assert rx.http.post(f"{API}/protocols/run", json=body, headers=_as("carol")).status_code == 404
    build = {"patient_ref": {"dicom_study_uid": STUDY_B}, "hu_to_density_model": "LINEAR"}
    assert rx.http.post(f"{API}/geometry/build", json=build, headers=_as("alice")).json() == {"detail": "not found"}
    # the cache stays shared: alice's request for the same inputs is the run made before, with its first requester
    again = rx.http.post(f"{API}/protocols/run", json=body, headers=_as("alice"))
    assert again.status_code == 200 and again.json()["run_id"] == run.id

    # a file on the server names no study; a request without a user is refused; open routes stay open
    nrrd = {"patient_ref": {"nrrd_ct_path": "/etc/passwd"}, "hu_to_density_model": "LINEAR"}
    refused = rx.http.post(f"{API}/geometry/build", json=nrrd, headers=_as("bob"))
    assert refused.status_code == 422 and "nrrd_ct_path" in refused.json()["detail"]
    assert get(f"/geometry/{geo_a.id}", None).status_code == 401
    for path in ("/protocols", "/beam-model/machines", "/evaluate/goal-templates", "/lineage/capability", "/jobs/no-such-job"):
        assert get(path, None).status_code in (200, 404), path        # 404: no such job, not a refusal
    assert get("/protocols", None).status_code == 200


def test_the_host_is_asked_once_per_user_and_study_and_a_silent_host_refuses_nothing_silently(rx, host):  # noqa: F811
    geo = rx.build_geometry(STUDY_A, hu_model="LINEAR")
    host.on(alice=[STUDY_A])
    for _ in range(3):
        assert rx.http.get(f"{API}/geometry/{geo.id}", headers=_as("alice")).status_code == 200
    assert host.calls == [("alice", STUDY_A, "s3cret")]                     # kept for access_cache_s, with the proxy's secret

    from radiarch.services.access import AccessService

    for down in (True, "unreachable"):                                       # a 500, and no answer at all
        AccessService.forget()
        host.down = down
        r = rx.http.get(f"{API}/geometry/{geo.id}", headers=_as("alice"))
        assert r.status_code == 503 and r.json() == {"detail": "the access check is unavailable"}
        # meanwhile an unknown id answers as a known one does, so an outage does not tell which ids exist
        assert rx.http.get(f"{API}/geometry/no-such-geometry", headers=_as("alice")).status_code == 503
    # the host is asked about the user exactly as the proxy named them, not the name cleaned for DICOM
    AccessService.forget()
    host.down = False
    assert rx.http.get(f"{API}/geometry/{geo.id}", headers=_as("al=ice")).status_code == 404
    assert host.calls[-1][:2] == ("al=ice", STUDY_A)


def test_a_result_whose_source_is_gone_or_has_no_study_is_read_by_nobody(rx, host, monkeypatch):  # noqa: F811
    from radiarch.services.access import AccessService

    geo = rx.build_geometry(STUDY_A, hu_model="LINEAR")
    host.on(alice=[STUDY_A])
    svc = AccessService()
    assert svc.studies("geometry", geo.id) == {STUDY_A} and svc.visible("alice", "geometry", geo.id)
    assert svc.studies("geometry", "no-such-geometry") is None and not svc.visible("alice", "geometry", "no-such-geometry")
    # a parent that is gone adds an unknown study; a geometry with no study traces to none: nobody may see either
    real = AccessService._lookup
    monkeypatch.setattr(AccessService, "_lookup", staticmethod(lambda kind, vid: ([], [("geometry", "gone")]) if vid == "orphan"
                                                               else ([None], []) if vid == "studyless" else real(kind, vid)))
    AccessService.forget()
    assert AccessService().studies("dose", "orphan") == {""} and not AccessService().visible("alice", "dose", "orphan")
    assert AccessService().studies("geometry", "studyless") == frozenset() and not AccessService().visible("alice", "geometry", "studyless")


def test_every_route_is_open_or_checked_and_every_id_it_takes_is_known():
    """A new route or request field that names a result must be added to the check (or listed as not naming one)."""
    import inspect
    import typing

    from fastapi.routing import APIRoute
    from pydantic import BaseModel

    from radiarch.api.access import OPEN_ROUTES
    from radiarch.app import create_app
    from radiarch.config import get_settings
    from radiarch.services.access import BODY_KINDS, BODY_PATHS, BODY_STUDIES, BODY_UNCHECKED, PATH_KINDS, PATH_UNCHECKED, QUERY_UNCHECKED

    def types(a):
        args = typing.get_args(a)
        return [a] if not args else [t for x in args for t in types(x)]

    def fields(model, seen):
        if model in seen:
            return set()
        seen.add(model)
        out = set()
        for name, f in model.model_fields.items():
            out.add(name)
            if f.alias and f.alias != name:                                   # a body names the field by its alias
                out.add(f.alias)
            for t in types(f.annotation):
                if inspect.isclass(t) and issubclass(t, BaseModel):
                    out |= fields(t, seen)
        return out

    prefix = get_settings().api_prefix
    known_body = set(BODY_KINDS) | set(BODY_STUDIES) | set(BODY_PATHS) | set(BODY_UNCHECKED)
    from radiarch.services.access import is_server_path
    templates, unknown = set(), []
    for r in create_app().routes:
        if not isinstance(r, APIRoute) or not r.path.startswith(prefix) or r.path == f"{prefix}/info":
            continue
        template = r.path[len(prefix):]
        for method in r.methods:
            templates.add((method, template))
            if (method, template) in OPEN_ROUTES:
                continue
            unknown += [f"{method} {template}: path {p}" for p in r.param_convertors if p not in PATH_KINDS and p not in PATH_UNCHECKED]
            unknown += [f"{method} {template}: query {q.alias}" for q in r.dependant.query_params if q.alias not in QUERY_UNCHECKED]
            if r.body_field is not None:
                for t in types(r.body_field.type_):
                    if inspect.isclass(t) and issubclass(t, BaseModel):
                        for name in fields(t, set()):
                            looks_like = name.endswith(("_id", "_ids", "_uid", "_uids")) or name in ("id", "from_state") or \
                                bool({"path", "dir", "directory", "root", "file", "uri", "url"} & set(name.split("_")))
                            if looks_like and name not in known_body and not is_server_path(name):
                                unknown.append(f"{method} {template}: body {name}")
    assert unknown == []
    assert OPEN_ROUTES <= templates                                           # no open route that does not exist


def test_no_body_and_no_id_gets_past_the_check(rx, host, monkeypatch, tmp_path):  # noqa: F811
    """The review's ways round the check: a body the header does not call JSON, ids that are paths, files on the
    server, a state name that is a path, a body nested too deep, and a session's file name."""
    import json

    from radiarch.services.access import AccessService, NotVisible

    geo_a = rx.build_geometry(STUDY_A, hu_model="LINEAR")
    geo_b = rx.build_geometry(STUDY_B, hu_model="LINEAR")
    run_b = geo_b.run_protocol(PROTOCOL)
    dose_b = rx.http.get(f"{API}/dose/{run_b.result.dose_id}").json()["dose_grid_uri"]
    host.on(alice=[STUDY_A], bob=[STUDY_A, STUDY_B])
    body = json.dumps({"geometry_id": geo_b.id, "protocol": {**PROTOCOL, "protocol_id": "test-static"}})
    for content_type in (None, "Application/JSON", "application/vnd.x+json", "text/plain"):
        headers = {**_as("alice"), **({"Content-Type": content_type} if content_type else {})}
        r = rx.http.post(f"{API}/protocols/run", content=body, headers=headers)
        assert (r.status_code, r.json()) == (404, {"detail": "not found"}), content_type

    # an id is a plain token: a path in an id names nothing
    phases = {"reference_geometry_id": geo_a.id, "phase_geometry_ids": [f"../geometry/{geo_a.id}", geo_a.id]}
    assert rx.http.post(f"{API}/four-d/average", json=phases, headers=_as("alice")).status_code == 404
    assert rx.http.get(f"{API}/geometry/..", headers=_as("alice")).status_code == 404
    with pytest.raises(NotVisible):
        AccessService().check("alice", {}, {"state_id": f"../../{geo_b.id}/states/balance"})
    with pytest.raises(NotVisible):
        AccessService().check("alice", {"mco_id": "x", "state_id": "../y"}, None)

    # a file on the server, under any name that says so, is refused
    for a in ({"geometry_id": geo_a.id, "dose_ref_uri": dose_b, "prescription_gy": 2.0},
              {"geometry_id": geo_a.id, "dose_id": run_b.result.dose_id, "prescription_gy": 2.0,
               "gamma": {"reference_dose_uri": dose_b}}):
        r = rx.http.post(f"{API}/evaluate/compare", json={"a": a, "evaluation_id_b": "x"}, headers=_as("alice"))
        assert r.status_code in (404, 422) and r.status_code != 200, r.text
    r = rx.http.post(f"{API}/evaluate/compare", json={"a": {"geometry_id": geo_a.id, "dose_ref_uri": dose_b, "prescription_gy": 2.0},
                                                      "b": {"geometry_id": geo_a.id, "dose_ref_uri": dose_b, "prescription_gy": 2.0}},
                     headers=_as("alice"))
    assert r.status_code == 422 and "dose_ref_uri" in r.json()["detail"]

    # a body nested deeper than any request model is refused, not a server error
    deep = '{"a":' * 1500 + "1" + "}" * 1500
    r = rx.http.post(f"{API}/protocols/run", content=deep, headers={**_as("alice"), "Content-Type": "application/json"})
    assert r.status_code in (400, 404, 422)

    # sessions need a user now, and keep a client's file name inside their folder
    from radiarch.api.routes import sessions

    monkeypatch.setattr(sessions, "_session_dir", lambda sid: str(tmp_path / "sessions" / sid))   # the module fixes its folder at import
    files = {"file": ("../../escaped.dcm", b"x", "application/dicom")}
    assert rx.http.post(f"{API}/sessions", files=files).status_code == 401

    made = rx.http.post(f"{API}/sessions", files=files, headers=_as("bob"))
    assert made.status_code == 200
    folder = sessions._session_dir(made.json()["id"])
    assert sorted(os.listdir(folder)) == ["escaped.dcm"] and not (tmp_path / "escaped.dcm").exists()
    rx.http.delete(f"{API}/sessions/{made.json()['id']}", headers=_as("bob"))


def test_a_result_that_joins_another_study_through_a_plan_or_a_gamma_is_read_by_nobody_else(rx, host):  # noqa: F811
    """An imported RT Plan brings the study it was written in; a gamma comparison brings its reference dose."""
    import io
    import zipfile

    from radiarch.models.evaluation import EvaluationRequest
    from radiarch.services.evaluation import EvaluationService

    geo_a = rx.build_geometry(STUDY_A, hu_model="LINEAR")
    geo_b = rx.build_geometry(STUDY_B, hu_model="LINEAR")
    run_a, run_b = geo_a.run_protocol(PROTOCOL), geo_b.run_protocol(PROTOCOL)
    rp = next(o["path"] for o in rx.http.get(f"{API}/rt/exports/{run_b.export(label='RESEARCH').id}").json()["objects"] if o["kind"] == "RTPLAN")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(rp, "RP.dcm")
    upload = rx.http.post(f"{API}/uploads/dicom", files={"file": ("p.zip", buf.getvalue(), "application/zip")}).json()["upload_id"]
    imported = rx.http.post(f"{API}/beam-model/import", json={"geometry_id": geo_a.id, "upload_id": upload, "strict_frame_of_reference": False,
                                                             "machine_model_id": "test-120"})
    assert imported.status_code == 200, imported.text
    gamma = EvaluationService().run(EvaluationRequest(geometry_id=geo_a.id, dose_id=run_a.result.dose_id, prescription_gy=2.0,
                                                      gamma={"reference_dose_id": run_b.result.dose_id}))
    assert gamma.gamma.reference_dose_id == run_b.result.dose_id
    host.on(alice=[STUDY_A], bob=[STUDY_A, STUDY_B])
    for path in (f"/beam-model/{imported.json()['beam_model_id']}", f"/evaluate/{gamma.evaluation_id}", f"/uploads/{upload}"):
        assert rx.http.get(f"{API}{path}", headers=_as("alice")).status_code == 404, path
        assert rx.http.get(f"{API}{path}", headers=_as("bob")).status_code == 200, path
    # and alice may not import B's plan herself: the upload's study is B
    again = {"geometry_id": geo_a.id, "upload_id": upload, "strict_frame_of_reference": False, "machine_model_id": "test-120"}
    assert rx.http.post(f"{API}/beam-model/import", json=again, headers=_as("alice")).status_code == 404


def test_an_arc_plan_brings_its_beam_models_study_and_the_host_is_not_taken_down_by_one_request(rx, host, monkeypatch):  # noqa: F811
    """The second review: an arc plan made from another study's beam model; a malformed study UID; a cached geometry
    whose CT is another study's; names of shipped files that are paths."""
    from radiarch.models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from radiarch.models.dose import EngineSpec
    from radiarch.models.optimization import ObjectiveSpec, OptimizationRunRequest, SolverConfig
    from radiarch.models.vmat import ArcRequest, ArcSpec, sector_beams
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.geometry import GeometryService
    from radiarch.services.optimization import OptimizationService
    from radiarch.services.vmat import VMATService

    geo_a = rx.build_geometry(STUDY_A, hu_model="LINEAR")
    geo_b = rx.build_geometry(STUDY_B, hu_model="LINEAR")
    arc = ArcSpec(arc_id="A1", start_deg=300, stop_deg=60, direction="CW", sectors=4, control_point_spacing_deg=4.0)
    bm_b = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo_b.id, modality=Modality.photon_imrt, machine_model_id="synthetic-120",
        beam_set=BeamSetSpec(isocenter_mm=(10.0, 0.0, 0.0),
                             beams=[BeamSpec(beam_id=b, gantry_deg=g, collimator_deg=col) for b, g, _, col in sector_beams([arc])]),
        delivery_params=DeliveryParams(jaw_opening_mm=(40.0, 40.0), beamlet_size_mm=(5.0, 5.0))))
    objectives = [ObjectiveSpec(type="DUniform", structure_name="PTV", dose_gy=2.0, weight=1.0),
                  ObjectiveSpec(type="DMax", structure_name="OAR", dose_gy=0.8, weight=1.0)]
    opt = OptimizationService().run(OptimizationRunRequest(                  # A's CT with B's beam model
        geometry_id=geo_a.id, beam_model_id=bm_b.beam_model_id, dose_engine=EngineSpec(name="pb"),
        objectives=objectives, solver=SolverConfig(method="L-BFGS-B", max_iterations=30)))
    arcs = VMATService().arcs(opt.optimization_id, ArcRequest(objectives=objectives, arcs=[arc], max_iterations=30))

    # a geometry stored before the check was on, keyed by study A but holding B's CT (a data-root read ignores the study)
    def load(self, req):
        loaded = _loaded_ct()
        loaded.ct.studyInstanceUID = STUDY_B
        return loaded

    monkeypatch.setattr(GeometryService, "_load", load)
    legacy = {"patient_ref": {"dicom_study_uid": STUDY_A, "ct_series_uid": "9.9.9"}, "hu_to_density_model": "LINEAR"}
    assert rx.http.post(f"{API}/geometry/build", json=legacy).status_code in (200, 202)
    host.on(alice=[STUDY_A], bob=[STUDY_A, STUDY_B])

    for path in (f"/beam-model/{arcs.beam_model_id}", f"/dose/{arcs.dose_id}", f"/beam-model/{arcs.beam_model_id}/artifact",
                 f"/optimize/arcs/{arcs.vmat_id}"):
        assert rx.http.get(f"{API}{path}", headers=_as("alice")).status_code == 404, path
        assert rx.http.get(f"{API}{path}", headers=_as("bob")).status_code == 200, path
    below = {n["ref"]["id"] for n in rx.http.get(f"{API}/lineage/geometry/{geo_a.id}/descendants", headers=_as("alice")).json()}
    assert arcs.beam_model_id not in below and arcs.dose_id not in below
    assert rx.http.post(f"{API}/geometry/build", json=legacy, headers=_as("alice")).json() == {"detail": "not found"}

    # a study UID that is not one asks no host; a host's 400 refuses that request only
    calls = len(host.calls)
    bad = {"patient_ref": {"dicom_study_uid": "x" * 200}, "hu_to_density_model": "LINEAR"}
    assert rx.http.post(f"{API}/geometry/build", json=bad, headers=_as("mallory")).status_code == 404
    assert len(host.calls) == calls
    real = host.__call__
    monkeypatch.setattr(Host, "__call__", lambda self, r: httpx.Response(400) if r.url.params.get("study") == "1.2.3.400"
                        else real(r))
    odd = {"patient_ref": {"dicom_study_uid": "1.2.3.400"}, "hu_to_density_model": "LINEAR"}
    assert rx.http.post(f"{API}/geometry/build", json=odd, headers=_as("mallory")).status_code == 404
    assert rx.http.get(f"{API}/geometry/{geo_a.id}", headers=_as("alice")).status_code == 200      # not taken down

    # the names of shipped files are names, not paths
    for body in ({"geometry_id": geo_a.id, "beam_model_id": bm_b.beam_model_id, "engine": {"name": "mcsquare", "params": {"mcsquare_dir": "/tmp"}}},
                 {"geometry_id": geo_a.id, "beam_model_id": bm_b.beam_model_id, "engine": {"name": "mcsquare", "params": {"bdl": "/etc/x"}}}):
        r = rx.http.post(f"{API}/dose/compute", json=body, headers=_as("bob"))
        assert r.status_code == 422 and "on the server" in r.json()["detail"], r.text
    r = rx.http.post(f"{API}/beam-model/build", json={"geometry_id": geo_a.id, "machine_model_id": "../../x"}, headers=_as("alice"))
    assert r.status_code == 422 and "machine_model_id" in r.json()["detail"]
