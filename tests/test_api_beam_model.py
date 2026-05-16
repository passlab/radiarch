"""End-to-end tests for the /beam-model/* routes (sync + async + DELETE).

Uses FastAPI's TestClient + the same monkey-patch fixture pattern as
``test_api_geometry.py``: stub out _load_geometry, force the modality
builder to return a deterministic plan, patch ``.delay`` to ``.run`` so
Celery doesn't try to reach Redis, patch init_db to avoid Postgres.
"""

from __future__ import annotations

import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from radiarch import app as radiarch_app
from radiarch.api.routes import beam_model as beam_model_route
from radiarch.app import create_app
from radiarch.core import store as store_module
from radiarch.models.beam_model import (
    FluenceElementSet,
    Modality,
    PerBeamElements,
)
from radiarch.services.beam_model import BeamModelService, _LoadedGeometry
from radiarch.tasks import beam_model_tasks as beam_tasks_module


# ---------------------------------------------------------------------------
# Test plan double — picklable so persistence tests can run end-to-end.
# ---------------------------------------------------------------------------

@dataclass
class _MockPlan:
    note: str = "mock"


def _stub_geometry() -> _LoadedGeometry:
    return _LoadedGeometry(
        geometry_id="g-1",
        ct=object(),
        patient=object(),
        target_contour=object(),
    )


def _stub_proton_build(req, geom, mm):
    from radiarch.services.proton_spots import ProtonBuildResult
    return ProtonBuildResult(
        fluence_elements=FluenceElementSet(
            total_count=20,
            per_beam=[PerBeamElements(beam_id="B1", element_count=20,
                                      energy_layers=[100.0, 110.0],
                                      spots_per_layer=[10, 10])],
        ),
        plan=_MockPlan(note="proton"),
    )


def _stub_photon_build(req, geom, mm):
    from radiarch.services.photon_beamlets import PhotonBuildResult
    return PhotonBuildResult(
        fluence_elements=FluenceElementSet(
            total_count=400,
            per_beam=[PerBeamElements(beam_id="B1", element_count=400,
                                      grid_dims=(20, 20),
                                      active_beamlets=400)],
        ),
        plan=_MockPlan(note="photon"),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    svc = BeamModelService(base_dir=tmp.name)

    # Stub the dependency loaders so OpenTPS / DICOM are never touched.
    monkeypatch.setattr(svc, "_load_geometry", lambda gid: _stub_geometry())
    monkeypatch.setattr(BeamModelService, "_load_geometry",
                        lambda self, gid: _stub_geometry())
    monkeypatch.setattr(BeamModelService, "_build_proton",
                        staticmethod(_stub_proton_build))
    monkeypatch.setattr(BeamModelService, "_build_photon",
                        staticmethod(_stub_photon_build))

    # Force every BeamModelService instance built inside the Celery task
    # to use the same tempdir. Celery instantiates its own service.
    original_init = BeamModelService.__init__

    def _init_to_tmp(self, base_dir=None):
        original_init(self, base_dir=tmp.name)

    monkeypatch.setattr(BeamModelService, "__init__", _init_to_tmp)

    # Reset and re-point singletons.
    store_module.reset_store()
    beam_model_route._service.cache_clear()
    monkeypatch.setattr(beam_model_route, "_service", lambda: svc)

    # Bypass the Postgres lifespan init.
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)

    # Bypass Celery: call the task body synchronously.
    def _eager_delay(job_id, request_payload):
        beam_tasks_module.build_beam_model_job.run(job_id, request_payload)
        return types.SimpleNamespace(id=job_id)

    monkeypatch.setattr(
        beam_tasks_module.build_beam_model_job, "delay", _eager_delay
    )

    app = create_app()
    with TestClient(app) as c:
        yield c
    tmp.cleanup()
    store_module.reset_store()


def _proton_payload() -> dict:
    return {
        "geometry_id": "g-1",
        "modality": "PROTON_PBS",
        "machine_model_id": None,
        "beam_set": {
            "isocenter_mm": [0, 0, 0],
            "beams": [{"beam_id": "B1", "gantry_deg": 0.0, "couch_deg": 0.0,
                       "collimator_deg": 0.0}],
        },
        "delivery_params": {
            "spot_spacing_mm": 5.0,
            "layer_spacing_mm": 5.0,
        },
    }


def _photon_payload() -> dict:
    return {
        "geometry_id": "g-1",
        "modality": "PHOTON_IMRT",
        "beam_set": {
            "isocenter_mm": [0, 0, 0],
            "beams": [{"beam_id": "B1", "gantry_deg": 0.0}],
        },
        "delivery_params": {
            "beamlet_size_mm": [5.0, 5.0],
            "jaw_opening_mm": [100.0, 100.0],
        },
    }


# ---------------------------------------------------------------------------
# Async dispatch
# ---------------------------------------------------------------------------

