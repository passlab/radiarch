"""End-to-end tests for the /geometry/* routes.

Uses FastAPI's TestClient and a monkey-patched GeometryService so we can
drive the pipeline against synthetic CT + contours — no OpenTPS, no
real DICOM, no Celery.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest
from fastapi.testclient import TestClient

from radiarch import app as radiarch_app
from radiarch.api.routes import geometry as geometry_route
from radiarch.app import create_app
from radiarch.services.geometry import GeometryService, _LoadedCT


# ---------------------------------------------------------------------------
# Fakes (trimmed copies of test_geometry_service.py)
# ---------------------------------------------------------------------------

@dataclass
class _FakePatient:
    name: str = "API_TEST"
    rtStructs: list = field(default_factory=list)


@dataclass
class _FakeCT:
    imageArray: np.ndarray
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    patient: _FakePatient
    seriesInstanceUID: str = "1.2.3.4"
    studyInstanceUID: str = "1.2.3"
    frameOfReferenceUID: str = "1.2.3.9"


@dataclass
class _FakeMask:
    imageArray: np.ndarray


@dataclass
class _FakeContour:
    name: str
    mask: np.ndarray

    def getBinaryMask(self, origin, gridSize, spacing):
        return _FakeMask(imageArray=self.mask.astype(bool))


def _build_loaded_ct() -> _LoadedCT:
    ct_array = np.zeros((8, 8, 8), dtype=np.int16)
    ct_array[2:6, 2:6, 2:6] = 50
    ptv = np.zeros(ct_array.shape, dtype=bool)
    ptv[2:6, 2:6, 2:6] = True
    ct = _FakeCT(imageArray=ct_array, origin=(0, 0, 0), spacing=(1, 1, 1), patient=_FakePatient())
    return _LoadedCT(ct=ct, patient=ct.patient, contours=[_FakeContour("PTV", ptv)])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    """FastAPI client with a sandboxed, stubbed GeometryService singleton.

    We intercept two things that would otherwise break an offline pytest run:
      * ``init_db`` — the real implementation tries to connect to Postgres,
        which isn't available outside docker-compose. Stub to a no-op.
      * ``geometry_route._service`` — swap the lru_cached factory for a
        lambda returning our stubbed service. Clear the lru cache *before*
        monkeypatching so any prior test's cached instance doesn't leak.
    """
    tmp = tempfile.TemporaryDirectory()
    svc = GeometryService(base_dir=tmp.name)
    monkeypatch.setattr(svc, "_load", lambda _req: _build_loaded_ct())

    # Clear the real lru_cache before we replace the function — otherwise
    # the *previous* test's cached service would leak via the module global
    # once monkeypatch reverts at teardown.
    geometry_route._service.cache_clear()

    # No-op init_db so the app lifespan doesn't try to reach Postgres.
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    monkeypatch.setattr(geometry_route, "_service", lambda: svc)

    app = create_app()
    with TestClient(app) as c:
        yield c
    tmp.cleanup()
    # NOTE: don't call geometry_route._service.cache_clear() here — at this
    # point it's still the monkeypatched lambda (which has no cache_clear).
    # monkeypatch teardown restores the real lru_cached function on exit.


def _sample_payload(grid_spec=None) -> dict:
    return {
        "patient_ref": {
            "dicom_study_uid": "1.2.3",
            "ct_series_uid": "1.2.3.4",
            "rtstruct_uid": "1.2.3.5",
        },
        "grid_spec": grid_spec,
        "hu_to_density_model": "LINEAR",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildEndpoint:
    def test_happy_path_returns_geometry_result(self, client: TestClient) -> None:
        r = client.post("/api/v1/geometry/build", json=_sample_payload())
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["geometry_id"]
        assert body["structure_index"] == {"PTV": 1}
        assert body["frame_of_reference_uid"] == "1.2.3.9"
        assert body["ct_metadata"]["num_slices"] == 8
        assert body["grid_spec"]["size"] == [8, 8, 8]
        assert body["cache_key"]

    def test_cached_second_build_returns_same_geometry_id(self, client: TestClient) -> None:
        first = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        second = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        assert first["geometry_id"] == second["geometry_id"]


class TestGetEndpoint:
    def test_roundtrip_build_then_fetch(self, client: TestClient) -> None:
        built = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        fetched = client.get(f"/api/v1/geometry/{built['geometry_id']}").json()
        assert fetched["geometry_id"] == built["geometry_id"]
        assert fetched["cache_key"] == built["cache_key"]

    def test_unknown_id_is_404(self, client: TestClient) -> None:
        r = client.get("/api/v1/geometry/does-not-exist")
        assert r.status_code == 404


class TestVolumeStreaming:
    def test_density_stream_returns_nifti_bytes(self, client: TestClient) -> None:
        built = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        r = client.get(f"/api/v1/geometry/{built['geometry_id']}/density")
        assert r.status_code == 200
        # gzipped NIfTI starts with the gzip magic 0x1f 0x8b.
        assert r.content[:2] == b"\x1f\x8b"

    def test_masks_stream_returns_nifti_bytes(self, client: TestClient) -> None:
        built = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        r = client.get(f"/api/v1/geometry/{built['geometry_id']}/masks")
        assert r.status_code == 200
        assert r.content[:2] == b"\x1f\x8b"
