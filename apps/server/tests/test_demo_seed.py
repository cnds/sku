from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from config import Settings
from db import create_session_factory
from main import create_app
from models import DailyProductStat, ProductDiagnosis, RawEvent
from seed_demo import seed_demo_data


def _settings(sqlite_database_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url="redis://localhost:6379/15",
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
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

    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        blackboard = await client.get(
            "/api/leaderboard",
            params={
                "board": "black",
                "shop_id": "demo.myshopify.com",
                "window": "24h",
            },
        )
        redboard = await client.get(
            "/api/leaderboard",
            params={
                "board": "red",
                "shop_id": "demo.myshopify.com",
                "window": "24h",
            },
        )
        priorities = await client.get(
            "/api/priorities",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )
        analysis = await client.get(
            "/api/products/demo-size-confidence-leaker/analysis",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )
        diagnosis = await client.get(
            "/api/products/demo-size-confidence-leaker/diagnosis",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert blackboard.status_code == 200
    assert redboard.status_code == 200
    assert priorities.status_code == 200
    assert analysis.status_code == 200
    assert diagnosis.status_code == 200

    assert blackboard.json()[0]["product_id"] == "demo-size-confidence-leaker"
    assert redboard.json()[0]["product_id"] == "demo-hidden-winner"
    assert [card["product_id"] for card in priorities.json()] == [
        "demo-size-confidence-leaker",
        "demo-media-trust-leaker",
        "demo-hidden-winner",
    ]
    assert analysis.json()["benchmark_product_id"] == "demo-benchmark"
    assert analysis.json()["component_comparisons"]
    assert diagnosis.json()["status"] == "ready"
    assert "## Observed" in diagnosis.json()["report_markdown"]
    assert "## Suspected friction" in diagnosis.json()["report_markdown"]

    async with create_session_factory(settings.database_url)() as session:
        daily_stats = (
            await session.exec(
                select(DailyProductStat).where(
                    DailyProductStat.shop_id == "demo.myshopify.com"
                )
            )
        ).all()
    component_labels = set()
    for daily_stat in daily_stats:
        component_labels.update(daily_stat.component_clicks_distribution)
        component_labels.update(daily_stat.component_impressions_distribution)

    assert {"product_description", "shipping_returns", "recommendations"}.issubset(component_labels)


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
        first_raw_events = (
            await session.exec(
                select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com")
            )
        ).all()
        first_daily_stats = (
            await session.exec(
                select(DailyProductStat).where(DailyProductStat.shop_id == "demo.myshopify.com")
            )
        ).all()
        first_diagnoses = (
            await session.exec(
                select(ProductDiagnosis).where(
                    ProductDiagnosis.shop_id == "demo.myshopify.com"
                )
            )
        ).all()

    await seed_demo_data(
        settings=settings,
        now_utc=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )

    async with session_factory() as session:
        second_raw_events = (
            await session.exec(
                select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com")
            )
        ).all()
        second_daily_stats = (
            await session.exec(
                select(DailyProductStat).where(DailyProductStat.shop_id == "demo.myshopify.com")
            )
        ).all()
        second_diagnoses = (
            await session.exec(
                select(ProductDiagnosis).where(
                    ProductDiagnosis.shop_id == "demo.myshopify.com"
                )
            )
        ).all()

    assert len(first_raw_events) > 0
    assert len(first_daily_stats) == 4
    assert len(first_diagnoses) == 12
    assert len(second_raw_events) == len(first_raw_events)
    assert len(second_daily_stats) == len(first_daily_stats)
    assert len(second_diagnoses) == len(first_diagnoses)
