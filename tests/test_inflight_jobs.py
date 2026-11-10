"""A request whose inputs already have a job queued or running joins that job instead of dispatching a duplicate.

The store's ``find_active_job`` on both backends (in memory and SQL), the deliverable route the duplicate was found on,
and a source check that every job route asks before it dispatches.
"""

from __future__ import annotations

import re
import types
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from radiarch import app as radiarch_app
from radiarch.api.routes import mco as mco_route
from radiarch.app import create_app
from radiarch.core import store as store_module
from radiarch.core.database import Base
from radiarch.core.store import ACTIVE_JOB_KINDS, InMemoryStore, SQLStore
from radiarch.models.job import JobState
from radiarch.tasks import mco_tasks

ROUTES = Path(store_module.__file__).resolve().parent.parent / "api" / "routes"


def _sql_store() -> SQLStore:
    from radiarch.core import db_models  # noqa: F401 — registers the tables

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return SQLStore(sessionmaker(bind=engine))


@pytest.fixture(params=["memory", "sql"])
def backend(request):
    return InMemoryStore() if request.param == "memory" else _sql_store()


def _create(s, kind: str, key: str):
    if kind in ("dose", "influence"):
        return s.create_dose_job(key, kind=kind)
    return getattr(s, f"create_{kind}_job")(key)


def _update(s, kind: str, job_id: str, state: JobState):
    name = "dose" if kind in ("dose", "influence") else kind
    return getattr(s, f"update_{name}_job")(job_id, state=state)


def _age(s, kind: str, job_id: str, seconds: float) -> None:
    """Move a job's start and creation back by ``seconds``."""
    if isinstance(s, InMemoryStore):
        table = {"dose": s._dose_jobs, "influence": s._dose_jobs, "beam_model": s._beam_model_jobs}.get(kind) or getattr(s, f"_{kind}_jobs")
        job = table[job_id]
        update = {"created_at": job.created_at - timedelta(seconds=seconds)}
        if job.started_at:
            update["started_at"] = job.started_at - timedelta(seconds=seconds)
        table[job_id] = job.model_copy(update=update)
        return
    from radiarch.core import db_models

    rows = {"geometry": "GeometryJobRow", "beam_model": "BeamModelJobRow", "dose": "DoseJobRow", "influence": "DoseJobRow",
            "optimization": "OptimizationJobRow", "bao": "BAOJobRow", "evaluation": "EvaluationJobRow", "autoplan": "AutoplanJobRow",
            "mco": "MCOJobRow", "deliverable": "DeliverableJobRow"}
    row_type = getattr(db_models, rows[kind])
    session = s._session()
    row = session.query(row_type).filter_by(id=job_id).first()
    row.created_at = row.created_at - timedelta(seconds=seconds)
    if row.started_at:
        row.started_at = row.started_at - timedelta(seconds=seconds)
    session.commit()
    session.close()


@pytest.mark.parametrize("kind", ACTIVE_JOB_KINDS)
def test_a_queued_or_running_job_is_found_and_an_ended_one_is_not(backend, kind):
    job = _create(backend, kind, "k1")
    assert backend.find_active_job(kind, "k1", 3600).id == job.id
    assert backend.find_active_job(kind, "k2", 3600) is None
    _update(backend, kind, job.id, JobState.running)
    found = backend.find_active_job(kind, "k1", 3600)
    assert found.id == job.id and found.state == JobState.running
    _update(backend, kind, job.id, JobState.succeeded)
    assert backend.find_active_job(kind, "k1", 3600) is None
    again = _create(backend, kind, "k1")
    _update(backend, kind, again.id, JobState.failed)
    assert backend.find_active_job(kind, "k1", 3600) is None


@pytest.mark.parametrize("kind", ["mco", "deliverable", "autoplan"])
def test_a_job_past_its_time_limit_is_taken_for_lost(backend, kind):
    job = _create(backend, kind, "k1")
    _update(backend, kind, job.id, JobState.running)
    _age(backend, kind, job.id, 7200)
    assert backend.find_active_job(kind, "k1", 3600) is None
    assert backend.find_active_job(kind, "k1", 10800).id == job.id


def test_the_newest_of_two_active_jobs_is_joined(backend):
    old = backend.create_deliverable_job("k1")
    _age(backend, "deliverable", old.id, 60)
    new = backend.create_deliverable_job("k1")
    assert backend.find_active_job("deliverable", "k1", 3600).id == new.id


def test_a_dose_job_and_an_influence_job_are_told_apart(backend):
    dose = backend.create_dose_job("k1", kind="dose")
    assert backend.find_active_job("influence", "k1", 3600) is None
    assert backend.find_active_job("dose", "k1", 3600).id == dose.id


def test_an_unknown_kind_is_refused(backend):
    with pytest.raises(ValueError, match="no job kind"):
        backend.find_active_job("plan", "k1", 3600)


# ---- The route the duplicate was found on -------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    store_module.reset_store()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    monkeypatch.setattr(mco_route, "_known", lambda mco_id: None)
    fake = types.SimpleNamespace(cache_key=lambda mco_id, request: f"{mco_id}:{request.state_id}",
                                 store=types.SimpleNamespace(lookup_by_cache_key=lambda key: None))
    monkeypatch.setattr(mco_route, "_deliverables", lambda: fake)
    dispatched = []
    monkeypatch.setattr(mco_tasks.run_deliverable_job, "delay", lambda *args: dispatched.append(args))
    with TestClient(create_app()) as c:
        c.dispatched = dispatched
        yield c
    store_module.reset_store()


def test_a_repeated_deliverable_request_joins_the_job_in_flight(client):
    first = client.post("/api/v1/mco/m1/deliverable", json={"state_id": "s1"})
    assert first.status_code == 202, first.text
    store_module.store.update_deliverable_job(first.json()["job_id"], state=JobState.running)
    second = client.post("/api/v1/mco/m1/deliverable", json={"state_id": "s1"})
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"] and second.json()["state"] == "running"
    assert len(client.dispatched) == 1
    other = client.post("/api/v1/mco/m1/deliverable", json={"state_id": "s2"})
    assert other.json()["job_id"] != first.json()["job_id"] and len(client.dispatched) == 2


def test_a_request_after_the_job_failed_dispatches_a_new_one(client):
    first = client.post("/api/v1/mco/m1/deliverable", json={"state_id": "s1"}).json()
    store_module.store.update_deliverable_job(first["job_id"], state=JobState.failed)
    again = client.post("/api/v1/mco/m1/deliverable", json={"state_id": "s1"}).json()
    assert again["job_id"] != first["job_id"] and again["state"] == "queued"
    assert len(client.dispatched) == 2


# ---- Every job route asks before it dispatches --------------------------------------------------------------------


def test_every_job_route_joins_a_job_in_flight_before_creating_one():
    for path in sorted(ROUTES.glob("*.py")):
        text = path.read_text()
        creates = re.findall(r"store\.create_(\w+?)_job\(", text)
        joins = re.findall(r"in_flight\(\"(\w+)\"", text)
        assert len(joins) == len(creates), f"{path.name}: {len(creates)} job creation(s), {len(joins)} in_flight check(s)"
        for kind in joins:
            assert kind in ACTIVE_JOB_KINDS, f"{path.name}: unknown kind {kind!r}"
