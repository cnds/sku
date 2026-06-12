from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from config import Settings
from db import create_session_factory, init_db
from main import create_app
from models import DailyProductStat, ProductDiagnosis, RawEvent, ShopInstallation
from seed_demo import DEFAULT_SHOP_DOMAIN, seed_demo_data


def _settings(sqlite_database_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url="redis://localhost:6379/15",
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
        shopify_webhook_base_url="https://example.com",
    )


@pytest.mark.asyncio
async def test_seed_demo_data_populates_dashboard_and_product_analysis_endpoints(
    sqlite_database_url: str,
) -> None:
    settings = _settings(sqlite_database_url)
    now_utc = datetime.now(UTC)

    await seed_demo_data(
        settings=settings,
        now_utc=now_utc,
    )

    assert DEFAULT_SHOP_DOMAIN == "sku-dev-uaop8pff.myshopify.com"

    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        blackboard = await client.get(
            "/api/leaderboard",
            params={
                "board": "black",
                "shop_id": DEFAULT_SHOP_DOMAIN,
                "window": "24h",
            },
        )
        redboard = await client.get(
            "/api/leaderboard",
            params={
                "board": "red",
                "shop_id": DEFAULT_SHOP_DOMAIN,
                "window": "24h",
            },
        )
        priorities = await client.get(
            "/api/priorities",
            params={"shop_id": DEFAULT_SHOP_DOMAIN, "window": "24h"},
        )
        seven_day_priorities = await client.get(
            "/api/priorities",
            params={"shop_id": DEFAULT_SHOP_DOMAIN, "window": "7d"},
        )
        analysis = await client.get(
            "/api/products/demo-size-confidence-leaker/analysis",
            params={"shop_id": DEFAULT_SHOP_DOMAIN, "window": "24h"},
        )
        diagnosis = await client.get(
            "/api/products/demo-size-confidence-leaker/diagnosis",
            params={"shop_id": DEFAULT_SHOP_DOMAIN, "window": "24h"},
        )

    assert blackboard.status_code == 200
    assert redboard.status_code == 200
    assert priorities.status_code == 200
    assert seven_day_priorities.status_code == 200
    assert analysis.status_code == 200
    assert diagnosis.status_code == 200

    assert blackboard.json()[0]["product_id"] == "demo-size-confidence-leaker"
    assert redboard.json()[0]["product_id"] == "demo-hidden-winner"
    assert [card["product_id"] for card in priorities.json()] == [
        "demo-size-confidence-leaker",
        "demo-media-trust-leaker",
        "demo-hidden-winner",
    ]
    assert priorities.json()[0]["first_fix"] == (
        "Move the size chart beside the variant selector and repeat fit guidance near the buy box."
    )
    assert {card["trend_reason"] for card in seven_day_priorities.json()} != {"No previous 7d comparison window yet."}
    assert analysis.json()["benchmark_product_id"] == "demo-benchmark"
    assert analysis.json()["component_comparisons"]
    assert diagnosis.json()["status"] == "ready"
    assert "## Observed" in diagnosis.json()["report_markdown"]
    assert "## Suspected friction" in diagnosis.json()["report_markdown"]

    async with create_session_factory(settings.database_url)() as session:
        daily_stats = (
            await session.exec(select(DailyProductStat).where(DailyProductStat.shop_id == DEFAULT_SHOP_DOMAIN))
        ).all()
    component_labels = set()
    for daily_stat in daily_stats:
        component_labels.update(daily_stat.component_clicks_distribution)
        component_labels.update(daily_stat.component_impressions_distribution)

    assert {"product_description", "shipping_returns", "recommendations"}.issubset(component_labels)


