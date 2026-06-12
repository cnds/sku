from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlmodel import select

from celery_app import (
    DIAGNOSIS_QUEUE,
    DIAGNOSIS_TASK_NAME,
    DUE_SHOP_ROLLUPS_TASK_NAME,
    ROLLUP_QUEUE,
    ROLLUP_TASK_NAME,
    celery_app,
)
from config import Settings
from db import create_session_factory, db_session_context, get_db_session, init_db
from models import DailyProductStat, DiagnosisStatus, EventType, ProductDiagnosis, RawEvent, ShopInstallation
from tasks import runtime as task_runtime
from tasks.diagnosis import DIAGNOSIS_MAX_RETRIES, _process_diagnosis_task
from tasks.handlers import mark_diagnosis_failed, process_diagnosis_job, process_rollup_job
from tasks.rollups import _process_rollup_task
from tasks.runtime import close_task_runtime, init_task_runtime
from tasks.scheduler import run_due_shop_rollups


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="replace-me",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
        shopify_webhook_base_url="https://example.com",
    )


def test_celery_app_routes_tasks_and_schedules_due_shop_rollups() -> None:
    assert ROLLUP_TASK_NAME in celery_app.tasks
    assert DIAGNOSIS_TASK_NAME in celery_app.tasks
    assert DUE_SHOP_ROLLUPS_TASK_NAME in celery_app.tasks
    assert celery_app.conf.task_routes[ROLLUP_TASK_NAME]["queue"] == ROLLUP_QUEUE
    assert celery_app.conf.task_routes[DIAGNOSIS_TASK_NAME]["queue"] == DIAGNOSIS_QUEUE
    assert celery_app.conf.task_routes[DUE_SHOP_ROLLUPS_TASK_NAME]["queue"] == ROLLUP_QUEUE
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True

    scheduled = celery_app.conf.beat_schedule["run-due-shop-rollups"]

    assert scheduled["task"] == DUE_SHOP_ROLLUPS_TASK_NAME
    assert scheduled["schedule"] == 60.0
    assert scheduled["options"]["queue"] == ROLLUP_QUEUE


@pytest.mark.asyncio
async def test_task_session_context_exposes_context_session_and_commits(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_task_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )
    task_session_context = getattr(task_runtime, "task_session_context", None)

    try:
        assert task_session_context is not None

        async with task_session_context():
            get_db_session().add(
                ProductDiagnosis(
                    product_id="product-1",
                    shop_id="shop-1",
                    snapshot_hash="hash-1",
                    status=DiagnosisStatus.PENDING,
                    window="7d",
                    report_markdown=None,
                    summary_json={},
                    generated_at=None,
                )
            )

        async with session_factory() as session:
            stored = (
                await session.exec(
                    select(ProductDiagnosis).where(
                        ProductDiagnosis.shop_id == "shop-1",
                        ProductDiagnosis.product_id == "product-1",
                        ProductDiagnosis.window == "7d",
                    )
                )
            ).one()
    finally:
        await close_task_runtime()

    assert stored.status is DiagnosisStatus.PENDING


@pytest.mark.asyncio
async def test_task_session_context_rolls_back_on_error(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_task_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )
    task_session_context = getattr(task_runtime, "task_session_context", None)

    try:
        assert task_session_context is not None

        with pytest.raises(RuntimeError, match="provider unavailable"):
            async with task_session_context():
                get_db_session().add(
                    ProductDiagnosis(
                        product_id="product-1",
                        shop_id="shop-1",
                        snapshot_hash="hash-1",
                        status=DiagnosisStatus.PENDING,
                        window="7d",
                        report_markdown=None,
                        summary_json={},
                        generated_at=None,
                    )
                )
                raise RuntimeError("provider unavailable")

        async with session_factory() as session:
            stored = (
                await session.exec(
                    select(ProductDiagnosis).where(
                        ProductDiagnosis.shop_id == "shop-1",
                        ProductDiagnosis.product_id == "product-1",
                        ProductDiagnosis.window == "7d",
                    )
                )
            ).first()
    finally:
        await close_task_runtime()

    assert stored is None


