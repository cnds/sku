from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config import Settings
from models import ShopInstallation
from security.shopify import build_shopify_oauth_hmac
from services.shopify import (
    InvalidShopifyOAuthCallbackError,
    ShopifyInstallationCallbackService,
    ShopifyOrderWebhookService,
)


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:////tmp/sku_lens.db",
        gemini_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url="redis://localhost:6379/0",
        shopify_api_key="shopify-key",
        shopify_api_secret="shopify-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://example.com",
    )


def test_shopify_order_webhook_service_builds_ingestion_batch() -> None:
    occurred_at = datetime(2026, 4, 28, 15, 5, tzinfo=UTC)
    service = ShopifyOrderWebhookService(time_provider=lambda: occurred_at)

    batch = service.build_order_ingestion_batch(
        payload={
            "id": 42,
            "line_items": [
                {"product_id": 1001, "quantity": 2},
                {"quantity": 1},
                {"product_id": None, "quantity": 5},
            ],
        },
        shop_domain="demo.myshopify.com",
        timezone_name="Asia/Tokyo",
    )

    assert batch.shop_id == "demo.myshopify.com"
    assert batch.shop_domain == "demo.myshopify.com"
    assert batch.session_id == "order-42"
    assert batch.stat_date.isoformat() == "2026-04-29"
    assert batch.visitor_id == "shopify-order-42"
    assert len(batch.events) == 1
    assert batch.events[0].event_type.value == "order"
    assert batch.events[0].occurred_at == occurred_at
    assert batch.events[0].product_id == "1001"
    assert batch.events[0].context == {"order_id": "42", "quantity": 2}


@pytest.mark.asyncio
async def test_shopify_installation_callback_service_exchanges_token_and_upserts_installation() -> None:
    exchanged: list[tuple[str, str]] = []
    upserted: list[tuple[str, str, str | None, str]] = []

    class StubOAuthService:
        async def exchange_access_token(self, *, code: str, shop_domain: str) -> str:
            exchanged.append((code, shop_domain))
            return "access-1"

        async def fetch_shop_timezone(
            self,
            *,
            access_token: str,
            shop_domain: str,
        ) -> str:
            assert access_token.startswith("access-")
            assert access_token.endswith("1")
            assert shop_domain == "demo.myshopify.com"
            return "Asia/Tokyo"

    class StubInstallationService:
        async def upsert_installation(
            self,
            *,
            shop_domain: str,
            public_token: str,
            access_token: str | None,
            timezone_name: str,
        ) -> ShopInstallation:
            upserted.append((shop_domain, public_token, access_token, timezone_name))
            return ShopInstallation(
                shop_domain=shop_domain,
                public_token=public_token,
                access_token=access_token,
                timezone_name=timezone_name,
            )

    service = ShopifyInstallationCallbackService(
        _settings(),
        oauth_service=StubOAuthService(),
        installation_service=StubInstallationService(),
        token_provider=lambda: "public-1",
    )
    callback_params = {
        "code": "oauth-code",
        "shop": "demo.myshopify.com",
        "timestamp": "1700000000",
    }
    callback_params["hmac"] = build_shopify_oauth_hmac(
        _settings().shopify_api_secret,
        callback_params,
    )

    installation = await service.complete_installation(
        shop_domain="demo.myshopify.com",
        code="oauth-code",
        callback_params=callback_params,
    )

    assert exchanged == [("oauth-code", "demo.myshopify.com")]
    assert upserted == [("demo.myshopify.com", "public-1", "access-1", "Asia/Tokyo")]
    assert installation.shop_domain == "demo.myshopify.com"
    assert installation.public_token == upserted[0][1]
    assert installation.access_token == upserted[0][2]
    assert installation.timezone_name == "Asia/Tokyo"


@pytest.mark.asyncio
async def test_shopify_installation_callback_service_rejects_unsigned_callback() -> None:
    service = ShopifyInstallationCallbackService(_settings())

    with pytest.raises(InvalidShopifyOAuthCallbackError) as exc_info:
        await service.complete_installation(
            shop_domain="demo.myshopify.com",
            code="oauth-code",
            callback_params={
                "code": "oauth-code",
                "shop": "demo.myshopify.com",
                "timestamp": "1700000000",
            },
        )

    assert str(exc_info.value) == "Invalid Shopify OAuth callback signature."
