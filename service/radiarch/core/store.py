"""Temporary in-memory store for plans/jobs until persistence layer is implemented."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict

from ..models.plan import PlanDetail, PlanRequest, PlanSummary
from ..models.job import JobStatus, JobState


class InMemoryStore:
    def __init__(self):
        self._plans: Dict[str, PlanDetail] = {}
        self._jobs: Dict[str, JobStatus] = {}

    def create_plan(self, payload: PlanRequest) -> tuple[PlanDetail, JobStatus]:
        plan_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        detail = PlanDetail(
            id=plan_id,
            workflow_id=payload.workflow_id,
            status=JobState.queued.value,
            created_at=now,
            updated_at=now,
            prescription_gy=payload.prescription_gy,
            artifact_ids=[],
            study_instance_uid=payload.study_instance_uid,
            segmentation_uid=payload.segmentation_uid,
            fraction_count=payload.fraction_count,
            notes=payload.notes,
            job_id=job_id,
        )
        job = JobStatus(id=job_id, plan_id=plan_id, state=JobState.queued, progress=0.0)
        self._plans[plan_id] = detail
        self._jobs[job_id] = job
        return detail, job

    def list_plans(self):
        return list(self._plans.values())

    def get_plan(self, plan_id: str) -> PlanDetail | None:
        return self._plans.get(plan_id)

    def get_job(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        state: JobState | None = None,
        progress: float | None = None,
        message: str | None = None,
    ) -> JobStatus | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        update_data = job.model_dump()
        now = datetime.utcnow()
        if state:
            update_data["state"] = state
            if state == JobState.running and not update_data.get("started_at"):
                update_data["started_at"] = now
            if state in {JobState.succeeded, JobState.failed, JobState.cancelled}:
                update_data["finished_at"] = now
        if progress is not None:
            update_data["progress"] = progress
        if message is not None:
            update_data["message"] = message
        updated = JobStatus(**update_data)
        self._jobs[job_id] = updated
        plan = self._plans.get(job.plan_id)
        if plan:
            plan.status = updated.state.value
            plan.updated_at = datetime.utcnow()
        return updated

    def attach_artifact(self, plan_id: str, artifact_id: str):
        plan = self._plans.get(plan_id)
        if not plan:
            return
        artifacts = list(plan.artifact_ids)
        artifacts.append(artifact_id)
        plan.artifact_ids = artifacts
        plan.updated_at = datetime.utcnow()

    def set_plan_summary(self, plan_id: str, summary: dict):
        plan = self._plans.get(plan_id)
        if not plan:
            return
        plan.qa_summary = summary
        plan.updated_at = datetime.utcnow()


store = InMemoryStore()