@pytest.mark.asyncio
async def test_task_handlers_process_diagnosis_jobs_with_initialized_runtime(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_task_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )

    try:
        await process_diagnosis_job(
            job={
                "job_id": "job-1",
                "product_id": "product-1",
                "shop_id": "shop-1",
                "snapshot": {
                    "views": 120,
                    "add_to_carts": 9,
                    "orders": 2,
                    "component_clicks_distribution": {"size_chart": 0},
                },
                "snapshot_hash": "hash-1",
                "window": "7d",
            },
        )

        async with session_factory() as session:
            stored = (
                await session.exec(
                    select(ProductDiagnosis).where(
                        ProductDiagnosis.shop_id == "shop-1",
                        ProductDiagnosis.product_id == "product-1",
                        ProductDiagnosis.window == "7d",
                    )
                )
            ).one()
    finally:
        await close_task_runtime()

    assert stored.status is DiagnosisStatus.READY
    assert stored.summary_json["source"] == "fallback"
    assert "## First fix to try" in (stored.report_markdown or "")


@pytest.mark.asyncio
async def test_task_handlers_process_rollup_jobs_with_initialized_runtime(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_task_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )

    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)
    async with db_session_context(session_factory) as session:
        session.add_all(
            [
                RawEvent(
                    channel="shopify_pixel",
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="shop-1",
                    visitor_id="visitor-1",
                ),
                RawEvent(
                    channel="sdk_dom",
                    component_id="size_chart",
                    event_type=EventType.COMPONENT_CLICK,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="shop-1",
                    visitor_id="visitor-1",
                ),
            ]
        )
        await session.commit()

    try:
        await process_rollup_job(
            job={
                "job_id": "job-1",
                "shop_id": "shop-1",
                "stat_date": "2026-04-23",
            }
        )

        async with session_factory() as session:
            daily_stat = (
                await session.exec(
                    select(DailyProductStat).where(
                        DailyProductStat.shop_id == "shop-1",
                        DailyProductStat.product_id == "product-1",
                    )
                )
            ).one()
    finally:
        await close_task_runtime()

    assert daily_stat.views == 1
    assert daily_stat.add_to_carts == 0
    assert daily_stat.orders == 0
    assert daily_stat.component_clicks_distribution == {"size_chart": 1}


def test_rollup_celery_task_logs_job_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen_jobs: list[dict[str, object]] = []

    async def _fake_process_rollup_job(*, job: dict[str, object]) -> None:
        seen_jobs.append(job)

    class FakeTask:
        max_retries = 3
        request = SimpleNamespace(retries=0)

        def retry(self, *, exc: Exception, countdown: int) -> None:
            del exc, countdown
            raise AssertionError("rollup task should not retry after success")

    monkeypatch.setattr("tasks.rollups.process_rollup_job", _fake_process_rollup_job, raising=False)
    monkeypatch.setattr("tasks.rollups.ensure_task_runtime", lambda: None, raising=False)
    caplog.set_level(logging.INFO)

    _process_rollup_task(
        FakeTask(),
        job_id="job-1",
        shop_id="shop-1",
        stat_date="2026-04-23",
    )

    assert seen_jobs == [{"job_id": "job-1", "shop_id": "shop-1", "stat_date": "2026-04-23"}]
    assert any("job claimed" in message and "job_id=job-1" in message for message in caplog.messages)
    assert any("job completed" in message and "job_id=job-1" in message for message in caplog.messages)


