from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from config import Settings
from models import EventType, ShopInstallation
from schemas import IngestEvent
from security.shopify import verify_shopify_oauth_hmac
from services.shop_installations import ShopInstallationService


@dataclass(slots=True)
class ShopifyOrderIngestionBatch:
    events: list[IngestEvent]
    session_id: str
    shop_domain: str
    shop_id: str
    stat_date: date
    visitor_id: str


class InvalidShopifyOAuthCallbackError(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid Shopify OAuth callback signature.")


class ShopifyOrderWebhookService:
    def __init__(
        self,
        *,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._time_provider = time_provider or (lambda: datetime.now(UTC))

    def build_order_ingestion_batch(
        self,
        *,
        payload: dict[str, Any],
        shop_domain: str,
    ) -> ShopifyOrderIngestionBatch:
        order_id = str(payload.get("id", "unknown"))
        occurred_at = self._time_provider()
        line_items = payload.get("line_items", [])
        events = [
            IngestEvent(
                event_type=EventType.ORDER,
                occurred_at=occurred_at,
                product_id=str(item["product_id"]),
                context={"order_id": order_id, "quantity": item.get("quantity", 1)},
            )
            for item in line_items
            if item.get("product_id") is not None
        ]
        return ShopifyOrderIngestionBatch(
            events=events,
            session_id=f"order-{order_id}",
            shop_domain=shop_domain,
            shop_id=shop_domain,
            stat_date=occurred_at.date(),
            visitor_id=f"shopify-order-{order_id}",
        )


class ShopifyInstallationCallbackService:
    def __init__(
        self,
        settings: Settings,
        *,
        oauth_service: ShopifyOAuthService | None = None,
        installation_service: ShopInstallationService | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self._settings = settings
        self._oauth_service = oauth_service or ShopifyOAuthService(settings)
        self._installation_service = installation_service or ShopInstallationService()
        self._token_provider = token_provider or (lambda: secrets.token_urlsafe(24))

    async def complete_installation(
        self,
        *,
        shop_domain: str,
        code: str | None = None,
        callback_params: Mapping[str, str] | None = None,
    ) -> ShopInstallation:
        if callback_params is not None and not verify_shopify_oauth_hmac(
            self._settings.shopify_api_secret,
            callback_params,
        ):
            raise InvalidShopifyOAuthCallbackError()

        public_token = self._token_provider()
        access_token = None
        if code:
            access_token = await self._oauth_service.exchange_access_token(
                code=code,
                shop_domain=shop_domain,
            )

        return await self._installation_service.upsert_installation(
            shop_domain=shop_domain,
            public_token=public_token,
            access_token=access_token,
        )


class ShopifyOAuthService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def exchange_access_token(self, *, code: str, shop_domain: str) -> str:
        client = self._http_client or httpx.AsyncClient(timeout=20.0)
        should_close = self._http_client is None
        try:
            response = await client.post(
                f"https://{shop_domain}/admin/oauth/access_token",
                json={
                    "client_id": self._settings.shopify_api_key,
                    "client_secret": self._settings.shopify_api_secret,
                    "code": code,
                },
            )
            response.raise_for_status()
            payload = response.json()
            access_token = payload.get("access_token")
            if not access_token:
                raise httpx.HTTPStatusError(
                    "Missing access token in Shopify OAuth response.",
                    request=response.request,
                    response=response,
                )
            return access_token
        finally:
            if should_close:
                await client.aclose()
