from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from typing import cast

from config import Settings, get_settings
from db import DatabaseSessionFactory, create_session_factory, db_session_context, init_db
from job_queue import (
    acknowledge_claimed_json,
    claim_json,
    close_redis_client,
    init_redis_client,
    requeue_claimed_json,
    restore_claimed_json,
)
from schemas import ProductSnapshot, TimeWindow
from services.diagnosis import ProductDiagnosisService
from services.gemini import GeminiDiagnosisService
from services.rollups import DailyRollupService

ROLLUP_QUEUE = "sku-lens:rollups"
ROLLUP_PROCESSING_QUEUE = "sku-lens:rollups:processing"
DIAGNOSIS_QUEUE = "sku-lens:diagnoses"
DIAGNOSIS_PROCESSING_QUEUE = "sku-lens:diagnoses:processing"

type JobPayload = dict[str, object]

@dataclass(slots=True)
class WorkerRuntime:
    session_factory: DatabaseSessionFactory
    settings: Settings


_worker_runtime: WorkerRuntime | None = None


def init_worker_runtime(
    *,
    settings: Settings,
    session_factory: DatabaseSessionFactory | None = None,
) -> WorkerRuntime:
    runtime = WorkerRuntime(
        session_factory=session_factory or create_session_factory(settings.database_url),
        settings=settings,
    )
    global _worker_runtime
    _worker_runtime = runtime
    return runtime


def get_worker_runtime() -> WorkerRuntime:
    runtime = _worker_runtime
    if runtime is None:
        raise RuntimeError("Worker runtime has not been initialized.")
    return runtime


async def close_worker_runtime() -> None:
    global _worker_runtime
    runtime = _worker_runtime
    if runtime is None:
        return

    _worker_runtime = None
    await runtime.session_factory.engine.dispose()


async def main_async(poll_interval_seconds: float = 1.0) -> None:
    settings = get_settings()
    runtime = init_worker_runtime(settings=settings)
    await init_db(runtime.session_factory.engine)
    init_redis_client(settings.redis_url)

    try:
        await _restore_inflight_jobs()
        while True:
            processed = 0
            processed += await _drain_rollups()
            processed += await _drain_diagnoses()

            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)
    finally:
        await close_redis_client()
        await close_worker_runtime()


def main() -> None:
    asyncio.run(main_async())


async def process_rollup_job(
    *,
    job: JobPayload,
) -> None:
    async with db_session_context(get_worker_runtime().session_factory) as session:
        try:
            await DailyRollupService().rollup_day(
                shop_id=str(job["shop_id"]),
                stat_date=date.fromisoformat(str(job["stat_date"])),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def process_diagnosis_job(
    *,
    job: JobPayload,
) -> None:
    snapshot_payload = cast(dict[str, object], job["snapshot"])
    snapshot = ProductSnapshot.model_validate(snapshot_payload)
    runtime = get_worker_runtime()
    report_markdown, summary = await GeminiDiagnosisService(runtime.settings).generate_report(
        snapshot=snapshot
    )

    async with db_session_context(runtime.session_factory) as session:
        try:
            await ProductDiagnosisService().store_generated_report(
                product_id=str(job["product_id"]),
                report_markdown=report_markdown,
                shop_id=str(job["shop_id"]),
                snapshot_hash=str(job["snapshot_hash"]),
                summary_json=summary,
                window=TimeWindow(str(job["window"])),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _drain_rollups() -> int:
    payload = await claim_json(
        queue_name=ROLLUP_QUEUE,
        processing_queue_name=ROLLUP_PROCESSING_QUEUE,
    )
    if payload is None:
        return 0

    try:
        await process_rollup_job(
            job=cast(JobPayload, json.loads(payload)),
        )
    except Exception:
        await requeue_claimed_json(
            payload=payload,
            processing_queue_name=ROLLUP_PROCESSING_QUEUE,
            queue_name=ROLLUP_QUEUE,
        )
        raise

    await acknowledge_claimed_json(
        payload=payload,
        processing_queue_name=ROLLUP_PROCESSING_QUEUE,
    )
    return 1


async def _drain_diagnoses() -> int:
    payload = await claim_json(
        queue_name=DIAGNOSIS_QUEUE,
        processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
    )
    if payload is None:
        return 0

    try:
        await process_diagnosis_job(
            job=cast(JobPayload, json.loads(payload)),
        )
    except Exception:
        await requeue_claimed_json(
            payload=payload,
            processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
            queue_name=DIAGNOSIS_QUEUE,
        )
        raise

    await acknowledge_claimed_json(
        payload=payload,
        processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
    )
    return 1


async def _restore_inflight_jobs() -> None:
    await restore_claimed_json(
        queue_name=ROLLUP_QUEUE,
        processing_queue_name=ROLLUP_PROCESSING_QUEUE,
    )
    await restore_claimed_json(
        queue_name=DIAGNOSIS_QUEUE,
        processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
    )
