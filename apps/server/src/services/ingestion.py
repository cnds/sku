from __future__ import annotations

from datetime import date

from sqlmodel import select

from db import get_db_session
from models import EventType, RawEvent
from schemas import IngestEvent, ShopifyPixelEvent
from services.job_dispatch import AfterCommitCallbacks, JobDispatchService
from services.rollups import DailyRollupService

SDK_DOM_EVENT_TYPES = frozenset(
    {
        EventType.PRODUCT_IMPRESSION,
        EventType.PRODUCT_CLICK,
        EventType.COMPONENT_IMPRESSION,
        EventType.COMPONENT_CLICK,
        EventType.MEDIA_INTERACTION,
        EventType.VARIANT_INTENT,
        EventType.ENGAGE,
    }
)

SHOPIFY_PIXEL_EVENT_TYPES = frozenset(
    {
        EventType.PAGE_VIEW,
        EventType.PRODUCT_VIEW,
        EventType.COLLECTION_VIEW,
        EventType.SEARCH_SUBMITTED,
        EventType.CART_VIEW,
        EventType.ADD_TO_CART,
        EventType.REMOVE_FROM_CART,
        EventType.CHECKOUT_STARTED,
        EventType.CHECKOUT_STEP,
        EventType.CHECKOUT_COMPLETED,
    }
)

SHOPIFY_PIXEL_EVENT_TYPE_BY_SOURCE = {
    "page_viewed": EventType.PAGE_VIEW,
    "product_viewed": EventType.PRODUCT_VIEW,
    "collection_viewed": EventType.COLLECTION_VIEW,
    "search_submitted": EventType.SEARCH_SUBMITTED,
    "cart_viewed": EventType.CART_VIEW,
    "product_added_to_cart": EventType.ADD_TO_CART,
    "product_removed_from_cart": EventType.REMOVE_FROM_CART,
    "checkout_started": EventType.CHECKOUT_STARTED,
    "checkout_contact_info_submitted": EventType.CHECKOUT_STEP,
    "checkout_address_info_submitted": EventType.CHECKOUT_STEP,
    "checkout_shipping_info_submitted": EventType.CHECKOUT_STEP,
    "payment_info_submitted": EventType.CHECKOUT_STEP,
    "checkout_completed": EventType.CHECKOUT_COMPLETED,
}


class UnsupportedShopifyPixelEventError(Exception):
    def __init__(self, source_event_name: str) -> None:
        super().__init__(f"Unsupported Shopify pixel event: {source_event_name}.")


class UnsupportedSdkDomEventError(Exception):
    def __init__(self, event_type: EventType) -> None:
        super().__init__(f"Unsupported SDK DOM event: {event_type.value}.")


