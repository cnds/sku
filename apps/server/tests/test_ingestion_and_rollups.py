from __future__ import annotations

import time
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

import services.job_dispatch as job_dispatch_module
from config import Settings
from db import create_session_factory, db_session_context, init_db
from main import create_app
from models import DailyProductStat, EventType, RawEvent, ShopInstallation
from schemas import IngestEvent
from security.shopify import build_shopify_hmac
from services.ingestion import EventIngestionService
from services.job_dispatch import AfterCommitCallbacks
from services.rollups import DailyRollupService


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
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
            channel="shopify_pixel",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
                IngestEvent(
                    event_type=EventType.ADD_TO_CART,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
            ],
        )
        await ingestion_service.persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="shopify_webhook",
            session_id="order-order-1",
            stat_date=date(2026, 4, 23),
            visitor_id="shopify-order-order-1",
            events=[
                IngestEvent(
                    event_type=EventType.ORDER_COMPLETED,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        raw_events = (await session.exec(select(RawEvent).order_by(RawEvent.occurred_at))).all()
        daily_stat = (await session.exec(select(DailyProductStat))).one()

    assert len(raw_events) == 3
    assert {event.channel for event in raw_events} == {"shopify_pixel", "shopify_webhook"}
    assert daily_stat.shop_id == "shop-1"
    assert daily_stat.product_id == "product-1"
    assert daily_stat.views == 1
    assert daily_stat.add_to_carts == 1
    assert daily_stat.orders == 1
    assert daily_stat.component_clicks_distribution == {}


@pytest.mark.asyncio
async def test_ingestion_service_persists_rollup_and_registers_enqueue_callback(
    sqlite_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    callbacks = AfterCommitCallbacks()
    sent: list[dict[str, object]] = []
    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    async with db_session_context(session_factory) as session:
        await EventIngestionService().persist_batch_rollup_and_enqueue(
            after_commit_callbacks=callbacks,
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="shopify_pixel",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                ),
            ],
        )
        await session.commit()

    assert sent == []

    await callbacks.run()

    assert len(sent) == 1
    message = sent[0]
    enqueued_payload = message["kwargs"]
    assert message["name"] == "sku_lens.rollup.process"
    assert message["queue"] == "sku-lens:rollups"
    assert enqueued_payload["shop_id"] == "shop-1"
    assert enqueued_payload["stat_date"] == "2026-04-23"
    assert isinstance(enqueued_payload["job_id"], str)
    assert message["task_id"] == enqueued_payload["job_id"]


@pytest.mark.asyncio
async def test_ingest_events_persists_sdk_dom_rollup_and_enqueues_job_after_commit(
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

    sent: list[dict[str, object]] = []

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    async def _old_fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        del payload, queue_name
        raise AssertionError("legacy Redis enqueue_json should not be called")

    monkeypatch.setattr(job_dispatch_module, "enqueue_json", _old_fake_enqueue_json, raising=False)

    occurred_at = datetime(2026, 4, 28, 15, 5, tzinfo=UTC)
    payload = {
        "shop_domain": "demo.myshopify.com",
        "visitor_id": "visitor-1",
        "session_id": "session-1",
        "events": [
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
    assert response.json() == {"accepted": 1}
    assert len(sent) == 1
    message = sent[0]
    enqueued_payload = message["kwargs"]
    assert message["name"] == "sku_lens.rollup.process"
    assert message["queue"] == "sku-lens:rollups"
    assert enqueued_payload["shop_id"] == "demo.myshopify.com"
    assert enqueued_payload["stat_date"] == "2026-04-29"
    assert isinstance(enqueued_payload["job_id"], str)
    assert message["task_id"] == enqueued_payload["job_id"]

    async with app.state.session_factory() as session:
        raw_events = (
            await session.exec(select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com").order_by(RawEvent.id))
        ).all()
        daily_stats = (
            await session.exec(select(DailyProductStat).where(DailyProductStat.shop_id == "demo.myshopify.com"))
        ).all()

    assert len(raw_events) == 1
    assert raw_events[0].channel == "sdk_dom"
    assert raw_events[0].shop_domain == "demo.myshopify.com"
    assert raw_events[0].session_id == "session-1"
    assert raw_events[0].component_id == "size_chart"
    assert len(daily_stats) == 1
    assert daily_stats[0].product_id == "product-1"
    assert daily_stats[0].stat_date.isoformat() == "2026-04-29"
    assert daily_stats[0].views == 0
    assert daily_stats[0].add_to_carts == 0
    assert daily_stats[0].orders == 0
    assert daily_stats[0].component_clicks_distribution == {"size_chart": 1}


@pytest.mark.asyncio
async def test_ingest_pixel_events_maps_standard_events_and_dedupes(
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
                timezone_name="UTC",
            )
        )
        await session.commit()

    sent: list[dict[str, object]] = []

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    occurred_at = datetime(2026, 4, 28, 15, 5, tzinfo=UTC)
    payload = {
        "shop_domain": "demo.myshopify.com",
        "visitor_id": "visitor-1",
        "session_id": "session-1",
        "events": [
            {
                "event_id": "evt-product-view",
                "source_event_name": "product_viewed",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "variant_id": "variant-1",
            },
            {
                "event_id": "evt-product-view",
                "source_event_name": "product_viewed",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "variant_id": "variant-1",
            },
            {
                "event_id": "evt-add-cart",
                "source_event_name": "product_added_to_cart",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "variant_id": "variant-1",
            },
            {
                "context": {"line_item_index": 0, "order_id": "order-1", "quantity": 1},
                "event_id": "evt-checkout-completed",
                "source_event_name": "checkout_completed",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "variant_id": "variant-1",
            },
        ],
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/ingest/pixel-events",
            json=payload,
            headers={
                "X-SKU-Lens-Public-Token": "public-1",
                "X-SKU-Lens-Timestamp": str(int(time.time())),
            },
        )
        second = await client.post(
            "/ingest/pixel-events",
            json=payload,
            headers={
                "X-SKU-Lens-Public-Token": "public-1",
                "X-SKU-Lens-Timestamp": str(int(time.time())),
            },
        )

    assert first.status_code == 202
    assert first.json() == {"accepted": 3}
    assert second.status_code == 202
    assert second.json() == {"accepted": 0}
    assert len(sent) == 1

    async with app.state.session_factory() as session:
        raw_events = (
            await session.exec(select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com").order_by(RawEvent.id))
        ).all()
        daily_stat = (await session.exec(select(DailyProductStat))).one()

    assert [event.event_type for event in raw_events] == [
        EventType.PRODUCT_VIEW,
        EventType.ADD_TO_CART,
        EventType.CHECKOUT_COMPLETED,
    ]
    assert {event.channel for event in raw_events} == {"shopify_pixel"}
    assert raw_events[0].event_id == "evt-product-view"
    assert raw_events[0].source_event_name == "product_viewed"
    assert daily_stat.views == 1
    assert daily_stat.add_to_carts == 1
    assert daily_stat.orders == 0


@pytest.mark.asyncio
async def test_shopify_order_webhook_persists_order_facts_and_dedupes(
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
                timezone_name="UTC",
            )
        )
        await session.commit()

    sent: list[dict[str, object]] = []

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    body = (
        b'{"id":9001,"name":"#1001","created_at":"2026-04-28T15:05:00Z",'
        b'"line_items":[{"id":7001,"product_id":1001,"variant_id":2001,"quantity":2}]}'
    )
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Hmac-Sha256": build_shopify_hmac(settings.shopify_api_secret, body),
        "X-Shopify-Shop-Domain": "demo.myshopify.com",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/shopify/webhooks/orders/create",
            content=body,
            headers=headers,
        )
        second = await client.post(
            "/shopify/webhooks/orders/create",
            content=body,
            headers=headers,
        )

    assert first.status_code == 202
    assert first.json() == {"accepted": True, "enqueued": 1}
    assert second.status_code == 202
    assert second.json() == {"accepted": True, "enqueued": 0}
    assert len(sent) == 1

    async with app.state.session_factory() as session:
        raw_events = (await session.exec(select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com"))).all()
        daily_stat = (await session.exec(select(DailyProductStat))).one()

    assert len(raw_events) == 1
    assert raw_events[0].channel == "shopify_webhook"
    assert raw_events[0].event_type == EventType.ORDER_COMPLETED
    assert raw_events[0].event_id == "9001"
    assert raw_events[0].source_event_name == "orders/create"
    assert raw_events[0].dedupe_key == "orders/create|9001|1001|2001|7001"
    assert raw_events[0].context_json["quantity"] == 2
    assert daily_stat.orders == 1


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
                    channel="shopify_pixel",
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=datetime(2026, 4, 28, 14, 59, tzinfo=UTC),
                    product_id="product-1",
                    session_id="session-1",
                    shop_domain="demo.myshopify.com",
                    shop_id="shop-1",
                    visitor_id="visitor-1",
                ),
                RawEvent(
                    channel="shopify_pixel",
                    event_type=EventType.PRODUCT_VIEW,
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
            channel="sdk_dom",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.PRODUCT_IMPRESSION,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="featured-collection",
                    context={"position": 0},
                ),
                IngestEvent(
                    event_type=EventType.PRODUCT_IMPRESSION,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="featured-collection",
                    context={"position": 0},
                ),
                IngestEvent(
                    event_type=EventType.PRODUCT_CLICK,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="featured-collection",
                    context={"position": 0, "target_url": "/products/widget"},
                ),
                IngestEvent(
                    event_type=EventType.MEDIA_INTERACTION,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    context={"action": "zoom", "media_index": 0},
                ),
                IngestEvent(
                    event_type=EventType.VARIANT_INTENT,
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
    assert daily_stat.component_impressions_distribution == {}
    assert daily_stat.component_clicks_distribution == {}
    assert daily_stat.views == 0
    assert daily_stat.add_to_carts == 0
    assert daily_stat.orders == 0


@pytest.mark.asyncio
async def test_daily_rollup_counts_pixel_funnel_and_sdk_component_events(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    occurred_at = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)

    async with db_session_context(session_factory) as session:
        await EventIngestionService().persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="shopify_pixel",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.PRODUCT_VIEW,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    context={"page_type": "pdp"},
                ),
                IngestEvent(
                    event_type=EventType.ADD_TO_CART,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    variant_id="variant-1",
                    context={"source": "product_form"},
                ),
            ],
        )
        await EventIngestionService().persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="sdk_dom",
            session_id="session-1",
            stat_date=date(2026, 4, 23),
            visitor_id="visitor-1",
            events=[
                IngestEvent(
                    event_type=EventType.COMPONENT_IMPRESSION,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="product_media",
                    context={"page_type": "pdp"},
                ),
                IngestEvent(
                    event_type=EventType.COMPONENT_CLICK,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    component_id="buy_box",
                    context={"action": "intent"},
                ),
            ],
        )
        await EventIngestionService().persist_batch_and_rollup(
            shop_id="shop-1",
            shop_domain="demo.myshopify.com",
            channel="shopify_webhook",
            session_id="order-order-1",
            stat_date=date(2026, 4, 23),
            visitor_id="shopify-order-order-1",
            events=[
                IngestEvent(
                    event_type=EventType.ORDER_COMPLETED,
                    occurred_at=occurred_at,
                    product_id="product-1",
                    context={"order_id": "order-1"},
                )
            ],
        )
        await session.commit()

    async with session_factory() as session:
        daily_stat = (await session.exec(select(DailyProductStat))).one()

    assert daily_stat.views == 1
    assert daily_stat.add_to_carts == 1
    assert daily_stat.orders == 1
    assert daily_stat.component_clicks_distribution == {"buy_box": 1}
    assert daily_stat.component_impressions_distribution == {"product_media": 1}


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
            channel="sdk_dom",
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

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            del name, kwargs, queue, task_id

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    occurred_at = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "shop_domain": "demo.myshopify.com",
        "visitor_id": "visitor-1",
        "session_id": "session-1",
        "events": [
            {
                "event_type": "product_impression",
                "occurred_at": occurred_at.isoformat(),
                "product_id": "product-1",
                "component_id": "featured-collection",
                "context": {"position": 2},
            },
            {
                "event_type": "product_click",
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
            await session.exec(select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com").order_by(RawEvent.id))
        ).all()

    assert len(raw_events) == 3
    assert raw_events[0].event_type == EventType.PRODUCT_IMPRESSION
    assert raw_events[1].event_type == EventType.PRODUCT_CLICK
    assert raw_events[2].event_type == EventType.ENGAGE
    assert raw_events[2].product_id is None


@pytest.mark.asyncio
async def test_sdk_dom_endpoint_rejects_pixel_funnel_events(
    sqlite_database_url: str,
    redis_url: str,
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

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/ingest/events",
            json={
                "shop_domain": "demo.myshopify.com",
                "visitor_id": "visitor-1",
                "session_id": "session-1",
                "events": [
                    {
                        "event_type": "product_view",
                        "occurred_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                        "product_id": "product-1",
                    },
                ],
            },
            headers={
                "X-SKU-Lens-Public-Token": "public-1",
                "X-SKU-Lens-Timestamp": str(int(time.time())),
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported SDK DOM event: product_view."
