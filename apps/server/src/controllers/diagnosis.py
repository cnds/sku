from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from schemas import DiagnosisResult, ProductSnapshot, TimeWindow
from services.diagnosis import ProductDiagnosisService
from services.job_dispatch import JobDispatchService

router = APIRouter()

WINDOW_QUERY = Query()


@router.post("/api/products/{product_id}/diagnosis")
async def trigger_product_diagnosis(
    product_id: str,
    request: Request,
    snapshot: ProductSnapshot,
    shop_id: str,
    window: Annotated[TimeWindow, WINDOW_QUERY] = TimeWindow.DAYS_7,
) -> DiagnosisResult:
    prepared = await ProductDiagnosisService().prepare_report(
        product_id=product_id,
        shop_id=shop_id,
        snapshot=snapshot,
        window=window,
    )
    if prepared.enqueue_request is not None:
        JobDispatchService().enqueue_diagnosis(
            after_commit_callbacks=request.state.after_commit_callbacks,
            product_id=prepared.enqueue_request.product_id,
            shop_id=prepared.enqueue_request.shop_id,
            snapshot=prepared.enqueue_request.snapshot,
            snapshot_hash=prepared.enqueue_request.snapshot_hash,
            window=prepared.enqueue_request.window,
        )
    return prepared.result


@router.get("/api/products/{product_id}/diagnosis")
async def get_product_diagnosis(
    product_id: str,
    shop_id: str,
    window: Annotated[TimeWindow, WINDOW_QUERY] = TimeWindow.DAYS_7,
) -> DiagnosisResult:
    return await ProductDiagnosisService().require_report(
        product_id=product_id,
        shop_id=shop_id,
        window=window,
    )