def test_diagnosis_celery_task_marks_failed_after_retry_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed_jobs: list[tuple[dict[str, object], str]] = []

    async def _fake_process_diagnosis_job(*, job: dict[str, object]) -> None:
        del job
        raise RuntimeError("provider unavailable")

    async def _fake_mark_diagnosis_failed(*, job: dict[str, object], error: Exception) -> None:
        failed_jobs.append((job, str(error)))

    class FakeTask:
        max_retries = DIAGNOSIS_MAX_RETRIES
        request = SimpleNamespace(retries=DIAGNOSIS_MAX_RETRIES)

        def retry(self, *, exc: Exception, countdown: int) -> None:
            del exc, countdown
            raise AssertionError("final diagnosis attempt should not retry")

    monkeypatch.setattr("tasks.diagnosis.process_diagnosis_job", _fake_process_diagnosis_job, raising=False)
    monkeypatch.setattr("tasks.diagnosis.mark_diagnosis_failed", _fake_mark_diagnosis_failed, raising=False)
    monkeypatch.setattr("tasks.diagnosis.ensure_task_runtime", lambda: None, raising=False)
    caplog.set_level(logging.INFO)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        _process_diagnosis_task(
            FakeTask(),
            job_id="job-1",
            product_id="product-1",
            shop_id="shop-1",
            snapshot={
                "views": 120,
                "add_to_carts": 9,
                "orders": 2,
                "component_clicks_distribution": {"size_chart": 0},
            },
            snapshot_hash="hash-1",
            window="7d",
        )

    assert failed_jobs == [
        (
            {
                "job_id": "job-1",
                "product_id": "product-1",
                "shop_id": "shop-1",
                "snapshot": {
                    "views": 120,
                    "add_to_carts": 9,
                    "orders": 2,
                    "component_clicks_distribution": {"size_chart": 0},
                },
                "snapshot_hash": "hash-1",
                "window": "7d",
            },
            "provider unavailable",
        )
    ]
    assert any("job failed" in message and "job_id=job-1" in message for message in caplog.messages)
    assert any("job failed permanently" in message and "job_id=job-1" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_mark_diagnosis_failed_persists_failed_state_with_error_summary(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_task_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )

    async with db_session_context(session_factory) as session:
        session.add(
            ProductDiagnosis(
                product_id="product-1",
                shop_id="shop-1",
                snapshot_hash="hash-1",
                status=DiagnosisStatus.PENDING,
                window="7d",
                report_markdown=None,
                summary_json={},
                generated_at=None,
            )
        )
        await session.commit()

    try:
        await mark_diagnosis_failed(
            job={
                "job_id": "job-1",
                "product_id": "product-1",
                "shop_id": "shop-1",
                "snapshot_hash": "hash-1",
                "window": "7d",
            },
            error=RuntimeError("provider unavailable because upstream returned 503"),
        )

        async with session_factory() as session:
            stored = (
                await session.exec(
                    select(ProductDiagnosis).where(
                        ProductDiagnosis.shop_id == "shop-1",
                        ProductDiagnosis.product_id == "product-1",
                        ProductDiagnosis.window == "7d",
                    )
                )
            ).one()
    finally:
        await close_task_runtime()

    assert stored.status is DiagnosisStatus.FAILED
    assert stored.report_markdown is None
    assert stored.generated_at is not None
    assert stored.summary_json == {
        "error": "provider unavailable because upstream returned 503",
        "job_id": "job-1",
        "source": "worker",
    }


@pytest.mark.asyncio
async def test_task_scheduler_runs_due_shop_rollups_when_shop_crosses_local_midnight(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_task_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="Asia/Tokyo",
                last_completed_local_date=datetime(2026, 4, 27, tzinfo=UTC).date(),
                next_rollup_at_utc=datetime(2026, 4, 28, 15, 0, tzinfo=UTC),
            )
        )
        session.add_all(
            [
                RawEvent(
                    channel="shopify_pixel",
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=datetime(2026, 4, 28, 14, 50, tzinfo=UTC),
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="demo.myshopify.com",
                    visitor_id="visitor-1",
                ),
                RawEvent(
                    channel="shopify_pixel",
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=datetime(2026, 4, 28, 15, 5, tzinfo=UTC),
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="demo.myshopify.com",
                    visitor_id="visitor-1",
                ),
            ]
        )
        await session.commit()

    try:
        processed = await run_due_shop_rollups(
            now_utc=datetime(2026, 4, 28, 15, 5, tzinfo=UTC),
        )

        async with session_factory() as session:
            installation = (
                await session.exec(select(ShopInstallation).where(ShopInstallation.shop_domain == "demo.myshopify.com"))
            ).one()
            daily_stats = (
                await session.exec(
                    select(DailyProductStat).where(
                        DailyProductStat.shop_id == "demo.myshopify.com",
                        DailyProductStat.product_id == "product-1",
                    )
                )
            ).all()
    finally:
        await close_task_runtime()

    assert processed == 1
    assert installation.last_completed_local_date.isoformat() == "2026-04-28"
    assert installation.next_rollup_at_utc.replace(tzinfo=UTC) == datetime(
        2026,
        4,
        29,
        15,
        0,
        tzinfo=UTC,
    )
    assert len(daily_stats) == 1
    assert daily_stats[0].stat_date.isoformat() == "2026-04-28"
    assert daily_stats[0].views == 1
