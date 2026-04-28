from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from job_queue import enqueue_json

AfterCommitCallback = Callable[[], Awaitable[object]]


class AfterCommitCallbacks:
    def __init__(self) -> None:
        self._callbacks: list[AfterCommitCallback] = []

    def add(self, action: AfterCommitCallback) -> None:
        self._callbacks.append(action)

    async def run(self) -> None:
        for action in self._callbacks:
            await action()


class JobDispatchService:
    def enqueue_rollup(
        self,
        *,
        after_commit_callbacks: AfterCommitCallbacks,
        shop_id: str,
        stat_date: date,
    ) -> None:
        after_commit_callbacks.add(
            lambda: enqueue_json(
                payload={"shop_id": shop_id, "stat_date": stat_date.isoformat()},
                queue_name="sku-lens:rollups",
            ),
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
    ) -> None:
        after_commit_callbacks.add(
            lambda: enqueue_json(
                payload={
                    "product_id": product_id,
                    "shop_id": shop_id,
                    "snapshot": snapshot,
                    "snapshot_hash": snapshot_hash,
                    "window": window,
                },
                queue_name="sku-lens:diagnoses",
            ),
        )
