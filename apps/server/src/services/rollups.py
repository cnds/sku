from __future__ import annotations

from datetime import date

from sqlalchemy import case, delete, func, select
from sqlmodel import select as sqlmodel_select

from db import get_db_session
from models import DailyProductStat, EventType, RawEvent
from services.shop_time import utc_bounds_for_shop_date


def _build_component_index(rows: list) -> dict[str, dict[str, int]]:
    index: dict[str, dict[str, int]] = {}
    for row in rows:
        if row.component_id is None:
            continue
        product_components = index.setdefault(row.product_id, {})
        product_components[row.component_id] = int(row.cnt or 0)
    return index


class DailyRollupService:
    async def rollup_day(
        self,
        *,
        shop_id: str,
        stat_date: date,
        timezone_name: str | None = None,
    ) -> None:
        day_start, day_end = utc_bounds_for_shop_date(
            local_date=stat_date,
            timezone_name=timezone_name,
        )
        session = get_db_session()

        day_filter = [
            RawEvent.shop_id == shop_id,
            RawEvent.occurred_at >= day_start,
            RawEvent.occurred_at < day_end,
            RawEvent.product_id.is_not(None),
        ]

        metrics_statement = (
            select(
                RawEvent.product_id.label("product_id"),
                func.sum(case((RawEvent.event_type == EventType.VIEW, 1), else_=0)).label("views"),
                func.sum(
                    case((RawEvent.event_type == EventType.ADD_TO_CART, 1), else_=0)
                ).label("add_to_carts"),
                func.sum(case((RawEvent.event_type == EventType.ORDER, 1), else_=0)).label(
                    "orders"
                ),
                func.sum(
                    case((RawEvent.event_type == EventType.IMPRESSION, 1), else_=0)
                ).label("impressions"),
                func.sum(case((RawEvent.event_type == EventType.CLICK, 1), else_=0)).label(
                    "clicks"
                ),
                func.sum(case((RawEvent.event_type == EventType.MEDIA, 1), else_=0)).label(
                    "media_interactions"
                ),
                func.sum(case((RawEvent.event_type == EventType.VARIANT, 1), else_=0)).label(
                    "variant_changes"
                ),
                func.sum(case((RawEvent.event_type == EventType.ENGAGE, 1), else_=0)).label(
                    "engage_count"
                ),
            )
            .where(*day_filter)
            .group_by(RawEvent.product_id)
        )

        clicks_statement = (
            select(
                RawEvent.product_id,
                RawEvent.component_id,
                func.count().label("cnt"),
            )
            .where(
                *day_filter,
                RawEvent.event_type.in_([EventType.COMPONENT_CLICK, EventType.CLICK]),
                RawEvent.component_id.is_not(None),
            )
            .group_by(RawEvent.product_id, RawEvent.component_id)
        )

        impressions_statement = (
            select(
                RawEvent.product_id,
                RawEvent.component_id,
                func.count().label("cnt"),
            )
            .where(
                *day_filter,
                RawEvent.event_type == EventType.IMPRESSION,
                RawEvent.component_id.is_not(None),
            )
            .group_by(RawEvent.product_id, RawEvent.component_id)
        )

        engage_statement = (
            sqlmodel_select(RawEvent)
            .where(*day_filter, RawEvent.event_type == EventType.ENGAGE)
        )

        metrics_rows = (await session.exec(metrics_statement)).all()
        click_rows = (await session.exec(clicks_statement)).all()
        impression_rows = (await session.exec(impressions_statement)).all()
        engage_events = (await session.exec(engage_statement)).all()

        click_index = _build_component_index(click_rows)
        impression_index = _build_component_index(impression_rows)

        engage_index: dict[str, tuple[int, int, int]] = {}
        for evt in engage_events:
            dwell = int(evt.context_json.get("dwell_ms", 0))
            scroll = int(evt.context_json.get("max_scroll_pct", 0))
            cur = engage_index.get(evt.product_id, (0, 0, 0))
            engage_index[evt.product_id] = (cur[0] + dwell, cur[1] + scroll, cur[2] + 1)

        await session.exec(
            delete(DailyProductStat).where(
                DailyProductStat.shop_id == shop_id,
                DailyProductStat.stat_date == stat_date,
            )
        )

        session.add_all(
            [
                DailyProductStat(
                    shop_id=shop_id,
                    product_id=row.product_id,
                    stat_date=stat_date,
                    views=int(row.views or 0),
                    add_to_carts=int(row.add_to_carts or 0),
                    orders=int(row.orders or 0),
                    impressions=int(row.impressions or 0),
                    clicks=int(row.clicks or 0),
                    media_interactions=int(row.media_interactions or 0),
                    variant_changes=int(row.variant_changes or 0),
                    engage_count=int(row.engage_count or 0),
                    total_dwell_ms=engage_index.get(row.product_id, (0, 0, 0))[0],
                    avg_scroll_pct=(
                        round(eng[1] / eng[2]) if (eng := engage_index.get(row.product_id)) and eng[2] else 0
                    ),
                    component_clicks_distribution=click_index.get(row.product_id, {}),
                    component_impressions_distribution=impression_index.get(
                        row.product_id, {}
                    ),
                )
                for row in metrics_rows
            ]
        )
