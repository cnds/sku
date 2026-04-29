from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from config import Settings
from main import create_app
from models import DailyProductStat, EventType, RawEvent
from security.shopify import build_shopify_hmac


@pytest.mark.asyncio
async def test_shopify_webhook_rejects_invalid_hmac(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    settings = Settings(
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
    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/shopify/webhooks/orders/create",
            content=b'{"id": 1}',
            headers={
                "X-Shopify-Hmac-Sha256": "bad-signature",
                "X-Shopify-Shop-Domain": "demo.myshopify.com",
                "X-Shopify-Topic": "orders/create",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Shopify HMAC signature."


@pytest.mark.asyncio
async def test_shopify_webhook_accepts_valid_hmac(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    payload = {
        "id": 42,
        "line_items": [{"product_id": 1001, "quantity": 1}],
    }
    body = json.dumps(payload).encode()
    settings = Settings(
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
    app = create_app(settings)
    signature = build_shopify_hmac(settings.shopify_api_secret, body)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/shopify/webhooks/orders/create",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": signature,
                "X-Shopify-Shop-Domain": "demo.myshopify.com",
                "X-Shopify-Topic": "orders/create",
            },
        )

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "enqueued": 1}


@pytest.mark.asyncio
async def test_shopify_webhook_persists_order_rollup_and_enqueue_after_commit(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": 42,
        "line_items": [{"product_id": 1001, "quantity": 1}],
    }
    body = json.dumps(payload).encode()
    enqueued: list[tuple[str, dict[str, object]]] = []
    enqueue_visibility_checks: list[tuple[int, int]] = []

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        async with app.state.session_factory() as session:
            raw_events = (
                await session.exec(
                    select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com")
                )
            ).all()
            daily_stats = (
                await session.exec(
                    select(DailyProductStat).where(
                        DailyProductStat.shop_id == "demo.myshopify.com"
                    )
                )
            ).all()

        assert len(raw_events) == 1
        assert len(daily_stats) == 1
        enqueue_visibility_checks.append((len(raw_events), len(daily_stats)))
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

    settings = Settings(
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
    app = create_app(settings)
    signature = build_shopify_hmac(settings.shopify_api_secret, body)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/shopify/webhooks/orders/create",
            content=body,
            headers={
                "X-Shopify-Hmac-Sha256": signature,
                "X-Shopify-Shop-Domain": "demo.myshopify.com",
                "X-Shopify-Topic": "orders/create",
            },
        )

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "enqueued": 1}
    assert enqueue_visibility_checks == [(1, 1)]

    async with app.state.session_factory() as session:
        raw_events = (
            await session.exec(select(RawEvent).where(RawEvent.shop_id == "demo.myshopify.com"))
        ).all()
        daily_stats = (
            await session.exec(
                select(DailyProductStat).where(
                    DailyProductStat.shop_id == "demo.myshopify.com"
                )
            )
        ).all()

    assert len(raw_events) == 1
    assert raw_events[0].event_type == EventType.ORDER
    assert raw_events[0].channel == "webhook"
    assert raw_events[0].product_id == "1001"
    assert raw_events[0].context_json == {"order_id": "42", "quantity": 1}

    assert len(daily_stats) == 1
    assert daily_stats[0].product_id == "1001"
    assert daily_stats[0].orders == 1
    assert daily_stats[0].views == 0
    assert daily_stats[0].add_to_carts == 0
    assert len(enqueued) == 1
    queue_name, enqueued_payload = enqueued[0]
    assert queue_name == "sku-lens:rollups"
    assert enqueued_payload["shop_id"] == "demo.myshopify.com"
    assert enqueued_payload["stat_date"] == daily_stats[0].stat_date.isoformat()
    assert isinstance(enqueued_payload["job_id"], str)
