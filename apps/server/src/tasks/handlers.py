from __future__ import annotations

import logging
from datetime import date
from typing import cast

from repositories.installations import InstallationRepository
from schemas import ProductSnapshot, TimeWindow
from services.ai import AIDiagnosisService
from services.diagnosis import ProductDiagnosisService
from services.rollups import DailyRollupService
from tasks.runtime import JobPayload, get_task_runtime, task_session_context

LOGGER = logging.getLogger(__name__)


async def process_rollup_job(
    *,
    job: JobPayload,
) -> None:
    stat_date = date.fromisoformat(str(job["stat_date"]))

    async with task_session_context():
        installation = await InstallationRepository().get_by_shop_domain(str(job["shop_id"]))
        await DailyRollupService().rollup_day(
            shop_id=str(job["shop_id"]),
            stat_date=stat_date,
            timezone_name=installation.timezone_name if installation is not None else None,
        )
        LOGGER.info(
            "rollup processed shop_id=%s stat_date=%s",
            str(job["shop_id"]),
            stat_date,
        )


async def process_diagnosis_job(
    *,
    job: JobPayload,
) -> None:
    snapshot_payload = cast(dict[str, object], job["snapshot"])
    snapshot = ProductSnapshot.model_validate(snapshot_payload)
    runtime = get_task_runtime()
    report_markdown, summary = await AIDiagnosisService(runtime.settings).generate_report(snapshot=snapshot)

    async with task_session_context():
        await ProductDiagnosisService().store_generated_report(
            product_id=str(job["product_id"]),
            report_markdown=report_markdown,
            shop_id=str(job["shop_id"]),
            snapshot_hash=str(job["snapshot_hash"]),
            summary_json=summary,
            window=TimeWindow(str(job["window"])),
        )
        LOGGER.info(
            "diagnosis generated product_id=%s shop_id=%s window=%s",
            str(job["product_id"]),
            str(job["shop_id"]),
            str(job["window"]),
        )


async def mark_diagnosis_failed(
    *,
    error: Exception,
    job: JobPayload,
) -> None:
    summary_json = {
        "error": _summarize_error(error),
        "job_id": str(job.get("job_id", "")),
        "source": "worker",
    }

    async with task_session_context():
        await ProductDiagnosisService().store_failed_report(
            product_id=str(job["product_id"]),
            shop_id=str(job["shop_id"]),
            snapshot_hash=str(job["snapshot_hash"]),
            summary_json=summary_json,
            window=TimeWindow(str(job["window"])),
        )


def _summarize_error(error: Exception) -> str:
    message = str(error).strip() or error.__class__.__name__
    return message[:240]
