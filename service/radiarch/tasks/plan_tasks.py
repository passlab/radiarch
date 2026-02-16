from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.job import JobState


@celery_app.task(name="radiarch.plan.run")
def run_plan_job(job_id: str, plan_id: str):
    job = store.get_job(job_id)
    plan = store.get_plan(plan_id)
    if not job or not plan:
        logger.error("Job or plan missing for job_id=%s plan_id=%s", job_id, plan_id)
        return

    store.update_job(job_id, state=JobState.running, progress=0.05, message="Starting plan workflow")

    steps: list[tuple[str, float]] = [
        ("Fetching study from Orthanc", 0.20),
        ("Building OpenTPS plan", 0.50),
        ("Running dose engine", 0.80),
        ("Exporting artifacts", 0.95),
    ]

    for message, progress in steps:
        store.update_job(job_id, state=JobState.running, progress=progress, message=message)
        time.sleep(0.1)

    store.attach_artifact(plan_id, artifact_id="mock-artifact-uid")
    store.update_job(job_id, state=JobState.succeeded, progress=1.0, message="Plan completed")
