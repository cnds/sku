from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from schemas import (
    BillingCancelRequest,
    BillingStatusResponse,
    BillingSubscribeRequest,
    BillingSubscribeResponse,
)
from services.billing import BillingService
from services.shopify import build_onboarding_url, normalize_shop_domain

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/billing/status")
async def get_billing_status(
    request: Request,
    shop_id: str,
) -> BillingStatusResponse:
    return await BillingService(request.app.state.settings).get_status(shop_id=shop_id)


@router.post("/api/billing/subscribe")
async def post_billing_subscribe(
    payload: BillingSubscribeRequest,
    request: Request,
) -> BillingSubscribeResponse:
    return await BillingService(request.app.state.settings).subscribe(
        billing_interval=payload.billing_interval,
        plan=payload.plan,
        shop_id=payload.shop_id,
    )


@router.post("/api/billing/change-plan")
async def post_billing_change_plan(
    payload: BillingSubscribeRequest,
    request: Request,
) -> BillingSubscribeResponse:
    return await BillingService(request.app.state.settings).subscribe(
        billing_interval=payload.billing_interval,
        plan=payload.plan,
        shop_id=payload.shop_id,
    )


@router.post("/api/billing/cancel")
async def post_billing_cancel(
    payload: BillingCancelRequest,
    request: Request,
) -> BillingStatusResponse:
    service = BillingService(request.app.state.settings)
    await service.cancel(
        prorate=payload.prorate,
        shop_id=payload.shop_id,
    )
    return await service.get_status(shop_id=payload.shop_id)


@router.get("/shopify/billing/callback")
async def shopify_billing_callback(shop: str, request: Request) -> RedirectResponse:
    shop_domain = normalize_shop_domain(shop)
    await BillingService(request.app.state.settings).sync_from_shopify(shop_id=shop_domain)
    LOGGER.info("shopify billing callback synced shop_domain=%s", shop_domain)
    return RedirectResponse(
        build_onboarding_url(
            settings=request.app.state.settings,
            shop_domain=shop_domain,
        ).replace("/onboarding?", "/?"),
        status_code=307,
    )
