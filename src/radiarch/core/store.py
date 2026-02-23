"""Store abstraction: StoreBase ABC, InMemoryStore, and SQLStore.

Tests use InMemoryStore.  Production uses SQLStore when RADIARCH_DATABASE_URL is set.
"""

from __future__ import annotations

import abc
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..models.plan import PlanDetail, PlanRequest, PlanSummary
from ..models.job import JobStatus, JobState
from ..models.artifact import ArtifactRecord


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class StoreBase(abc.ABC):
    """Interface that InMemoryStore and SQLStore both implement."""

    @abc.abstractmethod
    def create_plan(self, payload: PlanRequest) -> tuple[PlanDetail, JobStatus]: ...

    @abc.abstractmethod
    def list_plans(self) -> List[PlanSummary]: ...

    @abc.abstractmethod
    def get_plan(self, plan_id: str) -> Optional[PlanDetail]: ...

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[JobStatus]: ...

    @abc.abstractmethod
    def update_job(
        self,
        job_id: str,
        *,
        state: Optional[JobState] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        stage: Optional[str] = None,
        eta_seconds: Optional[float] = None,
    ) -> Optional[JobStatus]: ...

    @abc.abstractmethod
    def register_artifact(
        self,
        plan_id: str,
        file_path: str,
        content_type: str = "application/dicom",
        file_name: str = "",
    ) -> Optional[str]: ...

    @abc.abstractmethod
    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]: ...

    @abc.abstractmethod
    def attach_artifact(self, plan_id: str, artifact_id: str) -> None: ...

    @abc.abstractmethod
    def set_plan_summary(self, plan_id: str, summary: dict) -> None: ...

    @abc.abstractmethod
    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan and all associated jobs/artifacts. Returns True if deleted."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (used in tests & dev)
# ---------------------------------------------------------------------------

class InMemoryStore(StoreBase):
    def __init__(self):
        self._plans: Dict[str, PlanDetail] = {}
        self._jobs: Dict[str, JobStatus] = {}
        self._artifacts: Dict[str, ArtifactRecord] = {}

    def create_plan(self, payload: PlanRequest) -> tuple[PlanDetail, JobStatus]:
        plan_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        now = _utcnow()
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
            beam_count=payload.beam_count,
            notes=payload.notes,
            job_id=job_id,
            objectives=payload.objectives,
            robustness=payload.robustness,
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
        stage: str | None = None,
        eta_seconds: float | None = None,
    ) -> JobStatus | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        update_data = job.model_dump()
        now = _utcnow()
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
        if stage is not None:
            update_data["stage"] = stage
        if eta_seconds is not None:
            update_data["eta_seconds"] = eta_seconds
        updated = JobStatus(**update_data)
        self._jobs[job_id] = updated
        plan = self._plans.get(job.plan_id)
        if plan:
            plan.status = updated.state.value
            plan.updated_at = _utcnow()
        return updated

    def register_artifact(
        self,
        plan_id: str,
        file_path: str,
        content_type: str = "application/dicom",
        file_name: str = "",
    ) -> Optional[str]:
        artifact_id = str(uuid.uuid4())
        record = ArtifactRecord(
            id=artifact_id,
            plan_id=plan_id,
            file_path=file_path,
            content_type=content_type,
            file_name=file_name or file_path.rsplit("/", 1)[-1],
            created_at=_utcnow(),
        )
        self._artifacts[artifact_id] = record
        self.attach_artifact(plan_id, artifact_id)
        return artifact_id

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        return self._artifacts.get(artifact_id)

    def attach_artifact(self, plan_id: str, artifact_id: str):
        plan = self._plans.get(plan_id)
        if not plan:
            return
        artifacts = list(plan.artifact_ids)
        artifacts.append(artifact_id)
        plan.artifact_ids = artifacts
        plan.updated_at = _utcnow()

    def set_plan_summary(self, plan_id: str, summary: dict):
        plan = self._plans.get(plan_id)
        if not plan:
            return
        plan.qa_summary = summary
        plan.updated_at = _utcnow()

    def delete_plan(self, plan_id: str) -> bool:
        plan = self._plans.pop(plan_id, None)
        if not plan:
            return False
        # Remove associated job
        if plan.job_id:
            self._jobs.pop(plan.job_id, None)
        # Remove associated artifacts
        artifact_ids_to_remove = [aid for aid, a in self._artifacts.items() if a.plan_id == plan_id]
        for aid in artifact_ids_to_remove:
            self._artifacts.pop(aid, None)
        return True


