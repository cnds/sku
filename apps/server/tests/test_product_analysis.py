from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from db import create_session_factory, db_session_context, init_db
from models import DailyProductStat, ShopInstallation
from schemas import (
    LeaderboardEntry,
    LeaderboardType,
    PriorityBoardType,
    PrioritySignalState,
    PriorityTrendState,
    ProductSnapshot,
    TimeWindow,
)
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

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
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
        component for component in analysis.component_comparisons if component.component_id == "size_chart"
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

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        leaderboard = await analysis_service.get_leaderboard(
            shop_id="shop-1",
            board=LeaderboardType.BLACK,
            window=TimeWindow.DAYS_7,
        )

    assert leaderboard[0].product_id == "product-underperformer"
    assert round(leaderboard[0].score, 2) == 3.76


@pytest.mark.asyncio
async def test_product_priorities_returns_two_leakers_and_one_hidden_winner(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="leaker-size-confidence",
                    stat_date=date(2026, 4, 23),
                    views=120,
                    add_to_carts=8,
                    orders=1,
                    impressions=240,
                    clicks=44,
                    media_interactions=12,
                    variant_changes=9,
                    component_clicks_distribution={"size_chart": 1, "review_tab": 3},
                    component_impressions_distribution={"size_chart": 70, "review_tab": 52},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="leaker-media-trust",
                    stat_date=date(2026, 4, 23),
                    views=100,
                    add_to_carts=10,
                    orders=2,
                    impressions=210,
                    clicks=39,
                    media_interactions=1,
                    variant_changes=5,
                    component_clicks_distribution={"product_media": 1, "review_tab": 1},
                    component_impressions_distribution={"product_media": 85, "review_tab": 64},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark-hero",
                    stat_date=date(2026, 4, 23),
                    views=120,
                    add_to_carts=24,
                    orders=16,
                    impressions=260,
                    clicks=58,
                    media_interactions=18,
                    variant_changes=12,
                    component_clicks_distribution={"size_chart": 10, "review_tab": 12},
                    component_impressions_distribution={"size_chart": 72, "review_tab": 66},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="hidden-winner",
                    stat_date=date(2026, 4, 23),
                    views=38,
                    add_to_carts=14,
                    orders=7,
                    impressions=62,
                    clicks=30,
                    media_interactions=8,
                    variant_changes=6,
                    component_clicks_distribution={"review_tab": 7, "size_chart": 5},
                    component_impressions_distribution={"review_tab": 30, "size_chart": 26},
                ),
            ],
        )
        await session.commit()

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        priorities = await analysis_service.get_product_priorities(
            shop_id="shop-1",
            window=TimeWindow.DAYS_7,
        )

    assert [priority.product_id for priority in priorities] == [
        "leaker-size-confidence",
        "leaker-media-trust",
        "hidden-winner",
    ]
    assert [priority.board for priority in priorities] == [
        PriorityBoardType.LEAKER,
        PriorityBoardType.LEAKER,
        PriorityBoardType.HIDDEN_WINNER,
    ]
    assert all(priority.signal_state is PrioritySignalState.READY for priority in priorities)
    assert priorities[0].trend_state is PriorityTrendState.NEW
    assert priorities[0].trend_reason == "No previous 7d comparison window yet."
    assert priorities[0].primary_step == "pdp_add_to_cart"
    assert [priority.card_rank for priority in priorities] == [1, 2, 3]
    assert all(priority.board_date == date(2026, 4, 29) for priority in priorities)
    assert all(priority.window_start_date == date(2026, 4, 22) for priority in priorities)
    assert all(priority.window_end_date == date(2026, 4, 29) for priority in priorities)
    assert "size_chart" in priorities[0].suspected_friction
    assert priorities[2].flag_reason == "High intent, underexposed"


