from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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
from logging_utils import configure_logging
from repositories.installations import InstallationRepository
from schemas import ProductSnapshot, TimeWindow
from services.diagnosis import ProductDiagnosisService
from services.gemini import GeminiDiagnosisService
from services.rollups import DailyRollupService
from services.shop_time import (
    ensure_utc_datetime,
    initial_last_completed_local_date,
    local_date_for_shop,
    normalize_shop_timezone,
    rollup_due_at_utc,
)

ROLLUP_QUEUE = "sku-lens:rollups"
ROLLUP_PROCESSING_QUEUE = "sku-lens:rollups:processing"
DIAGNOSIS_QUEUE = "sku-lens:diagnoses"
DIAGNOSIS_PROCESSING_QUEUE = "sku-lens:diagnoses:processing"
LOGGER = logging.getLogger(__name__)

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
    configure_logging(settings.sku_lens_log_level)
    runtime = init_worker_runtime(settings=settings)
    await init_db(runtime.session_factory.engine)
    init_redis_client(settings.redis_url)

    try:
        await _restore_inflight_jobs()
        while True:
            processed = 0
            processed += await _run_due_shop_rollups()
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
            installation = await InstallationRepository().get_by_shop_domain(str(job["shop_id"]))
            await DailyRollupService().rollup_day(
                shop_id=str(job["shop_id"]),
                stat_date=date.fromisoformat(str(job["stat_date"])),
                timezone_name=installation.timezone_name if installation is not None else None,
            )
            await session.commit()
            LOGGER.info(
                "rollup processed shop_id=%s stat_date=%s",
                str(job["shop_id"]),
                date.fromisoformat(str(job["stat_date"])),
            )
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
            LOGGER.info(
                "diagnosis generated product_id=%s shop_id=%s window=%s",
                str(job["product_id"]),
                str(job["shop_id"]),
                str(job["window"]),
            )
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

    job = cast(JobPayload, json.loads(payload))
    job_id = str(job.get("job_id", ""))

    LOGGER.info(
        "job claimed job_id=%s queue_name=%s shop_id=%s stat_date=%s",
        job_id,
        ROLLUP_QUEUE,
        str(job["shop_id"]),
        str(job["stat_date"]),
    )
    try:
        await process_rollup_job(job=job)
    except Exception as exc:
        LOGGER.exception(
            "job failed job_id=%s queue_name=%s shop_id=%s stat_date=%s error=%s",
            job_id,
            ROLLUP_QUEUE,
            str(job["shop_id"]),
            str(job["stat_date"]),
            exc,
        )
        await requeue_claimed_json(
            payload=payload,
            processing_queue_name=ROLLUP_PROCESSING_QUEUE,
            queue_name=ROLLUP_QUEUE,
        )
        LOGGER.warning(
            "job requeued job_id=%s queue_name=%s shop_id=%s stat_date=%s error=%s",
            job_id,
            ROLLUP_QUEUE,
            str(job["shop_id"]),
            str(job["stat_date"]),
            exc,
        )
        raise

    await acknowledge_claimed_json(
        payload=payload,
        processing_queue_name=ROLLUP_PROCESSING_QUEUE,
    )
    LOGGER.info(
        "job completed job_id=%s queue_name=%s shop_id=%s stat_date=%s",
        job_id,
        ROLLUP_QUEUE,
        str(job["shop_id"]),
        str(job["stat_date"]),
    )
    return 1


async def _drain_diagnoses() -> int:
    payload = await claim_json(
        queue_name=DIAGNOSIS_QUEUE,
        processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
    )
    if payload is None:
        return 0

    job = cast(JobPayload, json.loads(payload))
    job_id = str(job.get("job_id", ""))

    LOGGER.info(
        "job claimed job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s",
        job_id,
        str(job["product_id"]),
        DIAGNOSIS_QUEUE,
        str(job["shop_id"]),
        str(job["window"]),
    )
    try:
        await process_diagnosis_job(job=job)
    except Exception as exc:
        LOGGER.exception(
            "job failed job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s error=%s",
            job_id,
            str(job["product_id"]),
            DIAGNOSIS_QUEUE,
            str(job["shop_id"]),
            str(job["window"]),
            exc,
        )
        await requeue_claimed_json(
            payload=payload,
            processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
            queue_name=DIAGNOSIS_QUEUE,
        )
        LOGGER.warning(
            "job requeued job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s error=%s",
            job_id,
            str(job["product_id"]),
            DIAGNOSIS_QUEUE,
            str(job["shop_id"]),
            str(job["window"]),
            exc,
        )
        raise

    await acknowledge_claimed_json(
        payload=payload,
        processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
    )
    LOGGER.info(
        "job completed job_id=%s product_id=%s queue_name=%s shop_id=%s window=%s",
        job_id,
        str(job["product_id"]),
        DIAGNOSIS_QUEUE,
        str(job["shop_id"]),
        str(job["window"]),
    )
    return 1


async def _restore_inflight_jobs() -> None:
    restored_rollups = await restore_claimed_json(
        queue_name=ROLLUP_QUEUE,
        processing_queue_name=ROLLUP_PROCESSING_QUEUE,
    )
    if restored_rollups:
        LOGGER.warning(
            "jobs restored queue_name=%s restored=%s",
            ROLLUP_QUEUE,
            restored_rollups,
        )

    restored_diagnoses = await restore_claimed_json(
        queue_name=DIAGNOSIS_QUEUE,
        processing_queue_name=DIAGNOSIS_PROCESSING_QUEUE,
    )
    if restored_diagnoses:
        LOGGER.warning(
            "jobs restored queue_name=%s restored=%s",
            DIAGNOSIS_QUEUE,
            restored_diagnoses,
        )


async def _run_due_shop_rollups(now_utc: datetime | None = None) -> int:
    runtime = get_worker_runtime()
    reference = ensure_utc_datetime(now_utc or datetime.now(UTC))

    async with db_session_context(runtime.session_factory):
        due_installations = await InstallationRepository().list_due_for_rollup(now_utc=reference)

    processed = 0
    for installation in due_installations:
        processed += await _process_due_shop_rollups(
            now_utc=reference,
            shop_domain=installation.shop_domain,
        )
    return processed


async def _process_due_shop_rollups(*, now_utc: datetime, shop_domain: str) -> int:
    runtime = get_worker_runtime()

    async with db_session_context(runtime.session_factory) as session:
        installation = await InstallationRepository().get_by_shop_domain(shop_domain)
        if installation is None:
            return 0

        timezone_name = normalize_shop_timezone(installation.timezone_name)
        if installation.last_completed_local_date is None:
            installation.last_completed_local_date = initial_last_completed_local_date(
                installed_at=installation.installed_at,
                timezone_name=timezone_name,
            )

        local_today = local_date_for_shop(
            instant=now_utc,
            timezone_name=timezone_name,
        )
        processed = 0
        next_local_date = installation.last_completed_local_date + timedelta(days=1)

        while next_local_date < local_today:
            await DailyRollupService().rollup_day(
                shop_id=installation.shop_domain,
                stat_date=next_local_date,
                timezone_name=timezone_name,
            )
            installation.last_completed_local_date = next_local_date
            processed += 1
            next_local_date = installation.last_completed_local_date + timedelta(days=1)

        installation.next_rollup_at_utc = rollup_due_at_utc(
            local_date=installation.last_completed_local_date + timedelta(days=1),
            timezone_name=timezone_name,
        )
        await session.commit()
        if processed:
            LOGGER.info(
                "rollup backfill completed shop_domain=%s processed=%s",
                shop_domain,
                processed,
            )
        return processed
