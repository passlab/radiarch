"""A request whose inputs already have a job queued or running joins that job instead of dispatching a duplicate.

Each job route answers a request in one of three ways: the stored result (200, the cache), the job already working on
the same inputs (202, its ``job_id``), or a new job (202). Without the middle case a repeated request (a client that
retries, a viewer reloaded while a Pareto set is being made deliverable) starts the same computation again.
"""

from __future__ import annotations

from ...core.store import store


def in_flight(kind: str, cache_key: str, task: str):
    """The queued or running ``kind`` job for ``cache_key``, or ``None``.

    A job older than ``task``'s hard time limit is taken for lost (its worker stopped before the job could record an
    end), and the request dispatches a new one."""
    from ...tasks.celery_app import celery_app

    limit = (celery_app.conf.task_annotations or {}).get(task, {}).get("time_limit") or celery_app.conf.task_time_limit
    return store.find_active_job(kind, cache_key, max_age_s=float(limit))
