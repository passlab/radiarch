from celery import Celery

from ..config import get_settings

settings = get_settings()

celery_app = Celery(
    "radiarch",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["radiarch.tasks.plan_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    # Production resilience
    task_time_limit=1800,          # 30 min hard kill
    task_soft_time_limit=1500,     # 25 min soft (raises SoftTimeLimitExceeded)
    task_acks_late=True,           # ACK after completion, not before
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_reject_on_worker_lost=True,
)

if settings.environment == "dev":
    # Run tasks synchronously during development to avoid separate worker requirement
    celery_app.conf.task_always_eager = True

