from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

from schemas import ShopifyOAuthCallbackResponse, ShopifyWebhookAcceptedResponse
from security.shopify import shopify_hmac_required
from services.ingestion import EventIngestionService
from services.shop_installations import ShopInstallationService
from services.shopify import (
    SHOPIFY_OAUTH_STATE_COOKIE,
    MissingShopifyOAuthCodeError,
    ShopifyInstallationCallbackService,
    ShopifyOrderWebhookService,
    build_oauth_authorization_url,
    build_onboarding_url,
    new_oauth_state,
    normalize_shop_domain,
    verify_oauth_state,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/shopify/oauth/start")
async def shopify_oauth_start(shop: str, request: Request) -> RedirectResponse:
    shop_domain = normalize_shop_domain(shop)
    state_token = new_oauth_state()
    redirect = RedirectResponse(
        build_oauth_authorization_url(
            settings=request.app.state.settings,
            shop_domain=shop_domain,
            state=state_token,
        ),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    redirect.set_cookie(
        SHOPIFY_OAUTH_STATE_COOKIE,
        state_token,
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return redirect


@router.get("/shopify/oauth/callback")
async def shopify_oauth_callback_browser(
    shop: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    shop_domain = normalize_shop_domain(shop)
    if not code:
        raise MissingShopifyOAuthCodeError()
    verify_oauth_state(
        cookie_state=request.cookies.get(SHOPIFY_OAUTH_STATE_COOKIE),
        returned_state=state,
    )
    installation = await ShopifyInstallationCallbackService(
        request.app.state.settings
    ).complete_installation(
        shop_domain=shop_domain,
        code=code,
        callback_params=dict(request.query_params),
    )
    LOGGER.info(
        "shopify browser oauth completed shop_domain=%s",
        installation.shop_domain,
    )
    redirect = RedirectResponse(
        build_onboarding_url(
            settings=request.app.state.settings,
            shop_domain=installation.shop_domain,
            host=request.query_params.get("host"),
        ),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    redirect.delete_cookie(SHOPIFY_OAUTH_STATE_COOKIE)
    return redirect


@router.post("/shopify/oauth/callback")
async def shopify_oauth_callback(
    shop: str,
    request: Request,
    code: str | None = None,
) -> ShopifyOAuthCallbackResponse:
    installation = await ShopifyInstallationCallbackService(
        request.app.state.settings
    ).complete_installation(
        shop_domain=shop,
        code=code,
        callback_params=dict(request.query_params),
    )
    LOGGER.info(
        "shopify oauth completed shop_domain=%s",
        installation.shop_domain,
    )
    return ShopifyOAuthCallbackResponse(
        shop=installation.shop_domain,
        public_token=installation.public_token,
    )


@router.post("/shopify/webhooks/orders/create", status_code=status.HTTP_202_ACCEPTED)
@shopify_hmac_required(lambda request: request.app.state.settings.shopify_api_secret)
async def shopify_order_webhook(request: Request) -> ShopifyWebhookAcceptedResponse:
    payload = await request.json()
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "unknown.myshopify.com")
    installation = await ShopInstallationService().get_by_shop_domain(shop_domain)
    ingestion_batch = ShopifyOrderWebhookService().build_order_ingestion_batch(
        payload=payload,
        shop_domain=shop_domain,
        timezone_name=installation.timezone_name if installation is not None else None,
    )

    if ingestion_batch.events:
        await EventIngestionService().persist_batch_rollup_and_enqueue(
            after_commit_callbacks=request.state.after_commit_callbacks,
            channel="webhook",
            events=ingestion_batch.events,
            session_id=ingestion_batch.session_id,
            shop_domain=ingestion_batch.shop_domain,
            stat_date=ingestion_batch.stat_date,
            shop_id=ingestion_batch.shop_id,
            timezone_name=installation.timezone_name if installation is not None else None,
            visitor_id=ingestion_batch.visitor_id,
        )

    LOGGER.info(
        "shopify webhook accepted channel=%s enqueued=%s shop_domain=%s",
        "webhook",
        len(ingestion_batch.events),
        shop_domain,
    )
    return ShopifyWebhookAcceptedResponse(
        accepted=True,
        enqueued=len(ingestion_batch.events),
    )
