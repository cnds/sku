from __future__ import annotations

from datetime import date

from db import get_db_session
from models import RawEvent
from schemas import IngestEvent
from services.job_dispatch import AfterCommitCallbacks, JobDispatchService
from services.rollups import DailyRollupService


class EventIngestionService:
    async def persist_batch(
        self,
        *,
        channel: str,
        events: list[IngestEvent],
        session_id: str,
        shop_domain: str,
        shop_id: str,
        visitor_id: str,
    ) -> None:
        raw_events = [
            RawEvent(
                channel=channel,
                component_id=event.component_id,
                context_json=event.context,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                product_id=event.product_id,
                session_id=session_id,
                shop_domain=shop_domain,
                shop_id=shop_id,
                variant_id=event.variant_id,
                visitor_id=visitor_id,
            )
            for event in events
        ]

        get_db_session().add_all(raw_events)

    async def persist_batch_and_rollup(
        self,
        *,
        channel: str,
        events: list[IngestEvent],
        session_id: str,
        shop_domain: str,
        shop_id: str,
        stat_date: date,
        visitor_id: str,
    ) -> None:
        await self.persist_batch(
            channel=channel,
            events=events,
            session_id=session_id,
            shop_domain=shop_domain,
            shop_id=shop_id,
            visitor_id=visitor_id,
        )
        await DailyRollupService().rollup_day(
            shop_id=shop_id,
            stat_date=stat_date,
        )

    async def persist_batch_rollup_and_enqueue(
        self,
        *,
        after_commit_callbacks: AfterCommitCallbacks,
        channel: str,
        events: list[IngestEvent],
        session_id: str,
        shop_domain: str,
        shop_id: str,
        stat_date: date,
        visitor_id: str,
    ) -> None:
        await self.persist_batch_and_rollup(
            channel=channel,
            events=events,
            session_id=session_id,
            shop_domain=shop_domain,
            shop_id=shop_id,
            stat_date=stat_date,
            visitor_id=visitor_id,
        )
        JobDispatchService().enqueue_rollup(
            after_commit_callbacks=after_commit_callbacks,
            shop_id=shop_id,
            stat_date=stat_date,
        )
