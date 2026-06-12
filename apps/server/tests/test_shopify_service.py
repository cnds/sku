from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from config import Settings
from models import ShopInstallation
from security.shopify import build_shopify_oauth_hmac
from services.shopify import (
    InvalidShopifyOAuthCallbackError,
    ShopifyInstallationCallbackService,
    ShopifyOAuthService,
    ShopifyOrderWebhookService,
    ShopifyWebPixelService,
)


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:////tmp/sku_lens.db",
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url="redis://localhost:6379/0",
        shopify_api_key="shopify-key",
        shopify_api_secret="shopify-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
        shopify_webhook_base_url="https://example.com",
    )


@pytest.mark.asyncio
async def test_shopify_installation_callback_service_exchanges_token_and_upserts_installation() -> None:
    exchanged: list[tuple[str, str]] = []
    pixel_upserts: list[tuple[str, str, str]] = []
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

    class StubPixelService:
        async def upsert_web_pixel(
            self,
            *,
            access_token: str,
            public_token: str,
            shop_domain: str,
        ) -> None:
            pixel_upserts.append((access_token, public_token, shop_domain))

    service = ShopifyInstallationCallbackService(
        _settings(),
        oauth_service=StubOAuthService(),
        installation_service=StubInstallationService(),
        pixel_service=StubPixelService(),
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
    assert pixel_upserts == [("access-1", "public-1", "demo.myshopify.com")]
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


@pytest.mark.asyncio
async def test_shopify_oauth_service_exchanges_access_token_with_form_encoded_body() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"access_token": "access-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        received = await ShopifyOAuthService(
            _settings(),
            http_client=client,
        ).exchange_access_token(
            code="oauth-code",
            shop_domain="demo.myshopify.com",
        )

    assert received == "access-1"
    assert captured_request is not None
    assert str(captured_request.url) == "https://demo.myshopify.com/admin/oauth/access_token"
    assert captured_request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert captured_request.content == (b"client_id=shopify-key&client_secret=shopify-secret&code=oauth-code")


def test_shopify_order_webhook_service_builds_product_order_events() -> None:
    batch = ShopifyOrderWebhookService().build_order_ingestion_batch(
        payload={
            "created_at": "2026-04-28T15:05:00Z",
            "id": 9001,
            "line_items": [
                {
                    "id": 7001,
                    "product_id": 1001,
                    "quantity": 2,
                    "variant_id": 2001,
                },
                {"id": 7002, "quantity": 1},
            ],
            "name": "#1001",
        },
        shop_domain="demo.myshopify.com",
        timezone_name="UTC",
    )

    assert batch.shop_domain == "demo.myshopify.com"
    assert batch.session_id == "order-9001"
    assert batch.visitor_id == "shopify-order-9001"
    assert batch.stat_date.isoformat() == "2026-04-28"
    assert len(batch.events) == 1
    assert batch.events[0].event_type.value == "order_completed"
    assert batch.events[0].product_id == "1001"
    assert batch.events[0].variant_id == "2001"
    assert batch.events[0].event_id == "9001"
    assert batch.events[0].source_event_name == "orders/create"
    assert batch.events[0].dedupe_key == "orders/create|9001|1001|2001|7001"
    assert batch.events[0].context["quantity"] == 2


@pytest.mark.asyncio
async def test_shopify_web_pixel_service_creates_missing_pixel() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json_body(request)
        if "query { webPixel" in payload["query"]:
            return httpx.Response(200, json={"data": {"webPixel": None}})
        return httpx.Response(
            200,
            json={
                "data": {
                    "webPixelCreate": {
                        "userErrors": [],
                        "webPixel": {"id": "gid://shopify/WebPixel/1", "settings": "{}"},
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ShopifyWebPixelService(
            _settings(),
            http_client=client,
        ).upsert_web_pixel(
            access_token="access-1",
            public_token="public-1",
            shop_domain="demo.myshopify.com",
        )

    assert result.created is True
    assert result.pixel_id == "gid://shopify/WebPixel/1"
    assert len(requests) == 2
    mutation_payload = json_body(requests[1])
    assert "webPixelCreate" in mutation_payload["query"]
    assert mutation_payload["variables"]["webPixel"]["settings"] == {
        "endpoint": "https://example.com/ingest/pixel-events",
        "publicToken": "public-1",
        "shopDomain": "demo.myshopify.com",
    }


@pytest.mark.asyncio
async def test_shopify_web_pixel_service_updates_existing_pixel() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json_body(request)
        if "query { webPixel" in payload["query"]:
            return httpx.Response(
                200,
                json={"data": {"webPixel": {"id": "gid://shopify/WebPixel/1", "settings": "{}"}}},
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "webPixelUpdate": {
                        "userErrors": [],
                        "webPixel": {"id": "gid://shopify/WebPixel/1", "settings": "{}"},
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ShopifyWebPixelService(
            _settings(),
            http_client=client,
        ).upsert_web_pixel(
            access_token="access-1",
            public_token="public-2",
            shop_domain="demo.myshopify.com",
        )

    assert result.created is False
    assert result.pixel_id == "gid://shopify/WebPixel/1"
    assert len(requests) == 2
    mutation_payload = json_body(requests[1])
    assert "webPixelUpdate" in mutation_payload["query"]
    assert mutation_payload["variables"]["id"] == "gid://shopify/WebPixel/1"
    assert mutation_payload["variables"]["webPixel"]["settings"]["publicToken"] == "public-2"


def json_body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode())
