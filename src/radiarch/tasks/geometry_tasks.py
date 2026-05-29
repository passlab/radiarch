"""Celery task for async geometry builds.

Lives alongside ``plan_tasks`` and follows the same pattern:

* Accept a ``job_id`` and the serialized :class:`GeometryBuildRequest`.
* Update the DB-backed ``geometry_jobs`` row as the pipeline advances
  through its stages, via the ``progress_callback`` that
  :meth:`GeometryService.build` now accepts.
* On success, stash the returned ``geometry_id`` on the job row so the
  ``GET /api/v1/geometry/jobs/{job_id}`` endpoint can deep-link clients
  to the finished result.

In ``environment=dev`` Celery is in eager mode, so the task runs
synchronously in the API worker process — tests exercise the same code
path as production without requiring a broker.
"""

from __future__ import annotations

import time

from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.geometry import GeometryBuildRequest, GeometryStage
from ..models.job import JobState


@celery_app.task(
    name="radiarch.geometry.build",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def build_geometry_job(job_id: str, request_payload: dict):
    """Execute :meth:`GeometryService.build` and mirror progress to the job row."""
    # Lazy import — keeps Celery worker start fast and avoids circular
    # imports between tasks and the service layer.
    from ..services.geometry import GeometryService

    job = store.get_geometry_job(job_id)
    if not job:
        logger.error("build_geometry_job called with unknown job_id=%s", job_id)
        return

    t0 = time.monotonic()

    def _on_progress(stage: GeometryStage, fraction: float, message: str) -> None:
        # Map the service's stage + fraction onto the job row. ETA is a
        # rough extrapolation; rather than nothing.
        elapsed = time.monotonic() - t0
        eta = None
        if fraction > 0.05:
            eta = max(0.0, elapsed * (1.0 - fraction) / fraction)
        store.update_geometry_job(
            job_id,
            state=JobState.running if fraction < 1.0 else job.state,
            progress=round(fraction, 3),
            stage=stage,
            message=message,
        )
        # Separate write for ETA so we don't clobber stage transitions;
        # update_geometry_job doesn't take eta_seconds (see note on
        # SQL persistence above) — we just log it for now.
        if eta is not None:
            logger.debug(
                "geometry job %s stage=%s progress=%.2f eta=%.1fs",
                job_id,
                stage.value if hasattr(stage, "value") else stage,
                fraction,
                eta,
            )

    try:
        store.update_geometry_job(
            job_id,
            state=JobState.running,
            progress=0.0,
            stage=GeometryStage.queued,
            message="Queued → running",
        )
        request = GeometryBuildRequest.model_validate(request_payload)
        service = GeometryService()
        result = service.build(request, progress_callback=_on_progress)

    except SoftTimeLimitExceeded:
        logger.error("Geometry build timed out for job %s", job_id)
        store.update_geometry_job(
            job_id,
            state=JobState.failed,
            progress=1.0,
            stage=GeometryStage.done,
            message="Timed out",
        )
        return

    except Exception as exc:  # pragma: no cover — defensive; exercised in tests
        logger.exception("Geometry build failed for job %s", job_id)
        store.update_geometry_job(
            job_id,
            state=JobState.failed,
            progress=1.0,
            stage=GeometryStage.done,
            message=f"{type(exc).__name__}: {exc}",
        )
        return

    store.update_geometry_job(
        job_id,
        state=JobState.succeeded,
        progress=1.0,
        stage=GeometryStage.done,
        message=f"Built in {time.monotonic() - t0:.1f}s",
        geometry_id=result.geometry_id,
    )
