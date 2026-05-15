from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient

import repositories.analytics as analytics_repository_module
import services.integration_health as integration_health_module
from config import Settings
from db import create_session_factory, db_session_context, init_db
from main import create_app
from models import DailyProductStat, EventType, RawEvent, ShopInstallation


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://example.com",
    )


@pytest.mark.asyncio
async def test_integration_health_reports_not_connected_without_installation(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/integration/health",
            params={"shop_id": "missing.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_connected"
    assert payload["last_event_at"] is None
    assert payload["coverage"] == {
        "add_to_carts": 0,
        "clicks": 0,
        "component_clicks": 0,
        "impressions": 0,
        "orders": 0,
        "views": 0,
    }
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["installation"]["status"] == "missing"
    assert checks["storefront_events"]["status"] == "missing"


@pytest.mark.asyncio
async def test_integration_health_reports_partial_when_funnel_steps_are_missing(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    now_utc = datetime.now(UTC).replace(microsecond=0)

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="UTC",
            )
        )
        session.add(
            RawEvent(
                shop_id="demo.myshopify.com",
                shop_domain="demo.myshopify.com",
                visitor_id="visitor-1",
                session_id="session-1",
                event_type=EventType.VIEW,
                product_id="product-1",
                channel="sdk",
                occurred_at=now_utc,
            )
        )
        session.add(
            DailyProductStat(
                shop_id="demo.myshopify.com",
                product_id="product-1",
                stat_date=now_utc.date(),
                views=24,
            )
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/integration/health",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["last_event_at"] == now_utc.isoformat().replace("+00:00", "Z")
    assert payload["coverage"]["views"] == 24
    assert payload["coverage"]["component_clicks"] == 0
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["installation"]["status"] == "ok"
    assert checks["pdp_views"]["status"] == "ok"
    assert checks["component_tracking"]["status"] == "missing"
    assert checks["buy_box_add_to_cart"]["status"] == "missing"
    assert checks["orders_webhook"]["status"] == "missing"


@pytest.mark.asyncio
async def test_integration_health_uses_shop_local_reference_date_for_window(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    fixed_now = datetime(2026, 5, 2, 15, 30, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # noqa: ANN001
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(integration_health_module, "datetime", FixedDateTime)
    monkeypatch.setattr(analytics_repository_module, "datetime", FixedDateTime)

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="tokyo.myshopify.com",
                public_token="public-1",
                timezone_name="Asia/Tokyo",
            )
        )
        session.add(
            RawEvent(
                shop_id="tokyo.myshopify.com",
                shop_domain="tokyo.myshopify.com",
                visitor_id="visitor-1",
                session_id="session-1",
                event_type=EventType.VIEW,
                product_id="product-1",
                channel="sdk",
                occurred_at=fixed_now,
            )
        )
        session.add(
            DailyProductStat(
                shop_id="tokyo.myshopify.com",
                product_id="product-1",
                stat_date=date(2026, 5, 1),
                views=80,
                add_to_carts=14,
                orders=3,
                component_clicks_distribution={"buy_box": 2},
            )
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/integration/health",
            params={"shop_id": "tokyo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"]["views"] == 0
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["pdp_views"]["status"] == "missing"


@pytest.mark.asyncio
async def test_integration_health_does_not_count_collection_clicks_as_component_tracking(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    now_utc = datetime.now(UTC).replace(microsecond=0)

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="UTC",
            )
        )
        session.add(
            RawEvent(
                shop_id="demo.myshopify.com",
                shop_domain="demo.myshopify.com",
                visitor_id="visitor-1",
                session_id="session-1",
                event_type=EventType.CLICK,
                component_id="featured-collection",
                product_id="product-1",
                channel="sdk",
                occurred_at=now_utc,
            )
        )
        session.add(
            DailyProductStat(
                shop_id="demo.myshopify.com",
                product_id="product-1",
                stat_date=now_utc.date(),
                views=80,
                add_to_carts=14,
                orders=3,
                impressions=180,
                clicks=32,
                component_clicks_distribution={"featured-collection": 12},
            )
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/integration/health",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["coverage"]["component_clicks"] == 0
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["component_tracking"]["status"] == "missing"


@pytest.mark.asyncio
async def test_integration_health_reports_healthy_when_core_coverage_is_present(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    now_utc = datetime.now(UTC).replace(microsecond=0)
    component_clicks = {
        "buy_box": 14,
        "product_description": 8,
        "shipping_returns": 4,
    }

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="UTC",
            )
        )
        session.add_all(
            [
                RawEvent(
                    shop_id="demo.myshopify.com",
                    shop_domain="demo.myshopify.com",
                    visitor_id="visitor-1",
                    session_id="session-1",
                    event_type=EventType.VIEW,
                    product_id="product-1",
                    channel="sdk",
                    occurred_at=now_utc,
                ),
                RawEvent(
                    shop_id="demo.myshopify.com",
                    shop_domain="demo.myshopify.com",
                    visitor_id="visitor-1",
                    session_id="session-1",
                    event_type=EventType.ORDER,
                    product_id="product-1",
                    channel="webhook",
                    occurred_at=now_utc,
                ),
                *[
                    RawEvent(
                        shop_id="demo.myshopify.com",
                        shop_domain="demo.myshopify.com",
                        visitor_id="visitor-1",
                        session_id="session-1",
                        event_type=EventType.COMPONENT_CLICK,
                        component_id=component_id,
                        product_id="product-1",
                        channel="sdk",
                        occurred_at=now_utc,
                    )
                    for component_id, count in component_clicks.items()
                    for _ in range(count)
                ],
            ]
        )
        session.add(
            DailyProductStat(
                shop_id="demo.myshopify.com",
                product_id="product-1",
                stat_date=now_utc.date(),
                views=80,
                add_to_carts=14,
                orders=3,
                impressions=180,
                clicks=32,
                component_clicks_distribution=component_clicks,
            )
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/integration/health",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["coverage"] == {
        "add_to_carts": 14,
        "clicks": 32,
        "component_clicks": 26,
        "impressions": 180,
        "orders": 3,
        "views": 80,
    }
    assert {check["status"] for check in payload["checks"]} == {"ok"}
