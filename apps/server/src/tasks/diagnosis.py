from __future__ import annotations

import logging
from typing import Any

from celery import Task

from celery_app import DIAGNOSIS_QUEUE, DIAGNOSIS_TASK_NAME, celery_app
from tasks.handlers import mark_diagnosis_failed, process_diagnosis_job
from tasks.runtime import JobPayload, ensure_task_runtime, run_coroutine
from tasks.shared import is_final_attempt, retry_countdown

LOGGER = logging.getLogger(__name__)
DIAGNOSIS_MAX_RETRIES = 3


@celery_app.task(bind=True, max_retries=DIAGNOSIS_MAX_RETRIES, name=DIAGNOSIS_TASK_NAME)
def process_diagnosis_task(
    self: Task,
    *,
    job_id: str,
    product_id: str,
    shop_id: str,
    snapshot: dict[str, Any],
    snapshot_hash: str,
    window: str,
) -> None:
    _process_diagnosis_task(
        self,
        job_id=job_id,
        product_id=product_id,
        shop_id=shop_id,
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        window=window,
    )


def _process_diagnosis_task(
    task: Task,
    *,
    job_id: str,
    product_id: str,
    shop_id: str,
    snapshot: dict[str, Any],
    snapshot_hash: str,
    window: str,
) -> None:
    ensure_task_runtime()
    job: JobPayload = {
        "job_id": job_id,
        "product_id": product_id,
        "shop_id": shop_id,
        "snapshot": snapshot,
        "snapshot_hash": snapshot_hash,
        "window": window,
    }
    LOGGER.info(
        "job claimed job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s",
        job_id,
        product_id,
        DIAGNOSIS_QUEUE,
        shop_id,
        window,
    )
    try:
        run_coroutine(process_diagnosis_job(job=job))
    except Exception as exc:
        LOGGER.exception(
            "job failed job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s error=%s",
            job_id,
            product_id,
            DIAGNOSIS_QUEUE,
            shop_id,
            window,
            exc,
        )
        if is_final_attempt(task):
            try:
                run_coroutine(mark_diagnosis_failed(job=job, error=exc))
            except Exception as failure_exc:
                LOGGER.exception(
                    "diagnosis failure persistence failed job_id=%s product_id=%s shop_id=%s window=%s error=%s",
                    job_id,
                    product_id,
                    shop_id,
                    window,
                    failure_exc,
                )
            LOGGER.error(
                "job failed permanently job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s error=%s",
                job_id,
                product_id,
                DIAGNOSIS_QUEUE,
                shop_id,
                window,
                exc,
            )
            raise
        raise task.retry(exc=exc, countdown=retry_countdown(task)) from exc

    LOGGER.info(
        "job completed job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s",
        job_id,
        product_id,
        DIAGNOSIS_QUEUE,
        shop_id,
        window,
    )
