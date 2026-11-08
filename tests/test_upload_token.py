"""An upload token per push (ADR 0020).

The host issues a token for one user's upload; the viewer sends it in ``X-Upload-Authorization``, and radiarch passes
it to the archive as the push's Authorization, as given, instead of its own credential. The token is never kept: not
in the export's files, its record, the response or a log line, and an error that would quote it names it
``[upload token]``. With ``upload_token_required`` a push without a token is refused (422) before anything is written,
an export without push still works, and a plan job pushes nothing. A token with a username is refused. The fake STOW-RS
server of test_dicomweb_push_auth plays the archive.
"""

from __future__ import annotations

from unittest import mock

import pytest
from loguru import logger

from radiarch.adapters import dicomweb as dw
from radiarch.adapters.dicomweb import DICOMwebNotifier, DICOMwebPushError

from test_dicomweb_push_auth import _instance, _Server, server  # noqa: F401  (the fake archive)
from test_r6_rt_export_service import _photon_pipeline, env  # noqa: F401  (stub CT, the test machine and engines)
from test_r11_pareto import rx  # noqa: F401  (the app in this process through the SDK)

pytest.importorskip("dicomweb_client")

SECRET = "tok-upload-7f3a9c"
TOKEN = f"Bearer {SECRET}"                  # the fake archive takes "Bearer tok…"
HEADER = "X-Upload-Authorization"


def _own_credential(monkeypatch, server):  # noqa: F811
    """Radiarch's own client-credentials token for the fake archive: a token request shows whether it was used."""
    from radiarch.config import get_settings

    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", server.url)
    monkeypatch.setenv("RADIARCH_DICOMWEB_TOKEN_URL", f"{server.url}/token")
    monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_ID", "radiarch")
    monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_SECRET", "s3cret")
    monkeypatch.setattr(dw, "_tokens", {})
    monkeypatch.setattr(dw, "_notifier", None)
    get_settings.cache_clear()


@pytest.fixture()
def api(rx, monkeypatch):  # noqa: F811
    from radiarch.api.routes import rt as routes

    routes._service.cache_clear()
    yield rx.http
    routes._service.cache_clear()


@pytest.fixture()
def log():
    lines = []
    sink = logger.add(lambda m: lines.append(str(m)), level="DEBUG")
    yield lines
    logger.remove(sink)


def _body(seq, **kw):
    return {"sequence_id": seq.sequence_id, "label": "R6TEST", "prescription": {"dose_gy": 2.0, "fractions": 2},
            "objects": ["rtstruct", "rtplan", "rtdose"], **kw}


def _no_trace(root, *texts):
    for f in root.rglob("*"):
        if f.is_file():
            data = f.read_bytes()
            assert not any(t.encode() in data for t in texts), f


def test_the_token_is_the_push_s_authorization_as_given(env, server, monkeypatch):  # noqa: F811
    _own_credential(monkeypatch, server)
    n = DICOMwebNotifier(upload_token=TOKEN)
    assert n.auth == "upload token"
    assert n.store_instances([_instance()], raise_errors=True)
    assert server.auth_headers == [TOKEN] and server.tokens_issued == 0           # radiarch's own token not even fetched
    with pytest.raises(ValueError, match="not both"):
        DICOMwebNotifier(upload_token=TOKEN, username="u", password="p")
    with pytest.raises(ValueError, match="cannot carry") as ei:
        DICOMwebNotifier(upload_token="Bearer x\r\nX-Other: 1")
    assert "X-Other" not in str(ei.value)


def test_an_error_that_quotes_the_token_names_it_upload_token(server, log):  # noqa: F811
    server.echo = True
    n = DICOMwebNotifier(url=server.url, upload_token=TOKEN)
    with pytest.raises(DICOMwebPushError) as ei:
        n.store_instances([_instance()], raise_errors=True)
    assert ei.value.status == 403 and SECRET not in str(ei.value) and "[upload token] is not valid" in str(ei.value)
    assert SECRET not in str(ei.value.details) and ei.value.__suppress_context__
    assert not n.store_instances([_instance()])                     # non-fatal: logged, without the token
    assert any("[upload token]" in line for line in log) and not any(SECRET in line for line in log)


def test_an_export_pushes_with_the_token_and_keeps_no_trace_of_it(env, api, server, monkeypatch, log):  # noqa: F811
    _own_credential(monkeypatch, server)
    _, _, _, seq = _photon_pipeline()
    r = api.post("/api/v1/rt/export", json=_body(seq, push=True), headers={HEADER: TOKEN})
    assert r.status_code == 200, r.text
    exp = r.json()
    assert exp["pushed"] is True and server.auth_headers == [TOKEN] and server.tokens_issued == 0
    assert SECRET not in r.text
    assert any("(upload token auth)" in line for line in log) and not any(SECRET in line for line in log)

    # the stored export pushed again takes the new token it is given
    again = api.post("/api/v1/rt/export", json=_body(seq, push=True), headers={HEADER: "Bearer tok-second"})
    assert again.json()["reused"] and server.auth_headers[-1] == "Bearer tok-second"
    # without a token, radiarch's own credential, as before
    assert api.post("/api/v1/rt/export", json=_body(seq, push=True)).json()["pushed"]
    assert server.auth_headers[-1] == "Bearer tok1" and server.tokens_issued == 1

    # the push route: the token goes to a request's URL; without one that URL gets no credential of radiarch's
    other = _Server()
    try:
        p = api.post(f"/api/v1/rt/exports/{exp['export_id']}/push", json={"url": other.url}, headers={HEADER: TOKEN})
        assert p.status_code == 200 and p.json()["pushed"] == 3 and other.auth_headers == [TOKEN]
        p = api.post(f"/api/v1/rt/exports/{exp['export_id']}/push", json={"url": other.url})
        assert p.json()["http_status"] == 401 and other.auth_headers[-1] is None
    finally:
        other.httpd.shutdown()
    # a token with a username: refused, the token not echoed
    p = api.post(f"/api/v1/rt/exports/{exp['export_id']}/push", json={"username": "u", "password": "p"}, headers={HEADER: TOKEN})
    assert p.status_code == 422 and "not both" in p.text and SECRET not in p.text

    # records pushed with a token
    rec = api.post(f"/api/v1/rt/exports/{exp['export_id']}/records",
                   json={"sessions": [{"fraction_number": 1, "treatment_date": "20261108"}], "push": True}, headers={HEADER: TOKEN})
    assert rec.status_code == 200 and rec.json()["pushed"] and server.auth_headers[-1] == TOKEN

    # nowhere on disk: the objects, the manifests, the stores
    _no_trace(env, SECRET)
    assert not any(SECRET in line for line in log)


