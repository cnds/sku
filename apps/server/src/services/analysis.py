from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

from config import Settings
from repositories.analytics import AnalyticsRepository
from repositories.installations import InstallationRepository
from schemas import (
    ComponentComparison,
    FunnelComparison,
    FunnelSnapshot,
    LeaderboardEntry,
    LeaderboardType,
    ProductAnalysisResult,
    ProductSnapshot,
    TimeWindow,
)
from services.shop_time import ensure_utc_datetime, local_date_for_shop


class ProductAnalysisService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        installation_repository: InstallationRepository | None = None,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = AnalyticsRepository()
        self._installation_repository = installation_repository or InstallationRepository()
        self._time_provider = time_provider or (lambda: datetime.now(UTC))
        self._benchmark_min_views = (settings or Settings.model_construct()).benchmark_min_views

    async def get_product_analysis(
        self,
        *,
        product_id: str,
        shop_id: str,
        window: TimeWindow,
    ) -> ProductAnalysisResult:
        reference_date = await self._shop_reference_date(shop_id=shop_id)
        snapshots = await self._repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )
        benchmark_snapshots = await self._repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=TimeWindow.DAYS_30,
            reference_date=reference_date,
        )

        target = snapshots[product_id]
        benchmark_product_id, benchmark = self._select_benchmark(benchmark_snapshots)
        store_avg_cr = self._store_average_cr(snapshots)
        gap = (target.views * store_avg_cr) - target.orders

        component_ids = sorted(
            set(target.component_clicks_distribution) | set(benchmark.component_clicks_distribution)
        )
        component_comparisons = [
            ComponentComparison(
                component_id=component_id,
                target_clicks=target.component_clicks_distribution.get(component_id, 0),
                benchmark_clicks=benchmark.component_clicks_distribution.get(component_id, 0),
                target_ctr=self._ctr(
                    target.component_clicks_distribution.get(component_id, 0),
                    target.views,
                ),
                benchmark_ctr=self._ctr(
                    benchmark.component_clicks_distribution.get(component_id, 0),
                    benchmark.views,
                ),
                delta=self._ctr(
                    benchmark.component_clicks_distribution.get(component_id, 0),
                    benchmark.views,
                )
                - self._ctr(
                    target.component_clicks_distribution.get(component_id, 0),
                    target.views,
                ),
            )
            for component_id in component_ids
        ]

        return ProductAnalysisResult(
            product_id=product_id,
            benchmark_product_id=benchmark_product_id,
            gap=gap,
            funnel=FunnelComparison(
                target=FunnelSnapshot(
                    views=target.views,
                    add_to_carts=target.add_to_carts,
                    orders=target.orders,
                    impressions=target.impressions,
                    clicks=target.clicks,
                ),
                benchmark=FunnelSnapshot(
                    views=benchmark.views,
                    add_to_carts=benchmark.add_to_carts,
                    orders=benchmark.orders,
                    impressions=benchmark.impressions,
                    clicks=benchmark.clicks,
                ),
            ),
            component_comparisons=component_comparisons,
        )

    async def get_leaderboard(
        self,
        *,
        board: LeaderboardType,
        shop_id: str,
        window: TimeWindow,
    ) -> list[LeaderboardEntry]:
        reference_date = await self._shop_reference_date(shop_id=shop_id)
        return await self._repository.fetch_leaderboard(
            board=board,
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )

    async def _shop_reference_date(self, *, shop_id: str) -> date:
        installation = await self._installation_repository.get_by_shop_domain(shop_id)
        now_utc = ensure_utc_datetime(self._time_provider())
        return local_date_for_shop(
            instant=now_utc,
            timezone_name=installation.timezone_name if installation is not None else None,
        )

    def _select_benchmark(
        self,
        snapshots: dict[str, ProductSnapshot],
    ) -> tuple[str, ProductSnapshot]:
        candidates = [
            (product_id, snapshot)
            for product_id, snapshot in snapshots.items()
            if snapshot.views >= self._benchmark_min_views
        ]
        ranked = self._rank_benchmark_candidates(candidates)
        if not ranked:
            ranked = self._rank_benchmark_candidates(list(snapshots.items()))

        benchmark_count = max(1, round(len(ranked) * 0.2))
        benchmark_product_id, benchmark = ranked[:benchmark_count][0]
        return benchmark_product_id, benchmark

    @staticmethod
    def _rank_benchmark_candidates(
        candidates: list[tuple[str, ProductSnapshot]],
    ) -> list[tuple[str, ProductSnapshot]]:
        return sorted(
            candidates,
            key=lambda item: ProductAnalysisService._ctr(item[1].orders, item[1].views),
            reverse=True,
        )

    @staticmethod
    def _ctr(clicks: int, views: int) -> float:
        return 0.0 if views == 0 else clicks / views

    @staticmethod
    def _store_average_cr(snapshots: dict[str, ProductSnapshot]) -> float:
        total_views = sum(snapshot.views for snapshot in snapshots.values())
        total_orders = sum(snapshot.orders for snapshot in snapshots.values())
        return 0.0 if total_views == 0 else total_orders / total_views
