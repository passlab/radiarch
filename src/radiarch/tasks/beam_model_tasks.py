"""Celery task for async beam-model builds.

Mirrors ``build_geometry_job`` from ``geometry_tasks.py``: pull the job
from the store, execute :meth:`BeamModelService.build` with a progress
callback that mirrors stages and progress to the DB row, and on success
stash the resulting ``beam_model_id`` so polling clients can deep-link.
"""

from __future__ import annotations

import time

from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.beam_model import BeamModelBuildRequest, BeamModelStage
from ..models.job import JobState


@celery_app.task(
    name="radiarch.beam_model.build",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def build_beam_model_job(job_id: str, request_payload: dict):
    """Execute :meth:`BeamModelService.build` and mirror progress to the job row."""
    # Lazy import keeps Celery worker boot fast and avoids circular imports.
    from ..services.beam_model import BeamModelService

    job = store.get_beam_model_job(job_id)
    if not job:
        logger.error("build_beam_model_job called with unknown job_id=%s", job_id)
        return

    t0 = time.monotonic()

    def _on_progress(stage: BeamModelStage, fraction: float, message: str) -> None:
        store.update_beam_model_job(
            job_id,
            state=JobState.running if fraction < 1.0 else job.state,
            progress=round(fraction, 3),
            stage=stage,
            message=message,
        )

    try:
        store.update_beam_model_job(
            job_id,
            state=JobState.running,
            progress=0.0,
            stage=BeamModelStage.queued,
            message="Queued → running",
        )
        request = BeamModelBuildRequest.model_validate(request_payload)
        service = BeamModelService()
        result = service.build(request, progress_callback=_on_progress)

    except SoftTimeLimitExceeded:
        logger.error("Beam model build timed out for job %s", job_id)
        store.update_beam_model_job(
            job_id,
            state=JobState.failed,
            progress=1.0,
            stage=BeamModelStage.done,
            message="Timed out",
        )
        return

    except Exception as exc:  # pragma: no cover — exercised in tests
        logger.exception("Beam model build failed for job %s", job_id)
        store.update_beam_model_job(
            job_id,
            state=JobState.failed,
            progress=1.0,
            stage=BeamModelStage.done,
            message=f"{type(exc).__name__}: {exc}",
        )
        return

    store.update_beam_model_job(
        job_id,
        state=JobState.succeeded,
        progress=1.0,
        stage=BeamModelStage.done,
        message=f"Built in {time.monotonic() - t0:.1f}s",
        beam_model_id=result.beam_model_id,
    )