@pytest.mark.asyncio
async def test_seed_demo_data_targets_existing_shopify_installation_without_wiping_access_token(
    sqlite_database_url: str,
) -> None:
    settings = _settings(sqlite_database_url)
    shop_domain = "merchant-dev.myshopify.com"
    existing_access = "existing-shopify-access-value"
    existing_public = "existing-public-value"
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add(
            ShopInstallation(
                access_token=existing_access,
                public_token=existing_public,
                shop_domain=shop_domain,
                timezone_name="Asia/Shanghai",
            )
        )
        await session.commit()

    summary = await seed_demo_data(
        settings=settings,
        now_utc=datetime.now(UTC),
    )

    assert summary.shop_domain == shop_domain
    assert summary.dashboard_url == f"http://localhost:3000/?shop={shop_domain}&window=24h"

    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        onboarding = await client.get(
            "/api/onboarding/status",
            params={"shop_id": shop_domain, "window": "24h"},
        )
        priorities = await client.get(
            "/api/priorities",
            params={"shop_id": shop_domain, "window": "24h"},
        )

    assert onboarding.status_code == 200
    assert onboarding.json()["installed"] is True
    assert onboarding.json()["integration_health"]["status"] == "healthy"
    assert {item["status"] for item in onboarding.json()["checklist"]} == {"done"}
    assert priorities.status_code == 200
    assert [card["product_id"] for card in priorities.json()] == [
        "demo-size-confidence-leaker",
        "demo-media-trust-leaker",
        "demo-hidden-winner",
    ]

    async with session_factory() as session:
        installation = (
            await session.exec(select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain))
        ).one()

    assert installation.access_token == existing_access
    assert installation.public_token == existing_public


@pytest.mark.asyncio
async def test_seed_demo_data_prefers_oauth_installation_over_fallback_demo_shop(
    sqlite_database_url: str,
) -> None:
    settings = _settings(sqlite_database_url)
    shop_domain = "merchant-dev.myshopify.com"
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                ShopInstallation(
                    installed_at=datetime(2026, 5, 27, 9, 0, tzinfo=UTC),
                    public_token="fallback-public-value",
                    shop_domain=DEFAULT_SHOP_DOMAIN,
                    timezone_name="UTC",
                ),
                ShopInstallation(
                    access_token="oauth-access-value",
                    installed_at=datetime(2026, 5, 27, 8, 0, tzinfo=UTC),
                    public_token="oauth-public-value",
                    shop_domain=shop_domain,
                    timezone_name="Asia/Shanghai",
                ),
            ]
        )
        await session.commit()

    summary = await seed_demo_data(
        settings=settings,
        now_utc=datetime(2026, 5, 27, 8, 0, tzinfo=UTC),
    )

    assert summary.shop_domain == shop_domain


@pytest.mark.asyncio
async def test_seed_demo_data_is_idempotent_for_demo_products(
    sqlite_database_url: str,
) -> None:
    settings = _settings(sqlite_database_url)
    session_factory = create_session_factory(sqlite_database_url)

    await seed_demo_data(
        settings=settings,
        now_utc=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )

    async with session_factory() as session:
        first_raw_events = (await session.exec(select(RawEvent).where(RawEvent.shop_id == DEFAULT_SHOP_DOMAIN))).all()
        first_daily_stats = (
            await session.exec(select(DailyProductStat).where(DailyProductStat.shop_id == DEFAULT_SHOP_DOMAIN))
        ).all()
        first_diagnoses = (
            await session.exec(select(ProductDiagnosis).where(ProductDiagnosis.shop_id == DEFAULT_SHOP_DOMAIN))
        ).all()

    await seed_demo_data(
        settings=settings,
        now_utc=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )

    async with session_factory() as session:
        second_raw_events = (await session.exec(select(RawEvent).where(RawEvent.shop_id == DEFAULT_SHOP_DOMAIN))).all()
        second_daily_stats = (
            await session.exec(select(DailyProductStat).where(DailyProductStat.shop_id == DEFAULT_SHOP_DOMAIN))
        ).all()
        second_diagnoses = (
            await session.exec(select(ProductDiagnosis).where(ProductDiagnosis.shop_id == DEFAULT_SHOP_DOMAIN))
        ).all()

    assert len(first_raw_events) > 0
    assert len(first_daily_stats) == 8
    assert len(first_diagnoses) == 12
    assert len(second_raw_events) == len(first_raw_events)
    assert len(second_daily_stats) == len(first_daily_stats)
    assert len(second_diagnoses) == len(first_diagnoses)