@pytest.mark.asyncio
async def test_product_priorities_gracefully_returns_fewer_than_three_cards(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add(
            DailyProductStat(
                shop_id="shop-1",
                product_id="only-leaker",
                stat_date=date(2026, 4, 23),
                views=100,
                add_to_carts=5,
                orders=1,
                impressions=160,
                clicks=35,
                component_clicks_distribution={"size_chart": 1},
                component_impressions_distribution={"size_chart": 60},
            )
        )
        await session.commit()

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        priorities = await analysis_service.get_product_priorities(
            shop_id="shop-1",
            window=TimeWindow.DAYS_7,
        )

    assert [priority.product_id for priority in priorities] == ["only-leaker"]
    assert priorities[0].board is PriorityBoardType.LEAKER


def test_priority_signal_state_derives_tracking_and_volume_quality() -> None:
    service = ProductAnalysisService()

    assert (
        service.derive_priority_signal_state(
            ProductSnapshot(views=80, add_to_carts=5, orders=1),
        )
        is PrioritySignalState.TRACKING_ISSUE
    )
    assert (
        service.derive_priority_signal_state(
            ProductSnapshot(views=6, add_to_carts=1, orders=0, impressions=20, clicks=4),
        )
        is PrioritySignalState.INSUFFICIENT_DATA
    )
    assert (
        service.derive_priority_signal_state(
            ProductSnapshot(views=22, add_to_carts=2, orders=0, impressions=50, clicks=8),
        )
        is PrioritySignalState.WEAK_SIGNAL
    )
    assert (
        service.derive_priority_signal_state(
            ProductSnapshot(views=80, add_to_carts=10, orders=3, impressions=120, clicks=30),
        )
        is PrioritySignalState.READY
    )


@pytest.mark.asyncio
async def test_product_priorities_marks_leaker_trend_when_gap_worsens(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="leaker",
                    stat_date=date(2026, 4, 28),
                    views=100,
                    add_to_carts=5,
                    orders=0,
                    impressions=180,
                    clicks=40,
                    component_clicks_distribution={"size_chart": 1},
                    component_impressions_distribution={"size_chart": 60},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark",
                    stat_date=date(2026, 4, 28),
                    views=100,
                    add_to_carts=20,
                    orders=10,
                    impressions=180,
                    clicks=48,
                    component_clicks_distribution={"size_chart": 10},
                    component_impressions_distribution={"size_chart": 60},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="leaker",
                    stat_date=date(2026, 4, 27),
                    views=100,
                    add_to_carts=10,
                    orders=6,
                    impressions=180,
                    clicks=40,
                    component_clicks_distribution={"size_chart": 5},
                    component_impressions_distribution={"size_chart": 60},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark",
                    stat_date=date(2026, 4, 27),
                    views=100,
                    add_to_carts=20,
                    orders=10,
                    impressions=180,
                    clicks=48,
                    component_clicks_distribution={"size_chart": 10},
                    component_impressions_distribution={"size_chart": 60},
                ),
            ]
        )
        await session.commit()

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        priorities = await analysis_service.get_product_priorities(
            shop_id="shop-1",
            window=TimeWindow.HOURS_24,
        )

    leaker = next(priority for priority in priorities if priority.product_id == "leaker")
    assert leaker.trend_state is PriorityTrendState.WORSENING
    assert leaker.trend_reason == "Leaker gap is up versus the previous 24h window."


@pytest.mark.asyncio
async def test_product_priorities_marks_leaker_trend_when_gap_improves(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="leaker",
                    stat_date=date(2026, 4, 28),
                    views=100,
                    add_to_carts=14,
                    orders=8,
                    impressions=180,
                    clicks=40,
                    component_clicks_distribution={"size_chart": 6},
                    component_impressions_distribution={"size_chart": 60},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark",
                    stat_date=date(2026, 4, 28),
                    views=100,
                    add_to_carts=20,
                    orders=10,
                    impressions=180,
                    clicks=48,
                    component_clicks_distribution={"size_chart": 10},
                    component_impressions_distribution={"size_chart": 60},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="leaker",
                    stat_date=date(2026, 4, 27),
                    views=100,
                    add_to_carts=5,
                    orders=0,
                    impressions=180,
                    clicks=40,
                    component_clicks_distribution={"size_chart": 1},
                    component_impressions_distribution={"size_chart": 60},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark",
                    stat_date=date(2026, 4, 27),
                    views=100,
                    add_to_carts=20,
                    orders=10,
                    impressions=180,
                    clicks=48,
                    component_clicks_distribution={"size_chart": 10},
                    component_impressions_distribution={"size_chart": 60},
                ),
            ]
        )
        await session.commit()

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        priorities = await analysis_service.get_product_priorities(
            shop_id="shop-1",
            window=TimeWindow.HOURS_24,
        )

    leaker = next(priority for priority in priorities if priority.product_id == "leaker")
    assert leaker.trend_state is PriorityTrendState.IMPROVING
    assert leaker.trend_reason == "Leaker gap is down versus the previous 24h window."


