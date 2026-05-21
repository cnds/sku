from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from schemas import (
    InternalCardReviewResponse,
    OnboardingStatusResponse,
    RecommendationFeedbackRequest,
    RecommendationFeedbackResponse,
    TimeWindow,
)
from services.card_review import InternalCardReviewService
from services.feedback import RecommendationFeedbackService
from services.onboarding import OnboardingStatusService

router = APIRouter()
WINDOW_QUERY = Query()


@router.get("/api/onboarding/status")
async def get_onboarding_status(
    request: Request,
    shop_id: str,
    window: Annotated[TimeWindow, WINDOW_QUERY] = TimeWindow.HOURS_24,
) -> OnboardingStatusResponse:
    return await OnboardingStatusService(request.app.state.settings).get_status(
        shop_id=shop_id,
        window=window,
    )


@router.post(
    "/api/recommendation-feedback",
    status_code=status.HTTP_201_CREATED,
)
async def post_recommendation_feedback(
    payload: RecommendationFeedbackRequest,
) -> RecommendationFeedbackResponse:
    return await RecommendationFeedbackService().record_feedback(payload)


@router.get("/api/internal/card-review")
async def get_internal_card_review(
    request: Request,
    shop_id: str,
    window: Annotated[TimeWindow, WINDOW_QUERY] = TimeWindow.HOURS_24,
) -> InternalCardReviewResponse:
    if not request.app.state.settings.sku_lens_internal_review:
        raise HTTPException(status_code=404, detail="Not found.")
    return await InternalCardReviewService().get_review(
        shop_id=shop_id,
        window=window,
    )
