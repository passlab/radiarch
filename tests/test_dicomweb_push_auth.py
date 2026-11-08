"""DICOMweb push with an OAuth2 client-credentials bearer token, and the refusal body of a server that
says no (a research write gateway answers 409 with JSON findings). A local stand-in server plays the
token endpoint and the STOW-RS endpoint."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pydicom
import pytest
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from radiarch.adapters import dicomweb as dw
from radiarch.adapters.dicomweb import ClientCredentialsToken, DICOMwebNotifier, DICOMwebPushError

pytest.importorskip("dicomweb_client")


class _Server:
    def __init__(self):
        self.tokens_issued = 0
        self.auth_headers = []
        self.refuse = False
        self.echo = False               # refuse every push, quoting its Authorization header (a careless gateway)
        self.expires_in = 300
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path == "/token":
                    form = dict(p.split("=", 1) for p in body.decode().split("&"))
                    if form.get("client_secret") != "s3cret":
                        return self._send(401, {"error": "invalid_client"})
                    state.tokens_issued += 1
                    return self._send(200, {"access_token": f"tok{state.tokens_issued}", "expires_in": state.expires_in, "token_type": "Bearer"})
                state.auth_headers.append(self.headers.get("Authorization"))
                auth = self.headers.get("Authorization") or ""
                if state.echo:
                    return self._send(403, {"message": f"{auth} is not valid for this study"})
                if not (auth.startswith("Bearer tok") or auth == "Basic dTpw"):          # a token, or HTTP basic u:p
                    return self._send(401, {"message": "missing or bad token"})
                if state.refuse:
                    return self._send(409, {"message": "batch refused", "target": "lung@v3",
                                            "findings": [{"code": "W031", "severity": "error", "path": "RTPlanLabel",
                                                          "message": "label lacks RESEARCH"}], "failed": ["1.2.3"]})
                return self._send(200, {"00081199": {"vr": "SQ", "Value": []}}, "application/dicom+json")

            def _send(self, code, obj, ctype="application/json"):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture()
def server():
    s = _Server()
    yield s
    s.httpd.shutdown()


def _instance():
    ds = pydicom.Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.481.5"
    ds.SOPInstanceUID, ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid(), generate_uid()
    ds.Modality, ds.PatientID = "RTPLAN", "P1"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID, ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPClassUID, ds.SOPInstanceUID
    return ds


def test_bearer_token_is_fetched_reused_and_refreshed(server, monkeypatch):
    tok = ClientCredentialsToken(f"{server.url}/token", "radiarch", "s3cret")
    n = DICOMwebNotifier(url=server.url, token=tok)
    assert n.auth == "bearer"
    assert n.store_instances([_instance()], raise_errors=True)
    assert n.store_instances([_instance()], raise_errors=True)
    assert server.tokens_issued == 1 and server.auth_headers == ["Bearer tok1", "Bearer tok1"]
    # past the refresh point (expires_in minus the margin) a new token is fetched
    now = dw.time.monotonic()
    monkeypatch.setattr(dw.time, "monotonic", lambda: now + 300)
    assert n.store_instances([_instance()], raise_errors=True)
    assert server.tokens_issued == 2 and server.auth_headers[-1] == "Bearer tok2"


def test_settings_turn_on_the_bearer_token_and_keep_the_secret_out_of_repr(server, monkeypatch):
    from radiarch.config import get_settings

    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", server.url)
    monkeypatch.setenv("RADIARCH_DICOMWEB_TOKEN_URL", f"{server.url}/token")
    monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_ID", "radiarch")
    monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_SECRET", "s3cret")
    monkeypatch.setattr(dw, "_tokens", {})
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert "s3cret" not in repr(s) and "s3cret" not in str(s.model_dump())
        assert DICOMwebNotifier().auth == "bearer"
        assert DICOMwebNotifier(url=server.url).auth == "bearer"                                 # the configured URL named again
        assert DICOMwebNotifier(url=server.url, username="u", password="p").auth == "basic"   # an explicit username wins
        assert DICOMwebNotifier(url=server.url).store_instances([_instance()], raise_errors=True)
    finally:
        get_settings.cache_clear()


def test_http_basic_push_reaches_the_server(server):
    """A plain PACS with a username and password (Orthanc in the compose file): the credentials go through a requests
    session, as dicomweb-client takes no username itself (every basic-auth push failed before 2026-10-27)."""
    n = DICOMwebNotifier(url=server.url, username="u", password="p")
    assert n.auth == "basic" and n.store_instances([_instance()], raise_errors=True)
    assert server.auth_headers[-1] == "Basic dTpw"


def test_a_refusal_carries_the_status_and_the_findings(server):
    server.refuse = True
    n = DICOMwebNotifier(url=server.url, token=ClientCredentialsToken(f"{server.url}/token", "radiarch", "s3cret"))
    with pytest.raises(DICOMwebPushError) as ei:
        n.store_instances([_instance()], raise_errors=True)
    assert ei.value.status == 409
    assert ei.value.details["findings"][0]["code"] == "W031"
    assert not n.store_instances([_instance()])                     # non-fatal mode logs and returns False


def test_a_bad_client_secret_is_reported_without_the_secret(server):
    n = DICOMwebNotifier(url=server.url, token=ClientCredentialsToken(f"{server.url}/token", "radiarch", "wrong"))
    with pytest.raises(DICOMwebPushError) as ei:
        n.store_instances([_instance()], raise_errors=True)
    assert ei.value.status == 401 and "invalid_client" in str(ei.value) and "wrong" not in str(ei.value)


def test_push_result_reports_the_refusal(server, monkeypatch, tmp_path):
    """RTExportService.push puts the refusal's status and parsed body into RTPushResult."""
    from radiarch.models.rt_export import RTExportResult, RTObjectRef
    from radiarch.services import rt_export as rx

    server.refuse = True
    svc = rx.RTExportService.__new__(rx.RTExportService)
    path = str(tmp_path / "RP.dcm")
    _instance().save_as(path, enforce_file_format=True)
    fake = RTExportResult.model_construct(export_id="e1", objects=[RTObjectRef.model_construct(kind="RTPLAN", path=path)])
    monkeypatch.setattr(svc, "get", lambda export_id: fake, raising=False)
    monkeypatch.setattr(dw, "_shared_token", lambda *a: ClientCredentialsToken(f"{server.url}/token", "radiarch", "s3cret"))
    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", server.url)
    monkeypatch.setenv("RADIARCH_DICOMWEB_TOKEN_URL", f"{server.url}/token")
    monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_ID", "radiarch")
    from radiarch.config import get_settings
    get_settings.cache_clear()
    try:
        res = svc.push("e1", url=server.url, kinds=["RTPLAN"])
    finally:
        get_settings.cache_clear()
    assert res.pushed == 0 and res.http_status == 409
    assert res.response["findings"][0]["code"] == "W031" and "W031" in res.error


