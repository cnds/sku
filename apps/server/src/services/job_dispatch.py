from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any
from uuid import uuid4

from celery_app import DIAGNOSIS_QUEUE, DIAGNOSIS_TASK_NAME, ROLLUP_QUEUE, ROLLUP_TASK_NAME, celery_app

AfterCommitCallback = Callable[[], Awaitable[object]]
LOGGER = logging.getLogger(__name__)


class AfterCommitCallbacks:
    def __init__(self) -> None:
        self._callbacks: list[AfterCommitCallback] = []

    def add(self, action: AfterCommitCallback) -> None:
        self._callbacks.append(action)

    async def run(self) -> None:
        for action in self._callbacks:
            await action()


class JobDispatchService:
    def enqueue_rollups(
        self,
        *,
        after_commit_callbacks: AfterCommitCallbacks,
        shop_id: str,
        stat_dates: list[date],
    ) -> list[str]:
        job_ids: list[str] = []
        for stat_date in sorted(set(stat_dates)):
            job_id = uuid4().hex
            job_ids.append(job_id)

            async def _enqueue_rollup_job(*, stat_date: date = stat_date, job_id: str = job_id) -> None:
                payload = {
                    "job_id": job_id,
                    "shop_id": shop_id,
                    "stat_date": stat_date.isoformat(),
                }
                success = _send_task(
                    task_name=ROLLUP_TASK_NAME,
                    kwargs=payload,
                    queue_name=ROLLUP_QUEUE,
                    task_id=job_id,
                )
                LOGGER.log(
                    logging.INFO if success else logging.ERROR,
                    "job %s job_id=%s queue_name=%s shop_id=%s stat_date=%s",
                    "enqueued" if success else "enqueue failed",
                    job_id,
                    ROLLUP_QUEUE,
                    shop_id,
                    stat_date,
                )

            after_commit_callbacks.add(
                _enqueue_rollup_job,
            )
        return job_ids

    def enqueue_rollup(
        self,
        *,
        after_commit_callbacks: AfterCommitCallbacks,
        shop_id: str,
        stat_date: date,
    ) -> list[str]:
        return self.enqueue_rollups(
            after_commit_callbacks=after_commit_callbacks,
            shop_id=shop_id,
            stat_dates=[stat_date],
        )

    def enqueue_diagnosis(
        self,
        *,
        product_id: str,
        after_commit_callbacks: AfterCommitCallbacks,
        shop_id: str,
        snapshot: dict[str, Any],
        snapshot_hash: str,
        window: str,
    ) -> str:
        job_id = uuid4().hex

        async def _enqueue_diagnosis_job() -> None:
            payload = {
                "job_id": job_id,
                "product_id": product_id,
                "shop_id": shop_id,
                "snapshot": snapshot,
                "snapshot_hash": snapshot_hash,
                "window": window,
            }
            success = _send_task(
                task_name=DIAGNOSIS_TASK_NAME,
                kwargs=payload,
                queue_name=DIAGNOSIS_QUEUE,
                task_id=job_id,
            )
            LOGGER.log(
                logging.INFO if success else logging.ERROR,
                "job %s job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s",
                "enqueued" if success else "enqueue failed",
                job_id,
                product_id,
                DIAGNOSIS_QUEUE,
                shop_id,
                window,
            )

        after_commit_callbacks.add(
            _enqueue_diagnosis_job,
        )
        return job_id


def _send_task(
    *,
    kwargs: dict[str, object],
    queue_name: str,
    task_id: str,
    task_name: str,
) -> bool:
    try:
        celery_app.send_task(
            task_name,
            kwargs=kwargs,
            queue=queue_name,
            task_id=task_id,
        )
        return True
    except Exception as exc:
        LOGGER.exception(
            "task publish failed task_name=%s queue_name=%s job_id=%s product_id=%s shop_id=%s error=%s",
            task_name,
            queue_name,
            task_id,
            kwargs.get("product_id"),
            kwargs.get("shop_id"),
            exc,
        )
        return False
