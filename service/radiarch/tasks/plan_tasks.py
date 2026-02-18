"""Celery task for running treatment plan jobs.

Phase 5: structured stages, ETA estimation, retry policies,
SoftTimeLimitExceeded handling, and DICOMweb STOW-RS push.
"""

from __future__ import annotations

import time
import traceback

from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.job import JobState
from ..core.planner import RadiarchPlanner, PlannerError
from ..adapters import build_orthanc_adapter
from ..adapters.dicomweb import get_dicomweb_notifier

planner = RadiarchPlanner(adapter=build_orthanc_adapter())


@celery_app.task(
    name="radiarch.plan.run",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def run_plan_job(job_id: str, plan_id: str):
    job = store.get_job(job_id)
    plan = store.get_plan(plan_id)
    if not job or not plan:
        logger.error("Job or plan missing for job_id=%s plan_id=%s", job_id, plan_id)
        return

    t0 = time.monotonic()

    def _elapsed():
        return round(time.monotonic() - t0, 1)

    try:
        # Stage 1: Initializing
        store.update_job(
            job_id, state=JobState.running, progress=0.05,
            message="Starting plan workflow", stage="initializing",
        )

        # Stage 2: Fetching data
        store.update_job(
            job_id, state=JobState.running, progress=0.15,
            message="Fetching study/segmentation", stage="fetching",
            eta_seconds=max(0, 30 - _elapsed()),
        )

        # Stage 3: Computing dose
        store.update_job(
            job_id, state=JobState.running, progress=0.20,
            message="Running dose calculation", stage="computing",
            eta_seconds=max(0, 120 - _elapsed()),
        )
        result = planner.run(plan)

        # Stage 4: Persisting artifacts
        store.update_job(
            job_id, state=JobState.running, progress=0.85,
            message="Persisting artifacts", stage="persisting",
            eta_seconds=max(0, 10 - (time.monotonic() - t0 - 100)),
        )

        # Register RTDOSE artifact if available
        rtdose_path = result.qa_summary.get("rtdosePath")
        if rtdose_path:
            store.register_artifact(
                plan_id, rtdose_path,
                content_type="application/dicom", file_name="RTDOSE.dcm",
            )

        # Register the JSON summary artifact
        if result.artifact_path:
            store.register_artifact(
                plan_id, result.artifact_path,
                content_type=result.artifact_content_type,
            )

        store.set_plan_summary(plan_id, result.qa_summary)

        # Stage 5: DICOMweb STOW-RS push (non-fatal)
        notifier = get_dicomweb_notifier()
        if notifier.enabled and rtdose_path:
            store.update_job(
                job_id, state=JobState.running, progress=0.92,
                message="Pushing to PACS via STOW-RS", stage="pushing",
            )
            try:
                with open(rtdose_path, "rb") as f:
                    notifier.store_instances(f.read())
            except Exception as exc:
                logger.warning("DICOMweb push failed (non-fatal): %s", exc)

    except SoftTimeLimitExceeded:
        logger.error("Soft time limit exceeded for plan %s (elapsed %.1fs)", plan_id, _elapsed())
        store.update_job(
            job_id, state=JobState.failed, progress=1.0,
            message=f"Timed out after {_elapsed():.0f}s", stage="timeout",
        )
        return

    except PlannerError as exc:
        logger.exception("Planner failed for plan %s", plan_id)
        store.update_job(
            job_id, state=JobState.failed, progress=1.0,
            message=str(exc), stage="error",
        )
        return

    except Exception as exc:
        logger.exception("Unexpected error in plan %s", plan_id)
        store.update_job(
            job_id, state=JobState.failed, progress=1.0,
            message=f"Internal error: {exc}", stage="error",
        )
        return

    store.update_job(
        job_id, state=JobState.succeeded, progress=1.0,
        message=f"Plan completed in {_elapsed():.1f}s", stage="done",
        eta_seconds=0,
    )
