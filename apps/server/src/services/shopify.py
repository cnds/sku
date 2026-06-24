from __future__ import annotations

import logging
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
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ShopifyWebPixelSetupResult:
    created: bool
    pixel_id: str | None


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


class ShopifyOAuthTokenExchangeError(Exception):
    def __init__(self, *, upstream_status_code: int | None = None) -> None:
        self.upstream_status_code = upstream_status_code
        super().__init__(
            "Shopify OAuth token exchange failed. Check Shopify app credentials, allowed redirect URL, "
            "and retry installation from /shopify/oauth/start."
        )


class InvalidShopifyShopDomainError(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid Shopify shop domain.")


class ShopifyWebPixelSetupError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


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


def build_pixel_ingest_endpoint(settings: Settings) -> str:
    return f"{settings.shopify_webhook_base_url.rstrip('/')}/ingest/pixel-events"


def build_app_embed_deep_link(*, settings: Settings, shop_domain: str) -> str:
    normalized_shop_domain = normalize_shop_domain(shop_domain)
    query = urlencode(
        {
            "context": "apps",
        }
    )
    activate_app_id = f"{settings.shopify_api_key}/{APP_EMBED_BLOCK_HANDLE}"
    return f"https://{normalized_shop_domain}/admin/themes/current/editor?{query}&activateAppId={activate_app_id}"


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
        order_id = str(payload.get("id") or payload.get("admin_graphql_api_id") or "unknown")
        occurred_at = _order_occurred_at(payload, fallback=self._time_provider)
        line_items = payload.get("line_items", [])
        events = [
            IngestEvent(
                context={
                    "line_item_id": str(item.get("id")) if item.get("id") is not None else None,
                    "line_item_index": index,
                    "order_id": order_id,
                    "order_name": payload.get("name"),
                    "product_id_source": "order_webhook",
                    "quantity": item.get("quantity", 1),
                    "source_event_name": "orders/create",
                },
                dedupe_key="|".join(
                    [
                        "orders/create",
                        order_id,
                        str(item.get("product_id")),
                        "" if item.get("variant_id") is None else str(item.get("variant_id")),
                        str(item.get("id")) if item.get("id") is not None else str(index),
                    ]
                ),
                event_id=order_id,
                event_type=EventType.ORDER_COMPLETED,
                occurred_at=occurred_at,
                product_id=str(item["product_id"]),
                source_event_name="orders/create",
                variant_id=str(item["variant_id"]) if item.get("variant_id") is not None else None,
            )
            for index, item in enumerate(line_items)
            if isinstance(item, dict) and item.get("product_id") is not None
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


def _order_occurred_at(payload: dict[str, Any], *, fallback: Callable[[], datetime]) -> datetime:
    for key in ("processed_at", "created_at", "updated_at"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return fallback()


def _response_excerpt(response: httpx.Response) -> str:
    return response.text.strip()[:300]


class ShopifyInstallationCallbackService:
    def __init__(
        self,
        settings: Settings,
        *,
        oauth_service: ShopifyOAuthService | None = None,
        installation_service: ShopInstallationService | None = None,
        pixel_service: ShopifyWebPixelService | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self._settings = settings
        self._oauth_service = oauth_service or ShopifyOAuthService(settings)
        self._installation_service = installation_service or ShopInstallationService()
        self._pixel_service = pixel_service or ShopifyWebPixelService(settings)
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

        installation = await self._installation_service.upsert_installation(
            shop_domain=normalized_shop_domain,
            public_token=public_token,
            access_token=access_token,
            timezone_name=timezone_name,
        )
        if access_token is not None:
            await self._pixel_service.upsert_web_pixel(
                access_token=access_token,
                public_token=public_token,
                shop_domain=normalized_shop_domain,
            )
        return installation


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
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                LOGGER.warning(
                    "shopify oauth token exchange failed shop_domain=%s status=%s response=%s",
                    shop_domain,
                    exc.response.status_code,
                    _response_excerpt(exc.response),
                )
                raise ShopifyOAuthTokenExchangeError(upstream_status_code=exc.response.status_code) from exc

            try:
                payload = response.json()
            except ValueError as exc:
                LOGGER.warning(
                    "shopify oauth token exchange returned invalid json shop_domain=%s status=%s response=%s",
                    shop_domain,
                    response.status_code,
                    _response_excerpt(response),
                )
                raise ShopifyOAuthTokenExchangeError(upstream_status_code=response.status_code) from exc

            access_token = payload.get("access_token")
            if not access_token:
                LOGGER.warning(
                    "shopify oauth token exchange returned no access token shop_domain=%s status=%s response=%s",
                    shop_domain,
                    response.status_code,
                    _response_excerpt(response),
                )
                raise ShopifyOAuthTokenExchangeError(upstream_status_code=response.status_code)
            return str(access_token)
        except httpx.RequestError as exc:
            LOGGER.warning(
                "shopify oauth token exchange request failed shop_domain=%s error=%s",
                shop_domain,
                exc,
            )
            raise ShopifyOAuthTokenExchangeError(upstream_status_code=None) from exc
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


class ShopifyWebPixelService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def upsert_web_pixel(
        self,
        *,
        access_token: str,
        public_token: str,
        shop_domain: str,
    ) -> ShopifyWebPixelSetupResult:
        existing = await self._fetch_web_pixel(
            access_token=access_token,
            shop_domain=shop_domain,
        )
        settings = {
            "endpoint": build_pixel_ingest_endpoint(self._settings),
            "publicToken": public_token,
            "shopDomain": shop_domain,
        }

        if existing is None:
            pixel = await self._mutate_web_pixel(
                access_token=access_token,
                mutation_name="webPixelCreate",
                query=(
                    "mutation webPixelCreate($webPixel: WebPixelInput!) { "
                    "webPixelCreate(webPixel: $webPixel) { "
                    "userErrors { field message code } "
                    "webPixel { id settings } "
                    "} "
                    "}"
                ),
                shop_domain=shop_domain,
                variables={"webPixel": {"settings": settings}},
            )
            return ShopifyWebPixelSetupResult(
                created=True,
                pixel_id=pixel.get("id") if pixel is not None else None,
            )

        pixel = await self._mutate_web_pixel(
            access_token=access_token,
            mutation_name="webPixelUpdate",
            query=(
                "mutation webPixelUpdate($id: ID!, $webPixel: WebPixelInput!) { "
                "webPixelUpdate(id: $id, webPixel: $webPixel) { "
                "userErrors { field message code } "
                "webPixel { id settings } "
                "} "
                "}"
            ),
            shop_domain=shop_domain,
            variables={
                "id": existing["id"],
                "webPixel": {"settings": settings},
            },
        )
        return ShopifyWebPixelSetupResult(
            created=False,
            pixel_id=pixel.get("id") if pixel is not None else existing["id"],
        )

    async def _fetch_web_pixel(
        self,
        *,
        access_token: str,
        shop_domain: str,
    ) -> dict[str, Any] | None:
        payload = await self._graphql(
            access_token=access_token,
            query="query { webPixel { id settings } }",
            shop_domain=shop_domain,
            variables={},
        )
        data = payload.get("data", {})
        web_pixel = data.get("webPixel")
        return web_pixel if isinstance(web_pixel, dict) else None

    async def _mutate_web_pixel(
        self,
        *,
        access_token: str,
        mutation_name: str,
        query: str,
        shop_domain: str,
        variables: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = await self._graphql(
            access_token=access_token,
            query=query,
            shop_domain=shop_domain,
            variables=variables,
        )
        mutation_payload = payload.get("data", {}).get(mutation_name, {})
        user_errors = mutation_payload.get("userErrors") or []
        if user_errors:
            messages = ", ".join(str(error.get("message", "Unknown error")) for error in user_errors)
            raise ShopifyWebPixelSetupError(f"Shopify web pixel setup failed: {messages}")
        web_pixel = mutation_payload.get("webPixel")
        return web_pixel if isinstance(web_pixel, dict) else None

    async def _graphql(
        self,
        *,
        access_token: str,
        query: str,
        shop_domain: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient(timeout=20.0)
        should_close = self._http_client is None
        try:
            response = await client.post(
                f"https://{shop_domain}/admin/api/latest/graphql.json",
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": access_token,
                },
                json={
                    "query": query,
                    "variables": variables,
                },
            )
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors")
            if errors:
                raise ShopifyWebPixelSetupError(f"Shopify web pixel setup failed: {errors}")
            return payload
        finally:
            if should_close:
                await client.aclose()
