from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request, status

from schemas import IngestAcceptedResponse, IngestBatchRequest
from services.ingest_auth import IngestAuthService
from services.ingestion import EventIngestionService
from services.shop_time import local_date_for_shop

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/ingest/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    request: Request,
    payload: IngestBatchRequest,
    x_sku_lens_public_token: str = Header(alias="X-SKU-Lens-Public-Token"),
    x_sku_lens_timestamp: int = Header(alias="X-SKU-Lens-Timestamp"),
) -> IngestAcceptedResponse:
    installation = await IngestAuthService(request.app.state.settings).verify_public_token(
        shop_domain=payload.shop_domain,
        public_token=x_sku_lens_public_token,
        timestamp=x_sku_lens_timestamp,
    )
    if not payload.events:
        LOGGER.info(
            "ingest accepted accepted=%s channel=%s shop_domain=%s session_id=%s visitor_id=%s",
            0,
            "sdk",
            payload.shop_domain,
            payload.session_id,
            payload.visitor_id,
        )
        return IngestAcceptedResponse(accepted=0)

    await EventIngestionService().persist_batch_rollup_and_enqueue(
        after_commit_callbacks=request.state.after_commit_callbacks,
        channel="sdk",
        events=payload.events,
        session_id=payload.session_id,
        shop_domain=payload.shop_domain,
        stat_dates={
            local_date_for_shop(
                instant=event.occurred_at,
                timezone_name=installation.timezone_name,
            )
            for event in payload.events
        },
        shop_id=payload.shop_domain,
        timezone_name=installation.timezone_name,
        visitor_id=payload.visitor_id,
    )
    LOGGER.info(
        "ingest accepted accepted=%s channel=%s shop_domain=%s session_id=%s visitor_id=%s",
        len(payload.events),
        "sdk",
        payload.shop_domain,
        payload.session_id,
        payload.visitor_id,
    )
    return IngestAcceptedResponse(accepted=len(payload.events))
