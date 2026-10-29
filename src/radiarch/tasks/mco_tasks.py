"""Celery tasks for multi-criteria optimization (R11): a Pareto set, and a navigation state's deliverable plan.

Mirrors ``autoplan_tasks.run_autoplan_job``: pull the job row, drive :meth:`MCOService.run` while mirroring stage and
progress to the row, stash ``mco_id`` on success, and emit audit events.
"""

from __future__ import annotations

import time

from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.job import JobState
from ..models.mco import DeliverableRequest, DeliverableStage, MCORunRequest, MCOStage
from ..services.audit import emit, make_event


@celery_app.task(
    name="radiarch.mco.run",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def run_mco_job(job_id: str, request_payload: dict):
    """Execute :meth:`MCOService.run` and mirror progress."""
    from ..services.mco import MCOService

    job = store.get_mco_job(job_id)
    if not job:
        logger.error("run_mco_job called with unknown job_id={}", job_id)
        return

    t0 = time.monotonic()

    def _on_progress(stage: MCOStage, fraction: float, message: str) -> None:
        store.update_mco_job(job_id, state=JobState.running if fraction < 1.0 else job.state,
                             progress=round(fraction, 3), stage=stage, message=message)

    request: MCORunRequest | None = None
    try:
        store.update_mco_job(job_id, state=JobState.running, progress=0.0, stage=MCOStage.queued, message="Queued → running")
        request = MCORunRequest.model_validate(request_payload)
        result = MCOService().run(request, progress_callback=_on_progress)
    except SoftTimeLimitExceeded:
        logger.error(f"MCO run timed out for job {job_id}")
        store.update_mco_job(job_id, state=JobState.failed, progress=1.0, stage=MCOStage.done, message="Timed out")
        emit(make_event("mco.run", state="failed", error_type="SoftTimeLimitExceeded", error_message="MCO run hit soft time limit",
                        duration_s=round(time.monotonic() - t0, 3), geometry_id=getattr(request, "geometry_id", None), extra={"job_id": job_id}))
        return
    except Exception as exc:  # pragma: no cover — exercised in tests
        logger.exception(f"MCO run failed for job {job_id}")
        store.update_mco_job(job_id, state=JobState.failed, progress=1.0, stage=MCOStage.done, message=f"{type(exc).__name__}: {exc}")
        emit(make_event("mco.run", state="failed", error_type=type(exc).__name__, error_message=str(exc)[:500],
                        duration_s=round(time.monotonic() - t0, 3), geometry_id=getattr(request, "geometry_id", None), extra={"job_id": job_id}))
        return

    store.update_mco_job(job_id, state=JobState.succeeded, progress=1.0, stage=MCOStage.done,
                         message=f"{len(result.plans)} plans, error bound {result.error_bound:.3f}", mco_id=result.mco_id)
    emit(make_event("mco.run", state="succeeded", cache_key=result.cache_key, geometry_id=request.geometry_id,
                    beam_model_id=request.beam_model_id, duration_s=round(time.monotonic() - t0, 3),
                    extra={"job_id": job_id, "mco_id": result.mco_id, "plans": len(result.plans), "error_bound": result.error_bound}))


@celery_app.task(
    name="radiarch.mco.deliverable",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def run_deliverable_job(job_id: str, mco_id: str, request_payload: dict):
    """Execute :meth:`DeliverableService.run` and mirror progress."""
    from ..services.mco_deliverable import DeliverableService

    job = store.get_deliverable_job(job_id)
    if not job:
        logger.error("run_deliverable_job called with unknown job_id={}", job_id)
        return
    t0 = time.monotonic()

    def _on_progress(stage: DeliverableStage, fraction: float, message: str) -> None:
        store.update_deliverable_job(job_id, state=JobState.running if fraction < 1.0 else job.state,
                                     progress=round(fraction, 3), stage=stage, message=message)

    try:
        store.update_deliverable_job(job_id, state=JobState.running, progress=0.0, stage=DeliverableStage.queued, message="Queued → running")
        result = DeliverableService().run(mco_id, DeliverableRequest.model_validate(request_payload), progress_callback=_on_progress)
    except SoftTimeLimitExceeded:
        store.update_deliverable_job(job_id, state=JobState.failed, progress=1.0, stage=DeliverableStage.done, message="Timed out")
        emit(make_event("mco.deliverable", state="failed", error_type="SoftTimeLimitExceeded", duration_s=round(time.monotonic() - t0, 3),
                        extra={"job_id": job_id, "mco_id": mco_id}))
        return
    except Exception as exc:  # pragma: no cover — exercised in tests
        logger.exception(f"Deliverable plan failed for job {job_id}")
        store.update_deliverable_job(job_id, state=JobState.failed, progress=1.0, stage=DeliverableStage.done, message=f"{type(exc).__name__}: {exc}")
        emit(make_event("mco.deliverable", state="failed", error_type=type(exc).__name__, error_message=str(exc)[:500],
                        duration_s=round(time.monotonic() - t0, 3), extra={"job_id": job_id, "mco_id": mco_id}))
        return
    store.update_deliverable_job(job_id, state=JobState.succeeded, progress=1.0, stage=DeliverableStage.done,
                                 message=f"{result.technique} plan, {result.flagged} deviation(s) flagged", deliverable_id=result.deliverable_id)
    emit(make_event("mco.deliverable", state="succeeded", cache_key=result.cache_key, geometry_id=result.geometry_id,
                    duration_s=round(time.monotonic() - t0, 3),
                    extra={"job_id": job_id, "mco_id": mco_id, "deliverable_id": result.deliverable_id, "flagged": result.flagged}))
