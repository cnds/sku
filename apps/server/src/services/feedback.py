from __future__ import annotations

from models import RecommendationFeedbackAction
from repositories.feedback import RecommendationFeedbackRepository
from schemas import RecommendationFeedbackRequest, RecommendationFeedbackResponse


class RecommendationFeedbackService:
    def __init__(
        self,
        repository: RecommendationFeedbackRepository | None = None,
    ) -> None:
        self._repository = repository or RecommendationFeedbackRepository()

    async def record_feedback(
        self,
        request: RecommendationFeedbackRequest,
    ) -> RecommendationFeedbackResponse:
        await self._repository.append(
            action=request.action,
            board=request.board,
            board_date=request.board_date,
            card_rank=request.card_rank,
            context=request.context,
            product_id=request.product_id,
            shop_id=request.shop_id,
            window=request.window,
            window_end_date=request.window_end_date,
            window_start_date=request.window_start_date,
        )
        latest = await self._repository.latest(
            product_id=request.product_id,
            shop_id=request.shop_id,
            window=request.window,
        )
        latest_action = (
            RecommendationFeedbackAction(latest.action)
            if latest is not None
            else request.action
        )
        return RecommendationFeedbackResponse(
            accepted=True,
            latest_action=latest_action,
            product_id=request.product_id,
            shop_id=request.shop_id,
            window=request.window,
        )
