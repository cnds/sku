from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, func, literal, select
from sqlalchemy.sql.selectable import Subquery
from sqlmodel import select as sqlmodel_select

from db import get_db_session
from models import DailyProductStat
from schemas import LeaderboardEntry, LeaderboardType, ProductSnapshot, TimeWindow


class AnalyticsRepository:
    async def fetch_leaderboard(
        self,
        *,
        board: LeaderboardType,
        shop_id: str,
        window: TimeWindow,
    ) -> list[LeaderboardEntry]:
        aggregated = self._aggregated_stats_subquery(shop_id=shop_id, window=window)
        store_avg_cr = (
            select(
                func.coalesce(func.sum(aggregated.c.orders), 0) * 1.0
                / func.nullif(func.coalesce(func.sum(aggregated.c.views), 0), 0)
            )
            .select_from(aggregated)
            .scalar_subquery()
        )
        store_avg_views = (
            select(func.avg(aggregated.c.views))
            .select_from(aggregated)
            .scalar_subquery()
        )

        gap_score = (
            aggregated.c.views * func.coalesce(store_avg_cr, literal(0.0)) - aggregated.c.orders
        )
        opportunity_score = (
            (
                aggregated.c.add_to_carts * 1.0
                / func.nullif(func.coalesce(aggregated.c.views, 0), 0)
            )
            * func.coalesce(store_avg_views, literal(0.0))
            - aggregated.c.views
        )
        score_column = gap_score if board is LeaderboardType.BLACK else opportunity_score

        statement = (
            select(
                aggregated.c.product_id,
                aggregated.c.views,
                aggregated.c.add_to_carts,
                aggregated.c.orders,
                aggregated.c.impressions,
                aggregated.c.clicks,
                score_column.label("score"),
            )
            .select_from(aggregated)
            .order_by(desc("score"), aggregated.c.product_id)
        )

        rows = (await get_db_session().exec(statement)).all()

        return [
            LeaderboardEntry(
                product_id=row.product_id,
                views=row.views or 0,
                add_to_carts=row.add_to_carts or 0,
                orders=row.orders or 0,
                impressions=row.impressions or 0,
                clicks=row.clicks or 0,
                score=float(row.score or 0.0),
            )
            for row in rows
        ]

    async def fetch_product_snapshots(
        self,
        *,
        shop_id: str,
        window: TimeWindow,
    ) -> dict[str, ProductSnapshot]:
        statement = (
            sqlmodel_select(DailyProductStat)
            .where(
                DailyProductStat.shop_id == shop_id,
                DailyProductStat.stat_date >= window.start_date(now=datetime.now(UTC)),
            )
        )

        rows = (await get_db_session().exec(statement)).all()

        aggregated: dict[str, ProductSnapshot] = {}
        for row in rows:
            current = aggregated.setdefault(
                row.product_id,
                ProductSnapshot(views=0, add_to_carts=0, orders=0),
            )
            current.views += row.views
            current.add_to_carts += row.add_to_carts
            current.orders += row.orders
            current.impressions += row.impressions
            current.clicks += row.clicks
            current.media_interactions += row.media_interactions
            current.variant_changes += row.variant_changes
            current.total_dwell_ms += row.total_dwell_ms
            current.engage_count += row.engage_count

            prev_engage = current.engage_count - row.engage_count
            if row.engage_count > 0:
                if prev_engage > 0:
                    current.avg_scroll_pct = round(
                        (current.avg_scroll_pct * prev_engage + row.avg_scroll_pct * row.engage_count)
                        / current.engage_count
                    )
                else:
                    current.avg_scroll_pct = row.avg_scroll_pct

            for component_id, count in row.component_clicks_distribution.items():
                current.component_clicks_distribution[component_id] = (
                    current.component_clicks_distribution.get(component_id, 0) + count
                )

            for component_id, count in row.component_impressions_distribution.items():
                current.component_impressions_distribution[component_id] = (
                    current.component_impressions_distribution.get(component_id, 0) + count
                )

        return aggregated

    def _aggregated_stats_subquery(self, *, shop_id: str, window: TimeWindow) -> Subquery:
        return (
            select(
                DailyProductStat.product_id.label("product_id"),
                func.sum(DailyProductStat.views).label("views"),
                func.sum(DailyProductStat.add_to_carts).label("add_to_carts"),
                func.sum(DailyProductStat.orders).label("orders"),
                func.sum(DailyProductStat.impressions).label("impressions"),
                func.sum(DailyProductStat.clicks).label("clicks"),
            )
            .where(
                DailyProductStat.shop_id == shop_id,
                DailyProductStat.stat_date
                >= window.start_date(now=datetime.now(UTC)),
            )
            .group_by(DailyProductStat.product_id)
            .subquery()
        )
