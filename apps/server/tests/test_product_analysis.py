from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from db import create_session_factory, db_session_context, init_db
from models import DailyProductStat, ShopInstallation
from schemas import LeaderboardType, TimeWindow
from services.analysis import ProductAnalysisService


@pytest.mark.asyncio
async def test_product_analysis_uses_top_twenty_percent_benchmark_and_component_deltas(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-target",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=12,
                    orders=4,
                    component_clicks_distribution={
                        "description": 6,
                        "review_tab": 2,
                        "size_chart": 1,
                    },
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-benchmark",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=22,
                    orders=18,
                    component_clicks_distribution={
                        "description": 18,
                        "review_tab": 10,
                        "size_chart": 8,
                    },
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-mid-1",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=15,
                    orders=7,
                    component_clicks_distribution={"size_chart": 4},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-mid-2",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=14,
                    orders=6,
                    component_clicks_distribution={"size_chart": 3},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-low-volume",
                    stat_date=date(2026, 4, 23),
                    views=20,
                    add_to_carts=10,
                    orders=5,
                    component_clicks_distribution={"size_chart": 3},
                ),
            ],
        )
        await session.commit()

    analysis_service = ProductAnalysisService()
    async with db_session_context(session_factory):
        analysis = await analysis_service.get_product_analysis(
            product_id="product-target",
            shop_id="shop-1",
            window=TimeWindow.DAYS_30,
        )

    assert analysis.benchmark_product_id == "product-benchmark"
    assert analysis.funnel.target.orders == 4
    assert analysis.funnel.benchmark.orders == 18
    size_chart_delta = next(
        component
        for component in analysis.component_comparisons
        if component.component_id == "size_chart"
    )
    assert round(size_chart_delta.target_ctr, 3) == 0.01
    assert round(size_chart_delta.benchmark_ctr, 3) == 0.08


@pytest.mark.asyncio
async def test_product_analysis_service_fetches_leaderboard_entries(
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

    analysis_service = ProductAnalysisService()
    async with db_session_context(session_factory):
        leaderboard = await analysis_service.get_leaderboard(
            shop_id="shop-1",
            board=LeaderboardType.BLACK,
            window=TimeWindow.DAYS_7,
        )

    assert leaderboard[0].product_id == "product-underperformer"
    assert round(leaderboard[0].score, 2) == 3.76


@pytest.mark.asyncio
async def test_product_analysis_falls_back_to_low_volume_products_when_threshold_has_no_candidates(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-target",
                    stat_date=date(2026, 4, 23),
                    views=20,
                    add_to_carts=4,
                    orders=1,
                    component_clicks_distribution={"size_chart": 1},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-benchmark",
                    stat_date=date(2026, 4, 23),
                    views=10,
                    add_to_carts=6,
                    orders=4,
                    component_clicks_distribution={"size_chart": 3},
                ),
            ],
        )
        await session.commit()

    analysis_service = ProductAnalysisService()
    async with db_session_context(session_factory):
        analysis = await analysis_service.get_product_analysis(
            product_id="product-target",
            shop_id="shop-1",
            window=TimeWindow.DAYS_30,
        )

    assert analysis.benchmark_product_id == "product-benchmark"
    assert analysis.funnel.target.orders == 1
    assert analysis.funnel.benchmark.orders == 4


@pytest.mark.asyncio
async def test_product_analysis_uses_shop_timezone_for_time_window_boundaries(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add(
            ShopInstallation(
                shop_domain="shop-1",
                public_token="public-1",
                timezone_name="Asia/Tokyo",
            )
        )
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-too-old",
                    stat_date=date(2026, 4, 21),
                    views=100,
                    add_to_carts=4,
                    orders=1,
                    component_clicks_distribution={"size_chart": 1},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="product-visible",
                    stat_date=date(2026, 4, 22),
                    views=100,
                    add_to_carts=15,
                    orders=8,
                    component_clicks_distribution={"size_chart": 8},
                ),
            ],
        )
        await session.commit()

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 28, 15, 5, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        leaderboard = await analysis_service.get_leaderboard(
            shop_id="shop-1",
            board=LeaderboardType.BLACK,
            window=TimeWindow.DAYS_7,
        )

    assert [entry.product_id for entry in leaderboard] == ["product-visible"]