def test_radiarch_s_own_credential_goes_only_to_its_configured_url(server, monkeypatch, tmp_path):
    """A push request may name another URL. Radiarch's own credential (its client-credentials token, or its username
    and password) is not sent there: that URL gets only the credential the request gives."""
    from radiarch.config import get_settings
    from radiarch.models.rt_export import RTExportResult, RTObjectRef
    from radiarch.services import rt_export as rx

    other = _Server()
    try:
        monkeypatch.setenv("RADIARCH_DICOMWEB_URL", server.url)
        monkeypatch.setenv("RADIARCH_DICOMWEB_TOKEN_URL", f"{server.url}/token")
        monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_ID", "radiarch")
        monkeypatch.setenv("RADIARCH_DICOMWEB_CLIENT_SECRET", "s3cret")
        monkeypatch.setattr(dw, "_tokens", {})
        get_settings.cache_clear()
        assert DICOMwebNotifier(url=other.url).auth == "none"
        with pytest.raises(DICOMwebPushError) as ei:
            DICOMwebNotifier(url=other.url).store_instances([_instance()], raise_errors=True)
        assert ei.value.status == 401 and other.auth_headers == [None] and server.tokens_issued == 0
        # through the export service, as POST /rt/exports/{id}/push with a url
        svc = rx.RTExportService.__new__(rx.RTExportService)
        path = str(tmp_path / "RP.dcm")
        _instance().save_as(path, enforce_file_format=True)
        fake = RTExportResult.model_construct(export_id="e1", objects=[RTObjectRef.model_construct(kind="RTPLAN", path=path)])
        monkeypatch.setattr(svc, "get", lambda export_id: fake, raising=False)
        res = svc.push("e1", url=other.url)
        assert res.pushed == 0 and res.http_status == 401 and other.auth_headers == [None, None]
        # a credential the request gives does go there
        assert DICOMwebNotifier(url=other.url, username="u", password="p").store_instances([_instance()], raise_errors=True)
        assert other.auth_headers[-1] == "Basic dTpw"
        # radiarch's own username and password stay home too
        monkeypatch.delenv("RADIARCH_DICOMWEB_TOKEN_URL")
        monkeypatch.setenv("RADIARCH_DICOMWEB_USERNAME", "u")
        monkeypatch.setenv("RADIARCH_DICOMWEB_PASSWORD", "p")
        get_settings.cache_clear()
        assert DICOMwebNotifier(url=other.url).auth == "none"
        assert DICOMwebNotifier(url=server.url + "/").auth == "basic"
        assert DICOMwebNotifier().store_instances([_instance()], raise_errors=True) and server.auth_headers[-1] == "Basic dTpw"
        assert server.tokens_issued == 0
    finally:
        get_settings.cache_clear()
        other.httpd.shutdown()


def test_same_url():
    assert dw._same_url("http://Host:8042/dicom-web/", "HTTP://host:8042/dicom-web")
    assert not dw._same_url("http://host:8042/dicom-web", "http://host:8043/dicom-web")
    assert not dw._same_url("http://host/dicom-web", "https://host/dicom-web")
    assert not dw._same_url("http://host/dicom-web", "http://host.evil/dicom-web")
    assert not dw._same_url("http://host/dicom-web", "http://host/dicom-web/../other")
