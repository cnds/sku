from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status

from schemas import ShopifyOAuthCallbackResponse, ShopifyWebhookAcceptedResponse
from security.shopify import shopify_hmac_required
from services.ingestion import EventIngestionService
from services.shop_installations import ShopInstallationService
from services.shopify import (
    ShopifyInstallationCallbackService,
    ShopifyOrderWebhookService,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


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
