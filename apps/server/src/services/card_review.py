from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from db import get_db_session
from models import RawEvent
from repositories.diagnosis import DiagnosisRepository
from repositories.installations import InstallationRepository
from schemas import InternalCardReviewItem, InternalCardReviewResponse, PriorityCard, TimeWindow
from services.analysis import ProductAnalysisService
from services.shop_time import local_date_for_shop, utc_bounds_for_shop_date


class InternalCardReviewService:
    def __init__(
        self,
        *,
        analysis_service: ProductAnalysisService | None = None,
        diagnosis_repository: DiagnosisRepository | None = None,
        installation_repository: InstallationRepository | None = None,
    ) -> None:
        self._analysis_service = analysis_service or ProductAnalysisService()
        self._diagnosis_repository = diagnosis_repository or DiagnosisRepository()
        self._installation_repository = installation_repository or InstallationRepository()

    async def get_review(
        self,
        *,
        shop_id: str,
        window: TimeWindow,
    ) -> InternalCardReviewResponse:
        installation = await self._installation_repository.get_by_shop_domain(shop_id)
        timezone_name = installation.timezone_name if installation is not None else None
        cards = await self._analysis_service.get_product_priorities(
            shop_id=shop_id,
            window=window,
        )
        review_items = [
            await self._review_item(
                card=card,
                shop_id=shop_id,
                timezone_name=timezone_name,
                window=window,
            )
            for card in cards
        ]
        return InternalCardReviewResponse(
            shop_id=shop_id,
            window=window,
            cards=review_items,
        )

    async def _review_item(
        self,
        *,
        card: PriorityCard,
        shop_id: str,
        timezone_name: str | None,
        window: TimeWindow,
    ) -> InternalCardReviewItem:
        diagnosis = await self._diagnosis_repository.get_record(
            product_id=card.product_id,
            shop_id=shop_id,
            window=window,
        )
        return InternalCardReviewItem(
            priority_card=card,
            raw_event_counts=await self._raw_event_counts(
                product_id=card.product_id,
                shop_id=shop_id,
                timezone_name=timezone_name,
                window=window,
            ),
            aggregate_evidence={
                "views": card.views,
                "add_to_carts": card.add_to_carts,
                "orders": card.orders,
                "impressions": card.impressions,
                "clicks": card.clicks,
                "evidence": card.evidence,
            },
            derived_signal={
                "board": card.board,
                "primary_step": card.primary_step,
                "score": card.score,
                "signal_state": card.signal_state,
                "trend_reason": card.trend_reason,
                "trend_state": card.trend_state,
            },
            ai_summary=diagnosis.summary_json if diagnosis is not None else {},
            merchant_copy={
                "flag_reason": card.flag_reason,
                "suspected_friction": card.suspected_friction,
                "first_fix": card.first_fix,
            },
        )

    @staticmethod
    async def _raw_event_counts(
        *,
        product_id: str,
        shop_id: str,
        timezone_name: str | None,
        window: TimeWindow,
    ) -> dict[str, int]:
        reference_date = local_date_for_shop(
            instant=datetime.now(UTC),
            timezone_name=timezone_name,
        )
        start_date = window.start_date_from_reference_date(reference_date=reference_date)
        start_utc, _ = utc_bounds_for_shop_date(
            local_date=start_date,
            timezone_name=timezone_name,
        )
        statement = (
            select(RawEvent.event_type, func.count())
            .where(
                RawEvent.shop_id == shop_id,
                RawEvent.product_id == product_id,
                RawEvent.occurred_at >= start_utc,
            )
            .group_by(RawEvent.event_type)
        )
        rows = (await get_db_session().exec(statement)).all()
        return {str(row[0].value): int(row[1] or 0) for row in rows}
