from __future__ import annotations

import os

from celery import Celery
from pydantic import ValidationError

from config import Settings, get_settings

ROLLUP_QUEUE = "sku-lens:rollups"
DIAGNOSIS_QUEUE = "sku-lens:diagnoses"

ROLLUP_TASK_NAME = "sku_lens.rollup.process"
DIAGNOSIS_TASK_NAME = "sku_lens.diagnosis.process"
DUE_SHOP_ROLLUPS_TASK_NAME = "sku_lens.rollup.scan_due_shops"


def broker_url() -> str:
    try:
        settings = get_settings()
        return settings.celery_broker_url or settings.redis_url
    except ValidationError:
        pass

    return os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"


def configure_celery(settings: Settings) -> None:
    celery_app.conf.update(broker_url=settings.celery_broker_url or settings.redis_url)


celery_app = Celery(
    "sku_lens",
    broker=broker_url(),
    include=["tasks.diagnosis", "tasks.rollups"],
)
celery_app.conf.update(
    accept_content=["json"],
    enable_utc=True,
    result_backend=None,
    result_serializer="json",
    task_acks_late=True,
    task_ignore_result=True,
    task_reject_on_worker_lost=True,
    task_routes={
        ROLLUP_TASK_NAME: {"queue": ROLLUP_QUEUE},
        DIAGNOSIS_TASK_NAME: {"queue": DIAGNOSIS_QUEUE},
        DUE_SHOP_ROLLUPS_TASK_NAME: {"queue": ROLLUP_QUEUE},
    },
    task_serializer="json",
    timezone="UTC",
    worker_prefetch_multiplier=1,
)
celery_app.conf.beat_schedule = {
    "run-due-shop-rollups": {
        "task": DUE_SHOP_ROLLUPS_TASK_NAME,
        "schedule": 60.0,
        "options": {"queue": ROLLUP_QUEUE},
    }
}
