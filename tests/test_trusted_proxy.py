"""The requesting user from a trusted proxy, and an export that fails when its push is refused.

With ``trusted_user_header`` and ``trusted_proxy_secret`` set, a request that carries the user header and the proxy's
secret records the user as ``requested_by`` on the optimization, Pareto set, navigation state, deliverable plan and
export it makes, and the exported RT objects name the user as Operators' Name. A user header without the secret is
refused; a ``requested_by`` sent in the body is replaced. With ``dicomweb_push_required`` an export whose push is
refused fails with 502 and keeps nothing; without it the export is kept with ``pushed`` false, as before.
"""

from __future__ import annotations

import pydicom
import pytest

from test_r6_rt_export_service import env  # noqa: F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)
from test_r11_pareto import rx  # noqa: F401  (the app in this process through the SDK)

USER, SECRET = "X-Forwarded-User", "X-Proxy-Secret"


def _trust(monkeypatch, secret="s3cret"):
    from radiarch.config import get_settings

    monkeypatch.setenv("RADIARCH_TRUSTED_USER_HEADER", USER)
    monkeypatch.setenv("RADIARCH_TRUSTED_PROXY_SECRET", secret)
    get_settings.cache_clear()


def _pareto_set(rx, budget=4):  # noqa: F811
    from radiarch.sdk import ops

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    return bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=budget,
                  hard_constraints=[ops.hard("PTV", "Dmin", ">=", 1.0)])


def test_the_user_header_is_read_only_from_the_trusted_proxy(rx, monkeypatch):  # noqa: F811
    ps = _pareto_set(rx)
    url = f"/api/v1/mco/{ps.id}/navigate"

    def navigate(headers, body=None):
        return rx.http.post(url, json=body or {}, headers=headers)

    # not configured: the header is ignored, and a requested_by in the body is replaced
    r = navigate({USER: "alice"}, {"requested_by": "mallory"})
    assert r.status_code == 200 and r.json()["requested_by"] is None
    _trust(monkeypatch)
    assert navigate({USER: "alice", SECRET: "s3cret"}).json()["requested_by"] == "alice"
    assert navigate({USER: "Smith^Al\\ice=x", SECRET: "s3cret"}).json()["requested_by"] == "SmithAlicex"     # no DICOM delimiters
    assert len(navigate({USER: "u" * 100, SECRET: "s3cret"}).json()["requested_by"]) == 64
    assert navigate({}, {"requested_by": "mallory"}).json()["requested_by"] is None                     # no header: nobody
    for headers in ({USER: "alice", SECRET: "wrong"}, {USER: "alice"}):                                  # around the proxy
        r = navigate(headers)
        assert r.status_code == 401 and "alice" not in r.text
    monkeypatch.delenv("RADIARCH_TRUSTED_PROXY_SECRET")
    from radiarch.config import get_settings

    get_settings.cache_clear()
    assert navigate({USER: "alice"}).status_code == 401                                                  # a header without a secret set


def test_the_user_is_kept_on_each_result_and_as_the_operator(rx, monkeypatch, tmp_path):  # noqa: F811
    from radiarch.sdk import ops

    _trust(monkeypatch)
    rx.http.headers.update({USER: "alice", SECRET: "s3cret"})
    ps = _pareto_set(rx, budget=5)
    assert ps.result.requested_by == "alice"
    st = ps.navigate(move={"MeanDose(OAR)": 0.9 * ps.states()[0].values_gy[1]})
    assert st.requested_by == "alice"
    plan = ps.deliverable(st, levels=5, max_iterations=60)
    assert plan.result.requested_by == "alice"
    exp = plan.export(label="MCO", prescription={"dose_gy": 2.0, "fractions": 2})
    assert exp.result.requested_by == "alice"
    files = {p.name: p for p in exp.download(tmp_path / "rt")}
    for name in ("RP.dcm", "RD.dcm", "RS.dcm"):
        assert str(pydicom.dcmread(files[name]).OperatorsName) == "alice"
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 120, 240], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    opt = bm.optimize([ops.uniform_rms("PTV", 2.0)], engine="analytic", max_iterations=30)
    assert opt.result.requested_by == "alice"
    # a cached result keeps its first requester; the requester is not part of the key
    rx.http.headers.update({USER: "bob"})
    again = bm.optimize([ops.uniform_rms("PTV", 2.0)], engine="analytic", max_iterations=30)
    assert again.id == opt.id and again.result.requested_by == "alice"
    rx.http.headers.pop(USER)
    bare = plan.export(label="MCO2", prescription={"dose_gy": 2.0, "fractions": 2})
    assert bare.result.requested_by is None
    assert str(pydicom.dcmread({p.name: p for p in bare.download(tmp_path / "rt2")}["RP.dcm"]).OperatorsName) == "radiarch"


def test_an_export_fails_when_its_push_is_refused_and_the_push_is_required(rx, monkeypatch, tmp_path):  # noqa: F811
    from radiarch.adapters import dicomweb
    from radiarch.config import get_settings
    from radiarch.sdk import RadiarchError

    def refuse(self, paths, raise_errors=False):
        raise RuntimeError("409 Conflict: the archive refused the instances")

    monkeypatch.setattr(dicomweb.DICOMwebNotifier, "store_instances", refuse)
    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", "http://pacs.invalid/dicom-web")
    get_settings.cache_clear()
    ps = _pareto_set(rx)
    plan = ps.deliverable("balance", levels=5, max_iterations=60)

    kept = plan.export(label="KEPT", push=True)                       # not required: kept, pushed false, the error recorded
    assert kept.result.pushed is False and "409" in kept.result.push_error
    monkeypatch.setenv("RADIARCH_DICOMWEB_PUSH_REQUIRED", "true")
    get_settings.cache_clear()
    from radiarch.services.rt_export import RTExportService

    before = {p.name for p in RTExportService().base_dir.iterdir()}
    with pytest.raises(RadiarchError) as e:
        plan.export(label="REQUIRED", push=True)
    assert e.value.status_code == 502 and "refused" in str(e.value.detail) and "409" in str(e.value.detail)
    assert {p.name for p in RTExportService().base_dir.iterdir()} == before                 # the refused export's objects removed
    with pytest.raises(RadiarchError) as e:                           # the stored export pushed again: refused too
        plan.export(label="KEPT", push=True)
    assert e.value.status_code == 502
    r = rx.http.post(f"/api/v1/rt/exports/{kept.id}/push", json={})
    assert r.status_code == 502 and "refused" in r.text