# ---------------------------------------------------------------------------
# SQL implementation (production)
# ---------------------------------------------------------------------------

class SQLStore(StoreBase):
    """Persistent store backed by SQLAlchemy."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def _session(self):
        return self._session_factory()

    def create_plan(self, payload: PlanRequest) -> tuple[PlanDetail, JobStatus]:
        from .db_models import PlanRow, JobRow

        plan_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        now = _utcnow()

        session = self._session()
        try:
            plan_row = PlanRow(
                id=plan_id,
                workflow_id=payload.workflow_id.value if hasattr(payload.workflow_id, 'value') else payload.workflow_id,
                status=JobState.queued.value,
                study_instance_uid=payload.study_instance_uid,
                segmentation_uid=payload.segmentation_uid,
                prescription_gy=payload.prescription_gy,
                fraction_count=payload.fraction_count,
                beam_count=payload.beam_count,
                notes=payload.notes,
                job_id=job_id,
                objectives=[obj.model_dump() for obj in payload.objectives] if payload.objectives else None,
                robustness=payload.robustness.model_dump() if payload.robustness else None,
                created_at=now,
                updated_at=now,
            )
            job_row = JobRow(
                id=job_id,
                plan_id=plan_id,
                state=JobState.queued.value,
                progress=0.0,
                started_at=None,
                finished_at=None,
            )
            session.add(plan_row)
            session.add(job_row)
            session.commit()

            detail = self._plan_row_to_detail(plan_row, session)
            job = self._job_row_to_status(job_row)
            return detail, job
        finally:
            session.close()

    def list_plans(self) -> list:
        from .db_models import PlanRow

        session = self._session()
        try:
            rows = session.query(PlanRow).order_by(PlanRow.created_at.desc()).all()
            return [self._plan_row_to_detail(r, session) for r in rows]
        finally:
            session.close()

    def get_plan(self, plan_id: str) -> Optional[PlanDetail]:
        from .db_models import PlanRow

        session = self._session()
        try:
            row = session.query(PlanRow).filter_by(id=plan_id).first()
            if not row:
                return None
            return self._plan_row_to_detail(row, session)
        finally:
            session.close()

    def get_job(self, job_id: str) -> Optional[JobStatus]:
        from .db_models import JobRow

        session = self._session()
        try:
            row = session.query(JobRow).filter_by(id=job_id).first()
            if not row:
                return None
            return self._job_row_to_status(row)
        finally:
            session.close()

    def update_job(
        self,
        job_id: str,
        *,
        state: Optional[JobState] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        stage: Optional[str] = None,
        eta_seconds: Optional[float] = None,
    ) -> Optional[JobStatus]:
        from .db_models import JobRow, PlanRow

        session = self._session()
        try:
            row = session.query(JobRow).filter_by(id=job_id).first()
            if not row:
                return None
            now = _utcnow()
            if state:
                row.state = state.value if hasattr(state, 'value') else state
                if state == JobState.running and not row.started_at:
                    row.started_at = now
                if state in {JobState.succeeded, JobState.failed, JobState.cancelled}:
                    row.finished_at = now
            if progress is not None:
                row.progress = progress
            if message is not None:
                row.message = message
            # Note: stage/eta_seconds are transient (not stored in SQL).
            # They are only meaningful for InMemoryStore or real-time queries.
            # Update plan status
            plan_row = session.query(PlanRow).filter_by(id=row.plan_id).first()
            if plan_row:
                plan_row.status = row.state
                plan_row.updated_at = now
            session.commit()
            return self._job_row_to_status(row)
        finally:
            session.close()

    def register_artifact(
        self,
        plan_id: str,
        file_path: str,
        content_type: str = "application/dicom",
        file_name: str = "",
    ) -> Optional[str]:
        from .db_models import ArtifactRow

        artifact_id = str(uuid.uuid4())
        session = self._session()
        try:
            row = ArtifactRow(
                id=artifact_id,
                plan_id=plan_id,
                file_path=file_path,
                content_type=content_type,
                file_name=file_name or file_path.rsplit("/", 1)[-1],
                created_at=_utcnow(),
            )
            session.add(row)
            session.commit()
            return artifact_id
        finally:
            session.close()

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        from .db_models import ArtifactRow

        session = self._session()
        try:
            row = session.query(ArtifactRow).filter_by(id=artifact_id).first()
            if not row:
                return None
            return ArtifactRecord(
                id=row.id,
                plan_id=row.plan_id,
                file_path=row.file_path,
                content_type=row.content_type,
                file_name=row.file_name,
                created_at=row.created_at,
            )
        finally:
            session.close()

    def attach_artifact(self, plan_id: str, artifact_id: str) -> None:
        # In SQL store, artifacts are linked via plan_id FK — no separate attach needed.
        pass

    def set_plan_summary(self, plan_id: str, summary: dict) -> None:
        from .db_models import PlanRow

        session = self._session()
        try:
            row = session.query(PlanRow).filter_by(id=plan_id).first()
            if row:
                row.qa_summary = summary
                row.updated_at = _utcnow()
                session.commit()
        finally:
            session.close()

    def delete_plan(self, plan_id: str) -> bool:
        from .db_models import PlanRow

        session = self._session()
        try:
            row = session.query(PlanRow).filter_by(id=plan_id).first()
            if not row:
                return False
            session.delete(row)  # cascade deletes jobs + artifacts
            session.commit()
            return True
        finally:
            session.close()

    # -- helpers --

    @staticmethod
    def _plan_row_to_detail(row, session) -> PlanDetail:
        from .db_models import ArtifactRow
        from ..models.plan import DoseObjective, RobustnessConfig

        artifact_ids = [
            a.id for a in session.query(ArtifactRow).filter_by(plan_id=row.id).all()
        ]

        # Deserialize objectives from JSON
        objectives = None
        if row.objectives:
            objectives = [DoseObjective(**obj) for obj in row.objectives]

        # Deserialize robustness from JSON
        robustness = None
        if row.robustness:
            robustness = RobustnessConfig(**row.robustness)

        return PlanDetail(
            id=row.id,
            workflow_id=row.workflow_id,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            prescription_gy=row.prescription_gy,
            artifact_ids=artifact_ids,
            study_instance_uid=row.study_instance_uid,
            segmentation_uid=row.segmentation_uid,
            fraction_count=row.fraction_count,
            beam_count=getattr(row, 'beam_count', 1) or 1,
            notes=row.notes,
            job_id=row.job_id,
            qa_summary=row.qa_summary,
            objectives=objectives,
            robustness=robustness,
        )

    @staticmethod
    def _job_row_to_status(row) -> JobStatus:
        return JobStatus(
            id=row.id,
            plan_id=row.plan_id,
            state=row.state,
            progress=row.progress,
            message=row.message,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )


# ---------------------------------------------------------------------------
# Factory + module-level convenience
# ---------------------------------------------------------------------------

_store: Optional[StoreBase] = None


def get_store() -> StoreBase:
    """Return the configured store instance.

    - If RADIARCH_DATABASE_URL is set and non-empty → SQLStore
    - Otherwise (tests, dev) → InMemoryStore
    """
    global _store
    if _store is not None:
        return _store

    db_url = os.environ.get("RADIARCH_DATABASE_URL", "")
    if db_url:
        from . import database
        database.get_engine()  # ensure engine is built
        if database.SessionLocal is not None:
            _store = SQLStore(database.SessionLocal)
        else:
            _store = InMemoryStore()
    else:
        _store = InMemoryStore()
    return _store


def reset_store():
    """Reset the global store (for testing)."""
    global _store
    _store = None


# Backwards-compatible module-level singleton (used by existing code).
# Uses a lazy proxy so that get_store() is called on first attribute access,
# allowing config (RADIARCH_DATABASE_URL) to determine the store type.
class _StoreProxy:
    """Lazy proxy that forwards all attribute access to get_store()."""
    def __getattr__(self, name):
        return getattr(get_store(), name)

store = _StoreProxy()
