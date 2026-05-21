from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from config import Settings
from models import EventType, ShopInstallation
from schemas import IngestEvent
from security.shopify import verify_shopify_oauth_hmac
from services.shop_installations import ShopInstallationService
from services.shop_time import local_date_for_shop, normalize_shop_timezone

SHOPIFY_OAUTH_STATE_COOKIE = "sku_lens_oauth_state"
APP_EMBED_BLOCK_HANDLE = "sku-lens-tracker"
SHOP_DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


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


class MissingShopifyOAuthCodeError(Exception):
    def __init__(self) -> None:
        super().__init__("Missing Shopify OAuth authorization code.")


class InvalidShopifyOAuthStateError(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid Shopify OAuth state.")


class InvalidShopifyShopDomainError(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid Shopify shop domain.")


def normalize_shop_domain(shop_domain: str) -> str:
    normalized = shop_domain.strip().lower()
    if not SHOP_DOMAIN_PATTERN.fullmatch(normalized):
        raise InvalidShopifyShopDomainError()
    return normalized


def build_oauth_authorization_url(
    *,
    settings: Settings,
    shop_domain: str,
    state: str,
) -> str:
    normalized_shop_domain = normalize_shop_domain(shop_domain)
    query = urlencode(
        {
            "client_id": settings.shopify_api_key,
            "scope": settings.shopify_scopes,
            "redirect_uri": f"{settings.shopify_webhook_base_url.rstrip('/')}/shopify/oauth/callback",
            "state": state,
        }
    )
    return f"https://{normalized_shop_domain}/admin/oauth/authorize?{query}"


def build_onboarding_url(
    *,
    settings: Settings,
    shop_domain: str,
    window: str = "24h",
    host: str | None = None,
) -> str:
    query_params = {"shop": normalize_shop_domain(shop_domain), "window": window}
    if host:
        query_params["host"] = host
    query = urlencode(query_params)
    return f"{settings.shopify_app_url.rstrip('/')}/onboarding?{query}"


def build_ingest_endpoint(settings: Settings) -> str:
    return f"{settings.shopify_webhook_base_url.rstrip('/')}/ingest/events"


def build_app_embed_deep_link(*, settings: Settings, shop_domain: str) -> str:
    normalized_shop_domain = normalize_shop_domain(shop_domain)
    query = urlencode(
        {
            "context": "apps",
        }
    )
    activate_app_id = f"{settings.shopify_api_key}/{APP_EMBED_BLOCK_HANDLE}"
    return (
        f"https://{normalized_shop_domain}/admin/themes/current/editor?"
        f"{query}&activateAppId={activate_app_id}"
    )


def new_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def verify_oauth_state(*, cookie_state: str | None, returned_state: str | None) -> None:
    if not cookie_state or not returned_state or not secrets.compare_digest(cookie_state, returned_state):
        raise InvalidShopifyOAuthStateError()


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
        timezone_name: str | None = None,
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
            stat_date=local_date_for_shop(
                instant=occurred_at,
                timezone_name=timezone_name,
            ),
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
        normalized_shop_domain = normalize_shop_domain(shop_domain)
        if callback_params is not None and not verify_shopify_oauth_hmac(
            self._settings.shopify_api_secret,
            callback_params,
        ):
            raise InvalidShopifyOAuthCallbackError()

        public_token = self._token_provider()
        access_token = None
        timezone_name = normalize_shop_timezone(None)
        if code:
            access_token = await self._oauth_service.exchange_access_token(
                code=code,
                shop_domain=normalized_shop_domain,
            )
            timezone_name = await self._oauth_service.fetch_shop_timezone(
                access_token=access_token,
                shop_domain=normalized_shop_domain,
            )

        return await self._installation_service.upsert_installation(
            shop_domain=normalized_shop_domain,
            public_token=public_token,
            access_token=access_token,
            timezone_name=timezone_name,
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
                data={
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

    async def fetch_shop_timezone(
        self,
        *,
        access_token: str,
        shop_domain: str,
    ) -> str:
        client = self._http_client or httpx.AsyncClient(timeout=20.0)
        should_close = self._http_client is None
        try:
            response = await client.get(
                f"https://{shop_domain}/admin/api/latest/shop.json",
                headers={"X-Shopify-Access-Token": access_token},
            )
            response.raise_for_status()
            payload = response.json()
            shop_payload = payload.get("shop", {})
            return normalize_shop_timezone(str(shop_payload.get("iana_timezone") or "UTC"))
        except httpx.HTTPError:
            return normalize_shop_timezone(None)
        finally:
            if should_close:
                await client.aclose()
