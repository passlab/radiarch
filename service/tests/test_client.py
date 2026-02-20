"""Tests for RadiarchClient — runs against TestClient in-process."""

import os
import pytest

# Force test environment before importing anything from radiarch
os.environ["RADIARCH_FORCE_SYNTHETIC"] = "true"
os.environ["RADIARCH_ENVIRONMENT"] = "dev"
os.environ["RADIARCH_ORTHANC_USE_MOCK"] = "true"
os.environ["RADIARCH_DATABASE_URL"] = ""
os.environ["RADIARCH_BROKER_URL"] = "memory://"
os.environ["RADIARCH_RESULT_BACKEND"] = "cache+memory://"
os.environ["RADIARCH_DICOMWEB_URL"] = ""

import tempfile
os.environ["RADIARCH_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="radiarch_test_")

from radiarch.client import RadiarchClient, RadiarchClientError  # noqa: E402


class _TestClientWrapper:
    """Wraps Starlette TestClient to prepend base_url to relative paths,
    mimicking httpx.Client(base_url=...) behavior."""

    def __init__(self, test_client, base_url: str):
        self._tc = test_client
        self._base = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def get(self, path: str, **kwargs):
        return self._tc.get(self._url(path), **kwargs)

    def post(self, path: str, **kwargs):
        return self._tc.post(self._url(path), **kwargs)

    def put(self, path: str, **kwargs):
        return self._tc.put(self._url(path), **kwargs)

    def delete(self, path: str, **kwargs):
        return self._tc.delete(self._url(path), **kwargs)


@pytest.fixture(scope="module")
def client():
    """Create a RadiarchClient backed by Starlette TestClient (in-process)."""
    from starlette.testclient import TestClient
    from radiarch.app import create_app

    app = create_app()
    tc = TestClient(app)

    rc = RadiarchClient.__new__(RadiarchClient)
    rc.base_url = "/api/v1"
    rc._http = _TestClientWrapper(tc, "/api/v1")
    yield rc


def test_client_info(client):
    info = client.info()
    assert info["name"] == "Radiarch TPS Service"
    assert "models" in info


def test_client_list_workflows(client):
    workflows = client.list_workflows()
    assert len(workflows) >= 1
    assert workflows[0]["id"] == "proton-impt-basic"


def test_client_create_and_poll(client):
    plan = client.create_plan(
        study_instance_uid="1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        prescription_gy=2.0,
    )
    assert "job_id" in plan
    assert plan["beam_count"] == 1

    # In eager mode the job is already done
    job = client.get_job(plan["job_id"])
    assert job["state"] == "succeeded"
    assert job["stage"] == "done"


def test_client_create_multibeam(client):
    plan = client.create_plan(
        study_instance_uid="1.2.840.113619.2.55.3.604688321.783.1459769131.467",
        prescription_gy=2.0,
        beam_count=3,
    )
    assert plan["beam_count"] == 3

    # Check the QA summary has multi-beam info
    detail = client.get_plan(plan["id"])
    assert detail["qa_summary"]["beamCount"] == 3
    assert len(detail["qa_summary"]["gantryAngles"]) == 3


def test_client_plan_not_found(client):
    with pytest.raises(RadiarchClientError) as exc_info:
        client.get_plan("nonexistent-plan-id")
    assert exc_info.value.status_code == 404
