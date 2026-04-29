from __future__ import annotations

import time
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from config import Settings
from db import create_session_factory, db_session_context, init_db
from main import create_app
from models import DailyProductStat, EventType, RawEvent, ShopInstallation
from schemas import IngestEvent
from services.ingestion import EventIngestionService
from services.job_dispatch import AfterCommitCallbacks
from services.rollups import DailyRollupService


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        gemini_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://example.com",
    )


@pytest.mark.asyncio
async def test_ingestion_service_persists_raw_events_and_rolls_up_daily_stats(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    ingestion_service = EventIngestionService()
    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)

    async with db_session_context(session_factory) as session:
        await ingestion_service.persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="sdk",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
                IngestEvent(
                    event_type=EventType.COMPONENT_CLICK,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="size_chart",
                ),
                IngestEvent(
                    event_type=EventType.ADD_TO_CART,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
                IngestEvent(
                    event_type=EventType.ORDER,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        raw_events = (await session.exec(select(RawEvent).order_by(RawEvent.occurred_at))).all()
        daily_stat = (await session.exec(select(DailyProductStat))).one()

    assert len(raw_events) == 4
    assert raw_events[0].channel == "sdk"
    assert daily_stat.shop_id == "shop-1"
    assert daily_stat.product_id == "product-1"
    assert daily_stat.views == 1
    assert daily_stat.add_to_carts == 1
    assert daily_stat.orders == 1
    assert daily_stat.component_clicks_distribution == {"size_chart": 1}


@pytest.mark.asyncio
async def test_ingestion_service_persists_rollup_and_registers_enqueue_callback(
    sqlite_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    callbacks = AfterCommitCallbacks()
    enqueued: list[tuple[str, dict[str, object]]] = []
    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

    async with db_session_context(session_factory) as session:
        await EventIngestionService().persist_batch_rollup_and_enqueue(
            after_commit_callbacks=callbacks,
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="sdk",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
            ],
        )
        await session.commit()

    assert enqueued == []

    await callbacks.run()

    assert len(enqueued) == 1
    queue_name, enqueued_payload = enqueued[0]
    assert queue_name == "sku-lens:rollups"
    assert enqueued_payload["shop_id"] == "shop-1"
    assert enqueued_payload["stat_date"] == "2026-04-23"
    assert isinstance(enqueued_payload["job_id"], str)


@pytest.mark.asyncio
async def test_ingest_events_persists_rollup_and_enqueues_job_after_commit(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    await init_db(app.state.session_factory.engine)

    async with db_session_context(app.state.session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="Asia/Tokyo",
            )
        )
        await session.commit()

    enqueued: list[tuple[str, dict[str, object]]] = []
    enqueue_visibility_checks: list[tuple[int, int, dict[str, int]]] = []

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        async with app.state.session_factory() as session:
            raw_events = (
                await session.exec(
                    select(RawEvent)
                    .where(RawEvent.shop_id == "demo.myshopify.com")
                    .order_by(RawEvent.id)
                )
            ).all()
            daily_stats = (
                await session.exec(
                    select(DailyProductStat).where(
                        DailyProductStat.shop_id == "demo.myshopify.com"
                    )
                )
            ).all()

        assert len(raw_events) == 2
        assert [raw_event.event_type for raw_event in raw_events] == [
            EventType.VIEW,
            EventType.COMPONENT_CLICK,
        ]
        assert len(daily_stats) == 1
        assert daily_stats[0].views == 1
        assert daily_stats[0].component_clicks_distribution == {"size_chart": 1}
        assert payload["shop_id"] == "demo.myshopify.com"
        assert payload["stat_date"] == daily_stats[0].stat_date.isoformat()
        assert isinstance(payload["job_id"], str)

        enqueue_visibility_checks.append(
            (
                len(raw_events),
                daily_stats[0].views,
                daily_stats[0].component_clicks_distribution,
            )
        )
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

    occurred_at = datetime(2026, 4, 28, 15, 5, tzinfo=UTC)
    payload = {
        "shop_domain": "demo.myshopify.com",
        "visitor_id": "visitor-1",
        "session_id": "session-1",
        "events": [
            {
                "event_type": "view",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
            },
            {
                "event_type": "component_click",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "component_id": "size_chart",
            },
        ],
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/ingest/events",
            json=payload,
            headers={
                "X-SKU-Lens-Public-Token": "public-1",
                "X-SKU-Lens-Timestamp": str(int(time.time())),
            },
        )

    assert response.status_code == 202
    assert response.json() == {"accepted": 2}
    assert enqueue_visibility_checks == [(2, 1, {"size_chart": 1})]
    assert len(enqueued) == 1
    queue_name, enqueued_payload = enqueued[0]
    assert queue_name == "sku-lens:rollups"
    assert enqueued_payload["shop_id"] == "demo.myshopify.com"
    assert enqueued_payload["stat_date"] == "2026-04-29"
    assert isinstance(enqueued_payload["job_id"], str)

    async with app.state.session_factory() as session:
        raw_events = (
            await session.exec(
                select(RawEvent)
                .where(RawEvent.shop_id == "demo.myshopify.com")
                .order_by(RawEvent.id)
            )
        ).all()
        daily_stats = (
            await session.exec(
                select(DailyProductStat).where(
                    DailyProductStat.shop_id == "demo.myshopify.com"
                )
            )
        ).all()

    assert len(raw_events) == 2
    assert raw_events[0].channel == "sdk"
    assert raw_events[0].shop_domain == "demo.myshopify.com"
    assert raw_events[0].session_id == "session-1"
    assert raw_events[1].component_id == "size_chart"
    assert len(daily_stats) == 1
    assert daily_stats[0].product_id == "product-1"
    assert daily_stats[0].stat_date.isoformat() == "2026-04-29"
    assert daily_stats[0].views == 1
    assert daily_stats[0].add_to_carts == 0
    assert daily_stats[0].orders == 0
    assert daily_stats[0].component_clicks_distribution == {"size_chart": 1}


@pytest.mark.asyncio
async def test_daily_rollup_service_uses_shop_timezone_day_boundaries(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with db_session_context(session_factory) as session:
        session.add_all(
            [
                RawEvent(
                    channel="sdk",
                    event_type=EventType.VIEW,
                    occurred_at=datetime(2026, 4, 28, 14, 59, tzinfo=UTC),
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="shop-1",
                    visitor_id="visitor-1",
                ),
                RawEvent(
                    channel="sdk",
                    event_type=EventType.VIEW,
                    occurred_at=datetime(2026, 4, 28, 15, 1, tzinfo=UTC),
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="shop-1",
                    visitor_id="visitor-1",
                ),
            ]
        )

        await DailyRollupService().rollup_day(
            shop_id="shop-1",
            stat_date=date(2026, 4, 29),
            timezone_name="Asia/Tokyo",
        )
        await session.commit()

    async with session_factory() as session:
        daily_stats = (
            await session.exec(
                select(DailyProductStat).where(
                    DailyProductStat.shop_id == "shop-1",
                    DailyProductStat.product_id == "product-1",
                )
            )
        ).all()

    assert len(daily_stats) == 1
    assert daily_stats[0].stat_date.isoformat() == "2026-04-29"
    assert daily_stats[0].views == 1


@pytest.mark.asyncio
async def test_ingestion_service_persists_new_sdk_events_and_rolls_up(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)

    async with db_session_context(session_factory) as session:
        await EventIngestionService().persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="sdk",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.IMPRESSION,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="featured-collection",
                    context={"position": 0},
                ),
                IngestEvent(
                    event_type=EventType.IMPRESSION,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="featured-collection",
                    context={"position": 0},
                ),
                IngestEvent(
                    event_type=EventType.CLICK,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="featured-collection",
                    context={"position": 0, "target_url": "/products/widget"},
                ),
                IngestEvent(
                    event_type=EventType.MEDIA,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    context={"action": "zoom", "media_index": 0},
                ),
                IngestEvent(
                    event_type=EventType.VARIANT,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    variant_id="variant-42",
                    context={"options": {"Size": "M", "Color": "Blue"}},
                ),
                IngestEvent(
                    event_type=EventType.ENGAGE,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    context={"dwell_ms": 15000, "max_scroll_pct": 75, "page_type": "pdp"},
                ),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        raw_events = (await session.exec(select(RawEvent).order_by(RawEvent.id))).all()
        daily_stat = (await session.exec(select(DailyProductStat))).one()

    assert len(raw_events) == 6
    assert daily_stat.impressions == 2
    assert daily_stat.clicks == 1
    assert daily_stat.media_interactions == 1
    assert daily_stat.variant_changes == 1
    assert daily_stat.engage_count == 1
    assert daily_stat.total_dwell_ms == 15000
    assert daily_stat.avg_scroll_pct == 75
    assert daily_stat.component_impressions_distribution == {"featured-collection": 2}
    assert daily_stat.component_clicks_distribution == {"featured-collection": 1}
    assert daily_stat.views == 0
    assert daily_stat.add_to_carts == 0
    assert daily_stat.orders == 0


@pytest.mark.asyncio
async def test_engage_event_without_product_id_persists_but_excluded_from_rollup(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with db_session_context(session_factory) as session:
        await EventIngestionService().persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="sdk",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.ENGAGE,
                    occurred_at=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
                    product_id=None,
                    context={"dwell_ms": 5000, "max_scroll_pct": 40, "page_type": "home"},
                ),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        raw_events = (await session.exec(select(RawEvent))).all()
        daily_stats = (await session.exec(select(DailyProductStat))).all()

    assert len(raw_events) == 1
    assert raw_events[0].product_id is None
    assert len(daily_stats) == 0


@pytest.mark.asyncio
async def test_ingest_new_sdk_events_via_http_endpoint(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    await init_db(app.state.session_factory.engine)

    async with db_session_context(app.state.session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
            )
        )
        await session.commit()

    async def _fake_enqueue_json(
        *, payload: dict[str, object], queue_name: str
    ) -> bool:
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

    occurred_at = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "shop_domain": "demo.myshopify.com",
        "visitor_id": "visitor-1",
        "session_id": "session-1",
        "events": [
            {
                "event_type": "impression",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "component_id": "featured-collection",
                "context": {"position": 2},
            },
            {
                "event_type": "click",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "component_id": "featured-collection",
                "context": {"position": 2, "target_url": "/products/widget"},
            },
            {
                "event_type": "engage",
                "occurred_at": occurred_at.isoformat(),
                "context": {"dwell_ms": 8000, "max_scroll_pct": 60, "page_type": "collection"},
            },
        ],
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/ingest/events",
            json=payload,
            headers={
                "X-SKU-Lens-Public-Token": "public-1",
                "X-SKU-Lens-Timestamp": str(int(time.time())),
            },
        )

    assert response.status_code == 202
    assert response.json() == {"accepted": 3}

    async with app.state.session_factory() as session:
        raw_events = (
            await session.exec(
                select(RawEvent)
                .where(RawEvent.shop_id == "demo.myshopify.com")
                .order_by(RawEvent.id)
            )
        ).all()

    assert len(raw_events) == 3
    assert raw_events[0].event_type == EventType.IMPRESSION
    assert raw_events[1].event_type == EventType.CLICK
    assert raw_events[2].event_type == EventType.ENGAGE
    assert raw_events[2].product_id is None
