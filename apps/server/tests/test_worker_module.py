from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from config import Settings
from db import create_session_factory, db_session_context, init_db
from models import DailyProductStat, DiagnosisStatus, EventType, ProductDiagnosis, RawEvent, ShopInstallation
from worker import (
    DIAGNOSIS_PROCESSING_QUEUE,
    DIAGNOSIS_QUEUE,
    ROLLUP_PROCESSING_QUEUE,
    ROLLUP_QUEUE,
    _drain_rollups,
    _restore_inflight_jobs,
    _run_due_shop_rollups,
    close_worker_runtime,
    init_worker_runtime,
    process_diagnosis_job,
    process_rollup_job,
)


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        gemini_api_key="replace-me",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://example.com",
    )


@pytest.mark.asyncio
async def test_server_worker_processes_diagnosis_jobs_with_initialized_runtime(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_worker_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )

    try:
        await process_diagnosis_job(
            job={
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
        await close_worker_runtime()

    assert stored.status is DiagnosisStatus.READY
    assert stored.summary_json["source"] == "fallback"
    assert "Recommendation" in (stored.report_markdown or "")


@pytest.mark.asyncio
async def test_server_worker_processes_rollup_jobs_with_initialized_runtime(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_worker_runtime(
        settings=_settings(sqlite_database_url, redis_url),
        session_factory=session_factory,
    )

    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)
    async with db_session_context(session_factory) as session:
        session.add_all(
            [
                RawEvent(
                    channel="sdk",
                    event_type=EventType.VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="shop-1",
                    visitor_id="visitor-1",
                ),
                RawEvent(
                    channel="sdk",
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
        await close_worker_runtime()

    assert daily_stat.views == 1
    assert daily_stat.add_to_carts == 0
    assert daily_stat.orders == 0
    assert daily_stat.component_clicks_distribution == {"size_chart": 1}


@pytest.mark.asyncio
async def test_worker_requeues_rollup_job_when_processing_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = '{"job_id":"job-1","shop_id":"shop-1","stat_date":"2026-04-23"}'

    class FakeRedis:
        def __init__(self) -> None:
            self.queues = {
                ROLLUP_QUEUE: [payload],
                ROLLUP_PROCESSING_QUEUE: [],
            }

        async def rpop(self, queue_name: str) -> str | None:
            queue = self.queues[queue_name]
            return queue.pop() if queue else None

        async def rpoplpush(self, source: str, destination: str) -> str | None:
            queue = self.queues[source]
            if not queue:
                return None
            claimed = queue.pop()
            self.queues[destination].insert(0, claimed)
            return claimed

        async def lrem(self, queue_name: str, count: int, value: str) -> int:
            del count
            queue = self.queues[queue_name]
            removed = 0
            remaining: list[str] = []
            for item in queue:
                if removed == 0 and item == value:
                    removed += 1
                    continue
                remaining.append(item)
            self.queues[queue_name] = remaining
            return removed

        async def rpush(self, queue_name: str, value: str) -> int:
            self.queues[queue_name].append(value)
            return len(self.queues[queue_name])

    fake_redis = FakeRedis()

    async def _fake_process_rollup_job(*, job: dict[str, object]) -> None:
        del job
        raise RuntimeError("boom")

    caplog.set_level(logging.INFO)
    monkeypatch.setattr("job_queue.get_redis_client", lambda: fake_redis, raising=False)
    monkeypatch.setattr("worker.process_rollup_job", _fake_process_rollup_job, raising=False)

    with pytest.raises(RuntimeError, match="boom"):
        await _drain_rollups()

    assert fake_redis.queues[ROLLUP_QUEUE] == [payload]
    assert fake_redis.queues[ROLLUP_PROCESSING_QUEUE] == []
    assert any(
        "job requeued" in message and "job_id=job-1" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_worker_logs_rollup_job_completion(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = '{"job_id":"job-1","shop_id":"shop-1","stat_date":"2026-04-23"}'
    acknowledged: list[str] = []

    async def _fake_claim_json(*, queue_name: str, processing_queue_name: str) -> str | None:
        del queue_name, processing_queue_name
        return payload

    async def _fake_process_rollup_job(*, job: dict[str, object]) -> None:
        assert job["job_id"] == "job-1"

    async def _fake_acknowledge_claimed_json(*, payload: str, processing_queue_name: str) -> None:
        del processing_queue_name
        acknowledged.append(payload)

    caplog.set_level(logging.INFO)
    monkeypatch.setattr("worker.claim_json", _fake_claim_json, raising=False)
    monkeypatch.setattr("worker.process_rollup_job", _fake_process_rollup_job, raising=False)
    monkeypatch.setattr("worker.acknowledge_claimed_json", _fake_acknowledge_claimed_json, raising=False)

    processed = await _drain_rollups()

    assert processed == 1
    assert acknowledged == [payload]
    assert any(
        "job claimed" in message and "job_id=job-1" in message
        for message in caplog.messages
    )
    assert any(
        "job completed" in message and "job_id=job-1" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_worker_restores_claimed_jobs_from_processing_queues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rollup_payload = '{"shop_id":"shop-1","stat_date":"2026-04-23"}'
    diagnosis_payload = (
        '{"product_id":"product-1","shop_id":"shop-1","snapshot":{},'
        '"snapshot_hash":"hash-1","window":"7d"}'
    )

    class FakeRedis:
        def __init__(self) -> None:
            self.queues = {
                ROLLUP_QUEUE: [],
                ROLLUP_PROCESSING_QUEUE: [rollup_payload],
                DIAGNOSIS_QUEUE: [],
                DIAGNOSIS_PROCESSING_QUEUE: [diagnosis_payload],
            }

        async def rpoplpush(self, source: str, destination: str) -> str | None:
            queue = self.queues[source]
            if not queue:
                return None
            claimed = queue.pop()
            self.queues[destination].insert(0, claimed)
            return claimed

    fake_redis = FakeRedis()
    monkeypatch.setattr("job_queue.get_redis_client", lambda: fake_redis, raising=False)

    await _restore_inflight_jobs()

    assert fake_redis.queues[ROLLUP_QUEUE] == [rollup_payload]
    assert fake_redis.queues[ROLLUP_PROCESSING_QUEUE] == []
    assert fake_redis.queues[DIAGNOSIS_QUEUE] == [diagnosis_payload]
    assert fake_redis.queues[DIAGNOSIS_PROCESSING_QUEUE] == []


@pytest.mark.asyncio
async def test_worker_runs_due_shop_rollups_when_shop_crosses_local_midnight(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    init_worker_runtime(
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
                    channel="sdk",
                    event_type=EventType.VIEW,
                    occurred_at=datetime(2026, 4, 28, 14, 50, tzinfo=UTC),
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="demo.myshopify.com",
                    visitor_id="visitor-1",
                ),
                RawEvent(
                    channel="sdk",
                    event_type=EventType.VIEW,
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
        processed = await _run_due_shop_rollups(
            now_utc=datetime(2026, 4, 28, 15, 5, tzinfo=UTC),
        )

        async with session_factory() as session:
            installation = (
                await session.exec(
                    select(ShopInstallation).where(
                        ShopInstallation.shop_domain == "demo.myshopify.com"
                    )
                )
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
        await close_worker_runtime()

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
