"""
End-to-end API test for the Radiarch FastAPI service.

Exercises the full data flow:
  POST /plans → GET /jobs/{id} → GET /plans/{id} → GET /artifacts/{id} → DELETE /plans/{id}

Uses Celery eager mode (task_always_eager) so no Redis/broker is needed.
Uses FakeOrthancAdapter so no Orthanc is needed.
"""

import sys
import os

# Ensure service package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force dev/mock mode and synthetic planner (skip real MCsquare)
os.environ["RADIARCH_ENVIRONMENT"] = "dev"
os.environ["RADIARCH_ORTHANC_USE_MOCK"] = "true"
os.environ["RADIARCH_FORCE_SYNTHETIC"] = "true"

import pytest
from fastapi.testclient import TestClient

from radiarch.app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---- Info & Workflows ----

def test_info(client):
    resp = client.get("/api/v1/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Radiarch TPS Service"
    assert "version" in data
    assert "workflows" in data
    assert len(data["workflows"]) >= 1


def test_list_workflows(client):
    resp = client.get("/api/v1/workflows")
    assert resp.status_code == 200
    workflows = resp.json()
    assert isinstance(workflows, list)
    assert len(workflows) >= 2
    ids = [w["id"] for w in workflows]
    assert "proton-impt-basic" in ids
    assert "photon-ccc" in ids


def test_get_workflow_detail(client):
    resp = client.get("/api/v1/workflows/proton-impt-basic")
    assert resp.status_code == 200
    wf = resp.json()
    assert wf["modality"] == "proton"
    assert wf["engine"] == "mcsquare"
    assert len(wf["default_parameters"]) > 0


def test_get_workflow_not_found(client):
    resp = client.get("/api/v1/workflows/nonexistent")
    assert resp.status_code == 404


# ---- Plans CRUD ----

def test_create_and_get_plan(client):
    # Create a plan
    payload = {
        "study_instance_uid": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        "workflow_id": "proton-impt-basic",
        "prescription_gy": 2.0,
        "fraction_count": 1,
        "notes": "E2E test plan",
    }
    resp = client.post("/api/v1/plans", json=payload)
    assert resp.status_code == 201
    plan = resp.json()
    assert plan["id"]
    assert plan["job_id"]
    assert plan["workflow_id"] == "proton-impt-basic"
    plan_id = plan["id"]
    job_id = plan["job_id"]

    # In eager mode, the Celery task runs synchronously during POST,
    # so the job should already be succeeded (or failed).
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    job = resp.json()
    assert job["state"] in ("succeeded", "failed"), f"Unexpected job state: {job['state']}"

    # Get plan detail — should have QA summary and artifacts
    resp = client.get(f"/api/v1/plans/{plan_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["qa_summary"] is not None
    assert detail["qa_summary"]["engine"] in ("opentps", "synthetic")

    # If artifacts were registered, test artifact download
    if detail["artifact_ids"]:
        artifact_id = detail["artifact_ids"][0]
        resp = client.get(f"/api/v1/artifacts/{artifact_id}")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    return plan_id


def test_list_plans(client):
    resp = client.get("/api/v1/plans")
    assert resp.status_code == 200
    plans = resp.json()
    assert isinstance(plans, list)


def test_delete_plan(client):
    # Create a plan to delete
    payload = {
        "study_instance_uid": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        "workflow_id": "proton-impt-basic",
        "prescription_gy": 1.5,
    }
    resp = client.post("/api/v1/plans", json=payload)
    assert resp.status_code == 201
    plan_id = resp.json()["id"]

    resp = client.delete(f"/api/v1/plans/{plan_id}")
    assert resp.status_code == 204

    # Verify job is cancelled
    plan = client.get(f"/api/v1/plans/{plan_id}").json()
    assert plan["status"] == "cancelled"


def test_delete_plan_not_found(client):
    resp = client.delete("/api/v1/plans/nonexistent-id")
    assert resp.status_code == 404


def test_get_artifact_not_found(client):
    resp = client.get("/api/v1/artifacts/nonexistent-id")
    assert resp.status_code == 404


# ---- Phase 4: Enriched /info ----

def test_info_has_models(client):
    """Verify /info now exposes models for MONAILabel-style engine discovery."""
    resp = client.get("/api/v1/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    models = data["models"]
    assert "proton-mcsquare" in models
    assert models["proton-mcsquare"]["status"] == "available"
    assert "photon-ccc" in models
    assert models["photon-ccc"]["status"] == "planned"


# ---- Phase 4: Sessions CRUD ----

def test_sessions_crud(client, tmp_path):
    """Test create → get → delete session lifecycle."""
    # Create a temp file to upload
    test_file = tmp_path / "test.dcm"
    test_file.write_bytes(b"\x00" * 128)

    # Create session
    with open(test_file, "rb") as f:
        resp = client.post(
            "/api/v1/sessions",
            files={"file": ("test.dcm", f, "application/dicom")},
        )
    assert resp.status_code == 200
    session = resp.json()
    assert "id" in session
    assert session["file_count"] == 1
    session_id = session["id"]

    # Get session
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == session_id

    # Delete session
    resp = client.delete(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == session_id

    # Verify deleted
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 404


# ---- Phase 5: Structured Job Progress ----

def test_job_has_stage(client):
    """Verify job response includes stage field after plan execution."""
    payload = {
        "study_instance_uid": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        "workflow_id": "proton-impt-basic",
        "prescription_gy": 2.0,
    }
    resp = client.post("/api/v1/plans", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    job = resp.json()
    # In eager mode, job should be succeeded with stage="done"
    assert job["state"] == "succeeded"
    assert "stage" in job
    assert job["stage"] == "done"


def test_job_progress_polling(client):
    """Verify job has expected final progress and ETA after completion."""
    payload = {
        "study_instance_uid": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        "workflow_id": "proton-impt-basic",
        "prescription_gy": 1.0,
    }
    resp = client.post("/api/v1/plans", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    resp = client.get(f"/api/v1/jobs/{job_id}")
    job = resp.json()
    assert job["progress"] == 1.0
    assert job["eta_seconds"] == 0
    assert "completed" in job["message"].lower() or "plan completed" in job["message"].lower()


# ---- Phase 6: Multi-Beam Support ----

def test_create_plan_with_beam_count(client):
    """Verify multi-beam plan request produces correct beam config in QA."""
    payload = {
        "study_instance_uid": "1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        "workflow_id": "proton-impt-basic",
        "prescription_gy": 2.0,
        "beam_count": 3,
    }
    resp = client.post("/api/v1/plans", json=payload)
    assert resp.status_code == 201
    plan = resp.json()
    assert plan["beam_count"] == 3

    # Check QA summary has multi-beam metrics
    detail = client.get(f"/api/v1/plans/{plan['id']}").json()
    assert detail["qa_summary"]["beamCount"] == 3
    assert len(detail["qa_summary"]["gantryAngles"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
