from __future__ import annotations

from datetime import date

import pytest

from db import create_session_factory, db_session_context, init_db
from models import DailyProductStat
from repositories.analytics import AnalyticsRepository
from schemas import LeaderboardType, TimeWindow


@pytest.mark.asyncio
async def test_leaderboard_query_returns_expected_black_and_red_rankings(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-underperformer",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=4,
                    orders=1,
                    component_clicks_distribution={"size_chart": 1},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-benchmark",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=15,
                    orders=8,
                    component_clicks_distribution={"size_chart": 8},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-hidden-gem",
                    stat_date=date(2026, 4, 23),
                    views=10,
                    add_to_carts=5,
                    orders=1,
                    component_clicks_distribution={"size_chart": 2},
                ),
            ],
        )
        await session.commit()

    repository = AnalyticsRepository()

    async with db_session_context(session_factory):
        black = await repository.fetch_leaderboard(
            shop_id="shop-1",
            board=LeaderboardType.BLACK,
            window=TimeWindow.DAYS_7,
        )
        red = await repository.fetch_leaderboard(
            shop_id="shop-1",
            board=LeaderboardType.RED,
            window=TimeWindow.DAYS_7,
        )

    assert black[0].product_id == "product-underperformer"
    assert round(black[0].score, 2) == 3.76
    assert red[0].product_id == "product-hidden-gem"
    assert red[0].score > red[1].score