class TestBuildAsyncDispatch:
    def test_proton_cache_miss_returns_202(self, client: TestClient):
        r = client.post("/api/v1/beam-model/build", json=_proton_payload())
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["job_id"]
        assert body["cache_key"]
        assert "beam_model_id" not in body

    def test_photon_cache_miss_returns_202(self, client: TestClient):
        r = client.post("/api/v1/beam-model/build", json=_photon_payload())
        assert r.status_code == 202, r.text


# ---------------------------------------------------------------------------
# Cache hit
# ---------------------------------------------------------------------------

class TestBuildCacheHit:
    def test_second_build_returns_200_with_full_result(self, client: TestClient):
        first = client.post("/api/v1/beam-model/build", json=_proton_payload())
        assert first.status_code == 202

        second = client.post("/api/v1/beam-model/build", json=_proton_payload())
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["beam_model_id"]
        assert body["modality"] == "PROTON_PBS"
        assert body["fluence_elements"]["total_count"] == 20

    def test_cache_hit_response_has_no_job_id(self, client: TestClient):
        client.post("/api/v1/beam-model/build", json=_proton_payload())
        second = client.post("/api/v1/beam-model/build", json=_proton_payload()).json()
        assert "job_id" not in second


# ---------------------------------------------------------------------------
# Jobs endpoint
# ---------------------------------------------------------------------------

class TestJobsEndpoint:
    def test_unknown_job_id_is_404(self, client: TestClient):
        r = client.get("/api/v1/beam-model/jobs/does-not-exist")
        assert r.status_code == 404

    def test_succeeded_job_carries_beam_model_id(self, client: TestClient):
        r = client.post("/api/v1/beam-model/build", json=_proton_payload())
        job_id = r.json()["job_id"]

        status = client.get(f"/api/v1/beam-model/jobs/{job_id}").json()
        assert status["state"] == "succeeded"
        assert status["beam_model_id"]
        assert status["progress"] == 1.0
        assert status["stage"] == "done"

    def test_job_beam_model_id_resolves_to_actual_result(self, client: TestClient):
        r = client.post("/api/v1/beam-model/build", json=_photon_payload()).json()
        status = client.get(f"/api/v1/beam-model/jobs/{r['job_id']}").json()
        bm = client.get(f"/api/v1/beam-model/{status['beam_model_id']}").json()
        assert bm["beam_model_id"] == status["beam_model_id"]
        assert bm["cache_key"] == r["cache_key"]
        assert bm["modality"] == "PHOTON_IMRT"


# ---------------------------------------------------------------------------
# GET /{id} + /{id}/artifact
# ---------------------------------------------------------------------------

class TestRetrieval:
    def _submit_and_get_id(self, client: TestClient) -> str:
        r = client.post("/api/v1/beam-model/build", json=_proton_payload())
        job_id = r.json()["job_id"]
        return client.get(f"/api/v1/beam-model/jobs/{job_id}").json()["beam_model_id"]

    def test_get_returns_full_result(self, client: TestClient):
        bm_id = self._submit_and_get_id(client)
        r = client.get(f"/api/v1/beam-model/{bm_id}").json()
        assert r["beam_model_id"] == bm_id
        assert r["fluence_elements"]["per_beam"][0]["beam_id"] == "B1"

    def test_artifact_stream_returns_pickled_bytes(self, client: TestClient):
        bm_id = self._submit_and_get_id(client)
        r = client.get(f"/api/v1/beam-model/{bm_id}/artifact")
        assert r.status_code == 200
        # Pickle protocol 5 starts with 0x80 0x05.
        assert r.content[:1] == b"\x80"

    def test_unknown_id_is_404(self, client: TestClient):
        assert client.get("/api/v1/beam-model/nope").status_code == 404
        assert client.get("/api/v1/beam-model/nope/artifact").status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

class TestDelete:
    def _submit_and_get_id(self, client: TestClient) -> str:
        r = client.post("/api/v1/beam-model/build", json=_proton_payload())
        job_id = r.json()["job_id"]
        return client.get(f"/api/v1/beam-model/jobs/{job_id}").json()["beam_model_id"]

    def test_delete_returns_204_and_removes(self, client: TestClient):
        bm_id = self._submit_and_get_id(client)
        r = client.delete(f"/api/v1/beam-model/{bm_id}")
        assert r.status_code == 204
        assert client.get(f"/api/v1/beam-model/{bm_id}").status_code == 404

    def test_delete_scrubs_cache(self, client: TestClient):
        bm_id = self._submit_and_get_id(client)
        client.delete(f"/api/v1/beam-model/{bm_id}")
        # Same payload should rebuild rather than cache-hit.
        r = client.post("/api/v1/beam-model/build", json=_proton_payload())
        assert r.status_code == 202

    def test_delete_unknown_id_is_404(self, client: TestClient):
        assert client.delete("/api/v1/beam-model/nope").status_code == 404
