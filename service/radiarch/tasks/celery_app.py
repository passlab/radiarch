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
)

if settings.environment == "dev":
    # Run tasks synchronously during development to avoid separate worker requirement
    celery_app.conf.task_always_eager = True
