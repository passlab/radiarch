from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from .celery_app import celery_app
from ..core.store import store
from ..models.job import JobState
from ..core.planner import RadiarchPlanner, PlannerError
from ..adapters import build_orthanc_adapter

planner = RadiarchPlanner(adapter=build_orthanc_adapter())


@celery_app.task(name="radiarch.plan.run")
def run_plan_job(job_id: str, plan_id: str):
    job = store.get_job(job_id)
    plan = store.get_plan(plan_id)
    if not job or not plan:
        logger.error("Job or plan missing for job_id=%s plan_id=%s", job_id, plan_id)
        return

    store.update_job(job_id, state=JobState.running, progress=0.05, message="Starting plan workflow")

    try:
        store.update_job(job_id, state=JobState.running, progress=0.20, message="Fetching study/segmentation")
        result = planner.run(plan)
        store.update_job(job_id, state=JobState.running, progress=0.90, message="Persisting artifacts")
        artifact_id = planner.adapter.store_artifact(result.artifact_bytes, result.artifact_content_type)
        store.attach_artifact(plan_id, artifact_id=artifact_id or "mock-artifact-uid")
        store.set_plan_summary(plan_id, result.qa_summary)
    except PlannerError as exc:
        logger.exception("Planner failed for plan %s", plan_id)
        store.update_job(job_id, state=JobState.failed, progress=1.0, message=str(exc))
        return

    store.update_job(job_id, state=JobState.succeeded, progress=1.0, message="Plan completed")
