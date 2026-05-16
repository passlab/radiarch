"""End-to-end tests for the /geometry/* routes (sync + async paths).

Uses FastAPI's TestClient plus a monkey-patched GeometryService so the
pipeline runs against synthetic CT + contours — no OpenTPS, no real
DICOM. In ``environment=dev`` Celery is configured to run tasks eagerly,
so the dispatch path ``build_geometry_job.delay()`` executes
synchronously in the API thread and we can poll the job endpoint
immediately.
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
from radiarch.core import store as store_module
from radiarch.services.geometry import GeometryService, _LoadedCT
from radiarch.tasks import geometry_tasks as geometry_tasks_module


# ---------------------------------------------------------------------------
# Fakes
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
    """FastAPI client with a sandboxed GeometryService and an in-memory store.

    The Celery task ``build_geometry_job`` imports ``GeometryService``
    lazily and constructs its own instance inside the task — we
    monkey-patch the class's ``_load`` method to use the stub, so both
    the API-route service *and* the Celery-task service produce the same
    synthetic data.
    """
    tmp = tempfile.TemporaryDirectory()
    svc = GeometryService(base_dir=tmp.name)
    monkeypatch.setattr(svc, "_load", lambda _req: _build_loaded_ct())

    # Reset any cached singletons so the test starts with a clean store.
    store_module.reset_store()
    geometry_route._service.cache_clear()

    # Swap the lru_cached service for our preconfigured instance.
    monkeypatch.setattr(geometry_route, "_service", lambda: svc)

    # Celery task instantiates its own GeometryService — patch the class
    # so any instance created in the task uses the same tempdir + stub.
    monkeypatch.setattr(
        GeometryService,
        "_load",
        lambda self, _req: _build_loaded_ct(),
    )
    # Also force new instances into the same base_dir.
    original_init = GeometryService.__init__

    def _init_to_tmp(self, base_dir=None, adapter=None):
        original_init(self, base_dir=tmp.name, adapter=adapter)

    monkeypatch.setattr(GeometryService, "__init__", _init_to_tmp)

    # No-op init_db so the app lifespan doesn't try to reach Postgres.
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)

    # Bypass Celery entirely: call the task body synchronously. Celery's
    # eager mode still tries to use the Redis result backend, which isn't
    # running locally; patching .delay sidesteps the broker completely.
    import types

    def _eager_delay(job_id, request_payload):
        geometry_tasks_module.build_geometry_job.run(job_id, request_payload)
        return types.SimpleNamespace(id=job_id)

    monkeypatch.setattr(
        geometry_tasks_module.build_geometry_job, "delay", _eager_delay
    )

    app = create_app()
    with TestClient(app) as c:
        yield c
    tmp.cleanup()
    store_module.reset_store()


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
# POST /build — async dispatch path
# ---------------------------------------------------------------------------

class TestBuildAsyncDispatch:
    def test_cache_miss_returns_202_and_job_id(self, client: TestClient) -> None:
        r = client.post("/api/v1/geometry/build", json=_sample_payload())
        assert r.status_code == 202, r.text
        body = r.json()
        assert "job_id" in body
        assert body["cache_key"]
        # No geometry fields in the 202 response shape.
        assert "geometry_id" not in body
        assert "structure_index" not in body

    def test_202_job_is_in_queued_or_succeeded_state(self, client: TestClient) -> None:
        """With Celery eager mode the task finishes before the HTTP
        response returns. Accept either queued (if the broker were real)
        or succeeded (eager) — both valid."""
        r = client.post("/api/v1/geometry/build", json=_sample_payload())
        job_id = r.json()["job_id"]
        status_r = client.get(f"/api/v1/geometry/jobs/{job_id}")
        assert status_r.status_code == 200, status_r.text
        assert status_r.json()["state"] in {"queued", "running", "succeeded"}


# ---------------------------------------------------------------------------
# POST /build — cache-hit fast path
# ---------------------------------------------------------------------------

class TestBuildCacheHit:
    def test_second_build_returns_200_with_full_result(self, client: TestClient) -> None:
        # First call: 202 (cache miss, builds and caches via eager Celery).
        first = client.post("/api/v1/geometry/build", json=_sample_payload())
        assert first.status_code == 202

        # Second call: 200 (cache hit) with the full geometry inline.
        second = client.post("/api/v1/geometry/build", json=_sample_payload())
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["geometry_id"]
        assert body["structure_index"] == {"PTV": 1}
        assert body["ct_metadata"]["num_slices"] == 8

    def test_cache_hit_has_no_job_id_field(self, client: TestClient) -> None:
        client.post("/api/v1/geometry/build", json=_sample_payload())
        second = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        # 200 response is a GeometryResult — no job_id key.
        assert "job_id" not in second


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------

class TestJobsEndpoint:
    def test_unknown_job_id_is_404(self, client: TestClient) -> None:
        r = client.get("/api/v1/geometry/jobs/does-not-exist")
        assert r.status_code == 404

    def test_succeeded_job_carries_geometry_id(self, client: TestClient) -> None:
        """In eager mode the job finishes synchronously → polling
        immediately after dispatch should see state=succeeded plus a
        populated geometry_id."""
        r = client.post("/api/v1/geometry/build", json=_sample_payload())
        job_id = r.json()["job_id"]

        status = client.get(f"/api/v1/geometry/jobs/{job_id}").json()
        assert status["state"] == "succeeded"
        assert status["geometry_id"]  # non-null, points at a real result
        assert status["progress"] == 1.0
        assert status["stage"] == "done"

    def test_job_geometry_id_resolves_to_actual_result(
        self, client: TestClient
    ) -> None:
        r = client.post("/api/v1/geometry/build", json=_sample_payload()).json()
        status = client.get(f"/api/v1/geometry/jobs/{r['job_id']}").json()
        geom = client.get(f"/api/v1/geometry/{status['geometry_id']}").json()
        assert geom["geometry_id"] == status["geometry_id"]
        assert geom["cache_key"] == r["cache_key"]


# ---------------------------------------------------------------------------
# GET /{geometry_id} + streaming endpoints (regression, unchanged behavior)
# ---------------------------------------------------------------------------

class TestGeometryRetrieval:
    def _submit_and_get_id(self, client: TestClient) -> str:
        r = client.post("/api/v1/geometry/build", json=_sample_payload())
        job_id = r.json()["job_id"]
        return client.get(f"/api/v1/geometry/jobs/{job_id}").json()["geometry_id"]

    def test_density_stream_returns_nifti_bytes(self, client: TestClient) -> None:
        gid = self._submit_and_get_id(client)
        r = client.get(f"/api/v1/geometry/{gid}/density")
        assert r.status_code == 200
        # gzipped NIfTI starts with the gzip magic 0x1f 0x8b.
        assert r.content[:2] == b"\x1f\x8b"

    def test_masks_stream_returns_nifti_bytes(self, client: TestClient) -> None:
        gid = self._submit_and_get_id(client)
        r = client.get(f"/api/v1/geometry/{gid}/masks")
        assert r.status_code == 200
        assert r.content[:2] == b"\x1f\x8b"

    def test_unknown_geometry_id_is_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/geometry/nope").status_code == 404
        assert client.get("/api/v1/geometry/nope/density").status_code == 404
        assert client.get("/api/v1/geometry/nope/masks").status_code == 404


# ---------------------------------------------------------------------------
# DELETE /{geometry_id}
# ---------------------------------------------------------------------------

class TestDelete:
    def _submit_and_get_id(self, client: TestClient) -> str:
        r = client.post("/api/v1/geometry/build", json=_sample_payload())
        job_id = r.json()["job_id"]
        return client.get(f"/api/v1/geometry/jobs/{job_id}").json()["geometry_id"]

    def test_delete_returns_204_and_removes_geometry(self, client: TestClient) -> None:
        gid = self._submit_and_get_id(client)
        r = client.delete(f"/api/v1/geometry/{gid}")
        assert r.status_code == 204
        assert client.get(f"/api/v1/geometry/{gid}").status_code == 404

    def test_delete_scrubs_cache_so_next_build_goes_through_pipeline(
        self, client: TestClient
    ) -> None:
        """After deleting, the same request should 202 (rebuild) rather
        than 200 (cache hit)."""
        gid = self._submit_and_get_id(client)
        client.delete(f"/api/v1/geometry/{gid}")

        resubmit = client.post("/api/v1/geometry/build", json=_sample_payload())
        assert resubmit.status_code == 202, resubmit.text

    def test_delete_unknown_id_is_404(self, client: TestClient) -> None:
        assert client.delete("/api/v1/geometry/nope").status_code == 404
