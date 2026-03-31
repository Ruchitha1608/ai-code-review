"""Celery application configuration with Redis broker."""
import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "code_review_bot",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.review", "app.tasks.feedback"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "nightly-prompt-versioning": {
            "task": "app.tasks.feedback.update_prompt_version",
            "schedule": crontab(hour=2, minute=0),  # 2 AM UTC daily
        },
    },
)