@pytest.mark.asyncio
async def test_product_priorities_marks_hidden_winner_opportunity_gap_growth(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with session_factory() as session:
        session.add_all(
            [
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="steady-leaker",
                    stat_date=date(2026, 4, 28),
                    views=100,
                    add_to_carts=6,
                    orders=1,
                    impressions=180,
                    clicks=36,
                    component_clicks_distribution={"size_chart": 1},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="hidden-winner",
                    stat_date=date(2026, 4, 28),
                    views=10,
                    add_to_carts=8,
                    orders=4,
                    impressions=30,
                    clicks=16,
                    component_clicks_distribution={"review_tab": 5},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark",
                    stat_date=date(2026, 4, 28),
                    views=140,
                    add_to_carts=18,
                    orders=8,
                    impressions=220,
                    clicks=60,
                    component_clicks_distribution={"review_tab": 8},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="hidden-winner",
                    stat_date=date(2026, 4, 27),
                    views=40,
                    add_to_carts=12,
                    orders=6,
                    impressions=80,
                    clicks=24,
                    component_clicks_distribution={"review_tab": 6},
                ),
                DailyProductStat(
                    shop_id="shop-1",
                    product_id="benchmark",
                    stat_date=date(2026, 4, 27),
                    views=100,
                    add_to_carts=12,
                    orders=5,
                    impressions=180,
                    clicks=42,
                    component_clicks_distribution={"review_tab": 5},
                ),
            ]
        )
        await session.commit()

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
    async with db_session_context(session_factory):
        priorities = await analysis_service.get_product_priorities(
            shop_id="shop-1",
            window=TimeWindow.HOURS_24,
        )

    hidden_winner = next(priority for priority in priorities if priority.product_id == "hidden-winner")
    assert hidden_winner.trend_state is PriorityTrendState.WORSENING
    assert hidden_winner.trend_reason == "Opportunity gap is growing versus the previous 24h window."


def test_low_data_priority_copy_avoids_confident_friction_claims() -> None:
    service = ProductAnalysisService()
    card = service._priority_card(
        board=PriorityBoardType.LEAKER,
        board_date=date(2026, 5, 27),
        card_rank=1,
        entry=LeaderboardEntry(
            product_id="product-1",
            views=4,
            add_to_carts=0,
            orders=0,
            impressions=12,
            clicks=2,
            score=0.0,
        ),
        snapshot=ProductSnapshot(
            views=4,
            add_to_carts=0,
            orders=0,
            impressions=12,
            clicks=2,
        ),
        previous_entry=None,
        window=TimeWindow.HOURS_24,
        window_end_date=date(2026, 5, 27),
        window_start_date=date(2026, 5, 26),
    )

    assert card.signal_state is PrioritySignalState.INSUFFICIENT_DATA
    assert card.flag_reason == "Not enough sessions to call a Winner or Leaker"
    assert "friction" not in card.suspected_friction.lower()
    assert "PDP sessions" in card.suspected_friction
    assert "traffic test" in card.first_fix


def test_hidden_winner_priority_copy_matches_roadmap_framing() -> None:
    service = ProductAnalysisService()
    card = service._priority_card(
        board=PriorityBoardType.HIDDEN_WINNER,
        board_date=date(2026, 5, 27),
        card_rank=1,
        entry=LeaderboardEntry(
            product_id="product-1",
            views=80,
            add_to_carts=12,
            orders=6,
            impressions=20,
            clicks=4,
            score=10.0,
        ),
        snapshot=ProductSnapshot(
            views=80,
            add_to_carts=12,
            orders=6,
            impressions=20,
            clicks=4,
        ),
        previous_entry=None,
        window=TimeWindow.HOURS_24,
        window_end_date=date(2026, 5, 27),
        window_start_date=date(2026, 5, 26),
    )

    assert card.signal_state is PrioritySignalState.READY
    assert card.flag_reason == "High intent, underexposed"


def test_tracking_issue_priority_copy_points_to_event_coverage() -> None:
    service = ProductAnalysisService()
    card = service._priority_card(
        board=PriorityBoardType.LEAKER,
        board_date=date(2026, 5, 27),
        card_rank=1,
        entry=LeaderboardEntry(
            product_id="product-1",
            views=80,
            add_to_carts=4,
            orders=1,
            impressions=0,
            clicks=0,
            score=2.0,
        ),
        snapshot=ProductSnapshot(
            views=80,
            add_to_carts=4,
            orders=1,
        ),
        previous_entry=None,
        window=TimeWindow.HOURS_24,
        window_end_date=date(2026, 5, 27),
        window_start_date=date(2026, 5, 26),
    )

    assert card.signal_state is PrioritySignalState.TRACKING_ISSUE
    assert "event coverage" in card.suspected_friction
    assert "before changing product content" in card.first_fix


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

    analysis_service = ProductAnalysisService(
        time_provider=lambda: datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
    )
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
