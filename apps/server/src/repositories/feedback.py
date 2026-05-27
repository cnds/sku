from __future__ import annotations

from datetime import date

from sqlmodel import select

from db import get_db_session
from models import RecommendationFeedback, RecommendationFeedbackAction
from schemas import PriorityBoardType, TimeWindow


class RecommendationFeedbackRepository:
    async def append(
        self,
        *,
        action: RecommendationFeedbackAction,
        board: PriorityBoardType | None,
        board_date: date | None,
        card_rank: int | None,
        context: dict[str, object],
        product_id: str,
        shop_id: str,
        window: TimeWindow,
        window_end_date: date | None,
        window_start_date: date | None,
    ) -> RecommendationFeedback:
        feedback = RecommendationFeedback(
            action=action.value,
            board=board.value if board is not None else None,
            board_date=board_date,
            card_rank=card_rank,
            context_json=context,
            product_id=product_id,
            shop_id=shop_id,
            window=window.value,
            window_end_date=window_end_date,
            window_start_date=window_start_date,
        )
        get_db_session().add(feedback)
        return feedback

    async def latest(
        self,
        *,
        product_id: str,
        shop_id: str,
        window: TimeWindow,
    ) -> RecommendationFeedback | None:
        return (
            await get_db_session().exec(
                select(RecommendationFeedback)
                .where(
                    RecommendationFeedback.shop_id == shop_id,
                    RecommendationFeedback.product_id == product_id,
                    RecommendationFeedback.window == window.value,
                )
                .order_by(RecommendationFeedback.created_at.desc(), RecommendationFeedback.id.desc())
            )
        ).first()
