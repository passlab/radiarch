"""Celery task for a protocol run (R10).

Mirrors ``evaluation_tasks.run_evaluation_job``: pull the job row, drive :meth:`AutoplanService.run` while mirroring
stage and progress to the row, stash ``run_id`` on success, and emit audit events.
"""

from __future__ import annotations

import time

from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.job import JobState
from ..models.protocol import AutoplanStage, ProtocolRunRequest
from ..services.audit import emit, make_event


@celery_app.task(
    name="radiarch.autoplan.run",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def run_autoplan_job(job_id: str, request_payload: dict):
    """Execute :meth:`AutoplanService.run` and mirror progress."""
    from ..services.autoplan import AutoplanService

    job = store.get_autoplan_job(job_id)
    if not job:
        logger.error("run_autoplan_job called with unknown job_id={}", job_id)
        return

    t0 = time.monotonic()

    def _on_progress(stage: AutoplanStage, fraction: float, message: str) -> None:
        store.update_autoplan_job(job_id, state=JobState.running if fraction < 1.0 else job.state,
                                  progress=round(fraction, 3), stage=stage, message=message)

    request: ProtocolRunRequest | None = None
    try:
        store.update_autoplan_job(job_id, state=JobState.running, progress=0.0, stage=AutoplanStage.queued, message="Queued → running")
        request = ProtocolRunRequest.model_validate(request_payload)
        result = AutoplanService().run(request, progress_callback=_on_progress)
    except SoftTimeLimitExceeded:
        logger.error(f"Protocol run timed out for job {job_id}")
        store.update_autoplan_job(job_id, state=JobState.failed, progress=1.0, stage=AutoplanStage.done, message="Timed out")
        emit(make_event("autoplan.run", state="failed", error_type="SoftTimeLimitExceeded", error_message="protocol run hit soft time limit",
                        duration_s=round(time.monotonic() - t0, 3), geometry_id=getattr(request, "geometry_id", None), extra={"job_id": job_id}))
        return
    except Exception as exc:  # pragma: no cover — exercised in tests
        logger.exception(f"Protocol run failed for job {job_id}")
        store.update_autoplan_job(job_id, state=JobState.failed, progress=1.0, stage=AutoplanStage.done, message=f"{type(exc).__name__}: {exc}")
        emit(make_event("autoplan.run", state="failed", error_type=type(exc).__name__, error_message=str(exc)[:500],
                        duration_s=round(time.monotonic() - t0, 3), geometry_id=getattr(request, "geometry_id", None), extra={"job_id": job_id}))
        return

    store.update_autoplan_job(job_id, state=JobState.succeeded, progress=1.0, stage=AutoplanStage.done,
                              message=f"Planned in {time.monotonic() - t0:.1f}s", run_id=result.run_id)
    emit(make_event("autoplan.run", state="succeeded", cache_key=result.cache_key, geometry_id=request.geometry_id,
                    duration_s=round(time.monotonic() - t0, 3),
                    extra={"job_id": job_id, "run_id": result.run_id, "protocol_id": result.protocol.protocol_id, "passed": result.passed,
                           "normalisation": result.normalisation}))