def test_a_refused_token_is_reported_as_any_refused_push(env, api, server, monkeypatch):  # noqa: F811
    _own_credential(monkeypatch, server)
    _, _, _, seq = _photon_pipeline()
    server.echo = True
    r = api.post("/api/v1/rt/export", json=_body(seq, push=True), headers={HEADER: TOKEN})
    assert r.status_code == 200 and r.json()["pushed"] is False
    assert "HTTP 403" in r.json()["push_error"] and "[upload token]" in r.json()["push_error"] and SECRET not in r.text
    p = api.post(f"/api/v1/rt/exports/{r.json()['export_id']}/push", json={}, headers={HEADER: TOKEN})
    assert p.json()["http_status"] == 403 and SECRET not in p.text
    _no_trace(env, SECRET)


def test_a_server_that_requires_a_token_refuses_a_push_without_one(env, api, server, monkeypatch):  # noqa: F811
    from radiarch.config import get_settings
    from radiarch.services.rt_export import RTExportService

    _own_credential(monkeypatch, server)
    monkeypatch.setenv("RADIARCH_UPLOAD_TOKEN_REQUIRED", "true")
    get_settings.cache_clear()
    _, _, _, seq = _photon_pipeline()
    exports = RTExportService().base_dir

    r = api.post("/api/v1/rt/export", json=_body(seq, push=True))
    assert r.status_code == 422 and HEADER in r.json()["detail"]
    assert list(exports.iterdir()) == [] and server.auth_headers == []                 # nothing written, nothing sent
    plain = api.post("/api/v1/rt/export", json=_body(seq))                             # an export without push: as before
    assert plain.status_code == 200 and not plain.json()["pushed"]
    eid = plain.json()["export_id"]
    assert api.post("/api/v1/rt/export", json=_body(seq, push=True)).status_code == 422     # the stored export: refused too

    p = api.post(f"/api/v1/rt/exports/{eid}/push", json={})
    assert p.status_code == 422 and server.auth_headers == []
    assert api.post(f"/api/v1/rt/exports/{eid}/push", json={"username": "u", "password": "p"}).status_code == 422
    p = api.post(f"/api/v1/rt/exports/{eid}/push", json={}, headers={HEADER: TOKEN})
    assert p.status_code == 200 and p.json()["pushed"] == 3 and server.auth_headers == [TOKEN]

    session = {"sessions": [{"fraction_number": 1, "treatment_date": "20261108"}]}
    before = sorted(f.name for f in (exports / eid).iterdir())
    assert api.post(f"/api/v1/rt/exports/{eid}/records", json={**session, "push": True}).status_code == 422
    assert sorted(f.name for f in (exports / eid).iterdir()) == before                # no record written
    assert api.post(f"/api/v1/rt/exports/{eid}/records", json=session).status_code == 200
    assert server.tokens_issued == 0


def test_a_plan_job_pushes_nothing_where_a_token_is_required(env, server, monkeypatch, tmp_path):  # noqa: F811
    from radiarch.config import get_settings
    from radiarch.tasks import plan_tasks

    rtdose = tmp_path / "RTDOSE.dcm"
    _instance().save_as(str(rtdose), enforce_file_format=True)
    store = mock.MagicMock()
    store.get_plan.return_value.workflow_id = "photon-ccc"
    monkeypatch.setattr(plan_tasks, "store", store)
    monkeypatch.setattr(plan_tasks, "planner", mock.MagicMock(**{
        "run.return_value": mock.MagicMock(qa_summary={"rtdosePath": str(rtdose)}, artifact_path=None)}))
    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", server.url)
    monkeypatch.setenv("RADIARCH_DICOMWEB_USERNAME", "u")
    monkeypatch.setenv("RADIARCH_DICOMWEB_PASSWORD", "p")
    monkeypatch.setattr(dw, "_notifier", None)
    get_settings.cache_clear()
    plan_tasks.run_plan_job("j1", "p1")
    assert server.auth_headers == ["Basic dTpw"]                                         # not required: pushed, as before

    monkeypatch.setenv("RADIARCH_UPLOAD_TOKEN_REQUIRED", "true")
    get_settings.cache_clear()
    plan_tasks.run_plan_job("j2", "p2")
    assert server.auth_headers == ["Basic dTpw"]
    assert [c.kwargs.get("stage") for c in store.update_job.call_args_list].count("pushing") == 1
