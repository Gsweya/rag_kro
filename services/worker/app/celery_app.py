"""Celery worker + beat scheduler (spec sections 5-6b, 8).

Tasks:
  - sync_products: re-embed changed product rows (hash-based change detection)
  - sync_documents: re-embed new/changed docs
  - summarize_contacts: re-summarize contact_profiles.notes from recent messages
  - notify_reminders: fire due reminders by sending a gateway message
  - send_digest: optional scheduled notifications
  - health_beat: keeps activity_log fed with worker liveness

Runs as: celery -A app.celery_app.app worker -B -l info -Q default
"""
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from celery import Celery
from celery.schedules import crontab

from rag_kro_shared import get_settings

settings = get_settings()

app = Celery(
    "rag_kro_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.embeddings_sync",
        "app.tasks.summarize",
        "app.tasks.reminders",
        "app.tasks.notifications",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={"app.tasks.*": {"queue": "default"}},
    beat_schedule={
        "product-sync-minute": {
            "task": "app.tasks.embeddings_sync.sync_products",
            "schedule": 60.0,
        },
        "document-sweep-hourly": {
            "task": "app.tasks.embeddings_sync.sync_documents",
            "schedule": 3600.0,
        },
        "summarize-contacts": {
            "task": "app.tasks.summarize.summarize_contacts",
            "schedule": 1800.0,
            "args": (100,),
        },
        "reminders-every-minute": {
            "task": "app.tasks.reminders.notify_reminders",
            "schedule": 60.0,
        },
        "worker-health": {
            "task": "app.tasks.notifications.health_beat",
            "schedule": crontab(minute="*/5"),
        },
    },
)


if __name__ == "__main__":
    app.start()