class EventIngestionService:
    @staticmethod
    def validate_sdk_dom_events(events: list[IngestEvent]) -> None:
        for event in events:
            if event.event_type not in SDK_DOM_EVENT_TYPES:
                raise UnsupportedSdkDomEventError(event.event_type)

    @staticmethod
    def build_shopify_pixel_events(events: list[ShopifyPixelEvent]) -> list[IngestEvent]:
        return [
            IngestEvent(
                component_id=event.component_id,
                context={
                    **event.context,
                    "source_event_name": event.source_event_name,
                },
                dedupe_key=EventIngestionService._pixel_dedupe_key(event),
                event_id=event.event_id,
                event_type=EventIngestionService._pixel_event_type(event.source_event_name),
                occurred_at=event.occurred_at,
                product_id=event.product_id,
                source_event_name=event.source_event_name,
                variant_id=event.variant_id,
            )
            for event in events
        ]

    @staticmethod
    def _resolve_stat_dates(
        *,
        stat_date: date | None = None,
        stat_dates: set[date] | None = None,
    ) -> list[date]:
        resolved = set(stat_dates or set())
        if stat_date is not None:
            resolved.add(stat_date)
        if not resolved:
            raise ValueError("At least one stat date is required.")
        return sorted(resolved)

    @staticmethod
    def _pixel_event_type(source_event_name: str) -> EventType:
        event_type = SHOPIFY_PIXEL_EVENT_TYPE_BY_SOURCE.get(source_event_name)
        if event_type is None:
            raise UnsupportedShopifyPixelEventError(source_event_name)
        return event_type

    @staticmethod
    def _pixel_dedupe_key(event: ShopifyPixelEvent) -> str:
        if event.dedupe_key:
            return event.dedupe_key

        line_item_id = event.context.get("line_item_id")
        line_item_index = event.context.get("line_item_index")
        line_key = line_item_id if line_item_id is not None else line_item_index
        return "|".join(
            [
                event.source_event_name,
                event.event_id,
                event.product_id or "",
                event.variant_id or "",
                "" if line_key is None else str(line_key),
            ]
        )

    async def persist_batch(
        self,
        *,
        channel: str,
        events: list[IngestEvent],
        session_id: str,
        shop_domain: str,
        shop_id: str,
        visitor_id: str,
    ) -> int:
        session = get_db_session()
        existing_dedupe_keys: set[str] = set()
        dedupe_keys = {event.dedupe_key for event in events if event.dedupe_key is not None}
        if dedupe_keys:
            existing_raw_events = (
                await session.exec(
                    select(RawEvent).where(
                        RawEvent.shop_id == shop_id,
                        RawEvent.channel == channel,
                        RawEvent.dedupe_key.in_(dedupe_keys),
                    )
                )
            ).all()
            existing_dedupe_keys = {
                raw_event.dedupe_key for raw_event in existing_raw_events if raw_event.dedupe_key is not None
            }

        seen_dedupe_keys: set[str] = set()
        raw_events: list[RawEvent] = []
        for event in events:
            if event.dedupe_key is not None:
                if event.dedupe_key in existing_dedupe_keys or event.dedupe_key in seen_dedupe_keys:
                    continue
                seen_dedupe_keys.add(event.dedupe_key)

            raw_events.append(
                RawEvent(
                    channel=channel,
                    component_id=event.component_id,
                    context_json=event.context,
                    dedupe_key=event.dedupe_key,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    product_id=event.product_id,
                    session_id=session_id,
                    shop_domain=shop_domain,
                    shop_id=shop_id,
                    source_event_name=event.source_event_name,
                    variant_id=event.variant_id,
                    visitor_id=visitor_id,
                )
            )

        session.add_all(raw_events)
        return len(raw_events)

    async def persist_batch_and_rollup(
        self,
        *,
        channel: str,
        events: list[IngestEvent],
        session_id: str,
        shop_domain: str,
        shop_id: str,
        stat_date: date | None = None,
        stat_dates: set[date] | None = None,
        timezone_name: str | None = None,
        visitor_id: str,
    ) -> int:
        accepted = await self.persist_batch(
            channel=channel,
            events=events,
            session_id=session_id,
            shop_domain=shop_domain,
            shop_id=shop_id,
            visitor_id=visitor_id,
        )
        if accepted == 0:
            return accepted
        for resolved_stat_date in self._resolve_stat_dates(
            stat_date=stat_date,
            stat_dates=stat_dates,
        ):
            await DailyRollupService().rollup_day(
                shop_id=shop_id,
                stat_date=resolved_stat_date,
                timezone_name=timezone_name,
            )
        return accepted

    async def persist_batch_rollup_and_enqueue(
        self,
        *,
        after_commit_callbacks: AfterCommitCallbacks,
        channel: str,
        events: list[IngestEvent],
        session_id: str,
        shop_domain: str,
        shop_id: str,
        stat_date: date | None = None,
        stat_dates: set[date] | None = None,
        timezone_name: str | None = None,
        visitor_id: str,
    ) -> int:
        accepted = await self.persist_batch_and_rollup(
            channel=channel,
            events=events,
            session_id=session_id,
            shop_domain=shop_domain,
            shop_id=shop_id,
            stat_date=stat_date,
            stat_dates=stat_dates,
            timezone_name=timezone_name,
            visitor_id=visitor_id,
        )
        if accepted == 0:
            return accepted
        JobDispatchService().enqueue_rollups(
            after_commit_callbacks=after_commit_callbacks,
            shop_id=shop_id,
            stat_dates=self._resolve_stat_dates(
                stat_date=stat_date,
                stat_dates=stat_dates,
            ),
        )
        return accepted
