from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request, status

from schemas import IngestAcceptedResponse, IngestBatchRequest
from services.ingest_auth import IngestAuthService
from services.ingestion import EventIngestionService

router = APIRouter()


@router.post("/ingest/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    request: Request,
    payload: IngestBatchRequest,
    x_sku_lens_public_token: str = Header(alias="X-SKU-Lens-Public-Token"),
    x_sku_lens_timestamp: int = Header(alias="X-SKU-Lens-Timestamp"),
) -> IngestAcceptedResponse:
    await IngestAuthService(request.app.state.settings).verify_public_token(
        shop_domain=payload.shop_domain,
        public_token=x_sku_lens_public_token,
        timestamp=x_sku_lens_timestamp,
    )
    stat_date = datetime.now(UTC).date()
    await EventIngestionService().persist_batch_rollup_and_enqueue(
        after_commit_callbacks=request.state.after_commit_callbacks,
        channel="sdk",
        events=payload.events,
        session_id=payload.session_id,
        shop_domain=payload.shop_domain,
        stat_date=stat_date,
        shop_id=payload.shop_domain,
        visitor_id=payload.visitor_id,
    )
    return IngestAcceptedResponse(accepted=len(payload.events))
