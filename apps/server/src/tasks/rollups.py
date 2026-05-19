from __future__ import annotations

import logging

from celery import Task

from celery_app import DUE_SHOP_ROLLUPS_TASK_NAME, ROLLUP_QUEUE, ROLLUP_TASK_NAME, celery_app
from tasks.handlers import process_rollup_job
from tasks.runtime import JobPayload, ensure_task_runtime, run_coroutine
from tasks.scheduler import run_due_shop_rollups
from tasks.shared import is_final_attempt, retry_countdown

LOGGER = logging.getLogger(__name__)
ROLLUP_MAX_RETRIES = 3


@celery_app.task(bind=True, max_retries=ROLLUP_MAX_RETRIES, name=ROLLUP_TASK_NAME)
def process_rollup_task(
    self: Task,
    *,
    job_id: str,
    shop_id: str,
    stat_date: str,
) -> None:
    _process_rollup_task(
        self,
        job_id=job_id,
        shop_id=shop_id,
        stat_date=stat_date,
    )


@celery_app.task(bind=True, max_retries=ROLLUP_MAX_RETRIES, name=DUE_SHOP_ROLLUPS_TASK_NAME)
def run_due_shop_rollups_task(self: Task) -> None:
    _process_due_shop_rollups_task(self)


def _process_rollup_task(
    task: Task,
    *,
    job_id: str,
    shop_id: str,
    stat_date: str,
) -> None:
    ensure_task_runtime()
    job: JobPayload = {
        "job_id": job_id,
        "shop_id": shop_id,
        "stat_date": stat_date,
    }
    LOGGER.info(
        "job claimed job_id=%s queue_name=%s shop_id=%s stat_date=%s",
        job_id,
        ROLLUP_QUEUE,
        shop_id,
        stat_date,
    )
    try:
        run_coroutine(process_rollup_job(job=job))
    except Exception as exc:
        LOGGER.exception(
            "job failed job_id=%s queue_name=%s shop_id=%s stat_date=%s error=%s",
            job_id,
            ROLLUP_QUEUE,
            shop_id,
            stat_date,
            exc,
        )
        if is_final_attempt(task):
            LOGGER.error(
                "job failed permanently job_id=%s queue_name=%s shop_id=%s stat_date=%s error=%s",
                job_id,
                ROLLUP_QUEUE,
                shop_id,
                stat_date,
                exc,
            )
            raise
        raise task.retry(exc=exc, countdown=retry_countdown(task)) from exc

    LOGGER.info(
        "job completed job_id=%s queue_name=%s shop_id=%s stat_date=%s",
        job_id,
        ROLLUP_QUEUE,
        shop_id,
        stat_date,
    )


def _process_due_shop_rollups_task(task: Task) -> None:
    ensure_task_runtime()
    job_id = str(getattr(task.request, "id", "") or "")
    LOGGER.info(
        "job claimed job_id=%s queue_name=%s task_name=%s",
        job_id,
        ROLLUP_QUEUE,
        DUE_SHOP_ROLLUPS_TASK_NAME,
    )
    try:
        processed = run_coroutine(run_due_shop_rollups())
    except Exception as exc:
        LOGGER.exception(
            "job failed job_id=%s queue_name=%s task_name=%s error=%s",
            job_id,
            ROLLUP_QUEUE,
            DUE_SHOP_ROLLUPS_TASK_NAME,
            exc,
        )
        if is_final_attempt(task):
            LOGGER.error(
                "job failed permanently job_id=%s queue_name=%s task_name=%s error=%s",
                job_id,
                ROLLUP_QUEUE,
                DUE_SHOP_ROLLUPS_TASK_NAME,
                exc,
            )
            raise
        raise task.retry(exc=exc, countdown=retry_countdown(task)) from exc

    LOGGER.info(
        "job completed job_id=%s queue_name=%s task_name=%s processed=%s",
        job_id,
        ROLLUP_QUEUE,
        DUE_SHOP_ROLLUPS_TASK_NAME,
        processed,
    )
