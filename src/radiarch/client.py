"""RadiarchClient — type-safe Python client for the Radiarch TPS API.

Mirrors MONAILabel's ``MONAILabelClient`` pattern: thin HTTP wrappers
with convenience methods like ``poll_job()`` for long-running tasks.

Usage::

    from radiarch.client import RadiarchClient

    client = RadiarchClient("http://localhost:8000/api/v1")
    info = client.info()
    plan = client.create_plan(
        study_instance_uid="1.2.3.4",
        prescription_gy=2.0,
    )
    job = client.poll_job(plan["job_id"], timeout=300)
    artifact = client.get_artifact(plan["artifact_ids"][0])
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx


class RadiarchClientError(RuntimeError):
    """Raised when the API returns an unexpected status."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class RadiarchClient:
    """Synchronous HTTP client for the Radiarch TPS API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        auth = (username, password) if username else None
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            auth=auth,
        )

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # -- helpers --

    def _check(self, resp: httpx.Response, expected: int = 200) -> httpx.Response:
        if resp.status_code != expected:
            detail = resp.text[:500]
            raise RadiarchClientError(resp.status_code, detail)
        return resp

    # -- Info & Workflows --

    def info(self) -> Dict[str, Any]:
        """GET /info — service metadata, models, workflows."""
        return self._check(self._http.get("/info")).json()

    def list_workflows(self) -> List[Dict[str, Any]]:
        """GET /workflows — available planning templates."""
        return self._check(self._http.get("/workflows")).json()

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """GET /workflows/{id} — workflow detail."""
        return self._check(self._http.get(f"/workflows/{workflow_id}")).json()

    # -- Plans --

    def create_plan(
        self,
        study_instance_uid: str,
        prescription_gy: float,
        workflow_id: str = "proton-impt-basic",
        fraction_count: int = 1,
        beam_count: int = 1,
        segmentation_uid: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /plans — submit a planning job. Returns plan detail with job_id."""
        payload: Dict[str, Any] = {
            "study_instance_uid": study_instance_uid,
            "prescription_gy": prescription_gy,
            "workflow_id": workflow_id,
            "fraction_count": fraction_count,
            "beam_count": beam_count,
        }
        if segmentation_uid:
            payload["segmentation_uid"] = segmentation_uid
        if notes:
            payload["notes"] = notes
        return self._check(self._http.post("/plans", json=payload), 201).json()

    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        """GET /plans/{id} — plan detail."""
        return self._check(self._http.get(f"/plans/{plan_id}")).json()

    def list_plans(self) -> List[Dict[str, Any]]:
        """GET /plans — list all plans."""
        return self._check(self._http.get("/plans")).json()

    def delete_plan(self, plan_id: str) -> None:
        """DELETE /plans/{id} — cancel a plan."""
        self._check(self._http.delete(f"/plans/{plan_id}"), 204)

    # -- Jobs --

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """GET /jobs/{id} — job status, progress, stage."""
        return self._check(self._http.get(f"/jobs/{job_id}")).json()

    def poll_job(
        self,
        job_id: str,
        timeout: float = 300.0,
        interval: float = 2.0,
    ) -> Dict[str, Any]:
        """Poll GET /jobs/{id} until a terminal state (succeeded/failed/cancelled).

        Returns the final job status dict.
        Raises ``RadiarchClientError`` on timeout.
        """
        deadline = time.monotonic() + timeout
        terminal = {"succeeded", "failed", "cancelled"}
        while time.monotonic() < deadline:
            job = self.get_job(job_id)
            if job["state"] in terminal:
                return job
            time.sleep(interval)
        raise RadiarchClientError(408, f"Job {job_id} did not complete within {timeout}s")

    # -- Artifacts --

    def get_artifact(self, artifact_id: str) -> bytes:
        """GET /artifacts/{id} — download artifact content."""
        resp = self._check(self._http.get(f"/artifacts/{artifact_id}"))
        return resp.content

    # -- Sessions --

    def create_session(self, filepath: str) -> Dict[str, Any]:
        """POST /sessions — upload a temporary DICOM file."""
        with open(filepath, "rb") as f:
            files = {"file": (filepath.rsplit("/", 1)[-1], f, "application/dicom")}
            return self._check(self._http.post("/sessions", files=files)).json()

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """GET /sessions/{id}."""
        return self._check(self._http.get(f"/sessions/{session_id}")).json()

    def delete_session(self, session_id: str) -> None:
        """DELETE /sessions/{id}."""
        self._check(self._http.delete(f"/sessions/{session_id}"))
