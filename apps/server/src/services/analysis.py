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
    PriorityBoardType,
    PriorityCard,
    PrioritySignalState,
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
                target=self._funnel_snapshot(target),
                benchmark=self._funnel_snapshot(benchmark),
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

    async def get_product_priorities(
        self,
        *,
        shop_id: str,
        window: TimeWindow,
    ) -> list[PriorityCard]:
        reference_date = await self._shop_reference_date(shop_id=shop_id)
        snapshots = await self._repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )
        if not snapshots:
            return []

        leaker_entries = await self._repository.fetch_leaderboard(
            board=LeaderboardType.BLACK,
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )
        hidden_winner_entries = await self._repository.fetch_leaderboard(
            board=LeaderboardType.RED,
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )

        selected: list[PriorityCard] = []
        selected_product_ids: set[str] = set()

        for entry in self._positive_or_fallback_entries(leaker_entries, limit=2):
            if entry.product_id not in snapshots:
                continue
            selected.append(
                self._priority_card(
                    board=PriorityBoardType.LEAKER,
                    entry=entry,
                    snapshot=snapshots[entry.product_id],
                )
            )
            selected_product_ids.add(entry.product_id)
            if len(selected) == 2:
                break

        for entry in self._positive_or_fallback_entries(
            hidden_winner_entries,
            limit=len(hidden_winner_entries),
        ):
            if entry.product_id in selected_product_ids or entry.product_id not in snapshots:
                continue
            selected.append(
                self._priority_card(
                    board=PriorityBoardType.HIDDEN_WINNER,
                    entry=entry,
                    snapshot=snapshots[entry.product_id],
                )
            )
            break

        return selected[:3]

    async def _shop_reference_date(self, *, shop_id: str) -> date:
        installation = await self._installation_repository.get_by_shop_domain(shop_id)
        now_utc = ensure_utc_datetime(self._time_provider())
        return local_date_for_shop(
            instant=now_utc,
            timezone_name=installation.timezone_name if installation is not None else None,
        )

    @staticmethod
    def derive_priority_signal_state(snapshot: ProductSnapshot) -> PrioritySignalState:
        tracked_volume = snapshot.views + snapshot.impressions + snapshot.clicks
        tracked_volume += snapshot.add_to_carts + snapshot.orders
        if tracked_volume == 0 or snapshot.views < 10:
            return PrioritySignalState.INSUFFICIENT_DATA
        if snapshot.views > 0 and snapshot.impressions == 0 and snapshot.clicks == 0:
            return PrioritySignalState.TRACKING_ISSUE
        if snapshot.views < 30:
            return PrioritySignalState.WEAK_SIGNAL
        return PrioritySignalState.READY

    @staticmethod
    def _funnel_snapshot(snapshot: ProductSnapshot) -> FunnelSnapshot:
        return FunnelSnapshot(
            views=snapshot.views,
            add_to_carts=snapshot.add_to_carts,
            orders=snapshot.orders,
            impressions=snapshot.impressions,
            clicks=snapshot.clicks,
            media_interactions=snapshot.media_interactions,
            variant_changes=snapshot.variant_changes,
            total_dwell_ms=snapshot.total_dwell_ms,
            engage_count=snapshot.engage_count,
            avg_scroll_pct=snapshot.avg_scroll_pct,
            component_clicks_distribution=snapshot.component_clicks_distribution,
            component_impressions_distribution=snapshot.component_impressions_distribution,
        )

    @staticmethod
    def _positive_or_fallback_entries(
        entries: list[LeaderboardEntry],
        *,
        limit: int,
    ) -> list[LeaderboardEntry]:
        positive = [entry for entry in entries if entry.score > 0]
        return (positive or entries)[:limit]

    def _priority_card(
        self,
        *,
        board: PriorityBoardType,
        entry: LeaderboardEntry,
        snapshot: ProductSnapshot,
    ) -> PriorityCard:
        signal_state = self.derive_priority_signal_state(snapshot)
        primary_step = self._primary_step(board=board, signal_state=signal_state, snapshot=snapshot)
        return PriorityCard(
            product_id=entry.product_id,
            board=board,
            signal_state=signal_state,
            flag_reason=self._flag_reason(board=board, signal_state=signal_state),
            primary_step=primary_step,
            evidence=self._priority_evidence(snapshot=snapshot, signal_state=signal_state),
            suspected_friction=self._suspected_friction(
                board=board,
                signal_state=signal_state,
                snapshot=snapshot,
            ),
            first_fix=self._first_fix(board=board, signal_state=signal_state, snapshot=snapshot),
            views=snapshot.views,
            add_to_carts=snapshot.add_to_carts,
            orders=snapshot.orders,
            impressions=snapshot.impressions,
            clicks=snapshot.clicks,
            score=entry.score,
        )

    @classmethod
    def _primary_step(
        cls,
        *,
        board: PriorityBoardType,
        signal_state: PrioritySignalState,
        snapshot: ProductSnapshot,
    ) -> str:
        if signal_state is PrioritySignalState.TRACKING_ISSUE:
            return "tracking_coverage"
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return "data_volume"
        if board is PriorityBoardType.HIDDEN_WINNER:
            return "merchandising_reach"
        if cls._rate(snapshot.add_to_carts, snapshot.views) < 0.1:
            return "pdp_add_to_cart"
        if snapshot.add_to_carts > 0 and cls._rate(snapshot.orders, snapshot.add_to_carts) < 0.35:
            return "cart_to_order"
        if snapshot.impressions > 0 and cls._rate(snapshot.clicks, snapshot.impressions) < 0.15:
            return "collection_click"
        return "pdp_decision"

    @staticmethod
    def _flag_reason(
        *,
        board: PriorityBoardType,
        signal_state: PrioritySignalState,
    ) -> str:
        if signal_state is PrioritySignalState.TRACKING_ISSUE:
            return "Tracker coverage is incomplete"
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return "Not enough sessions to call a winner or leaker"
        if signal_state is PrioritySignalState.WEAK_SIGNAL:
            return "Early signal; validate with more traffic"
        if board is PriorityBoardType.HIDDEN_WINNER:
            return "Strong buying intent with limited traffic"
        return "Orders lag similar traffic"

    @classmethod
    def _priority_evidence(
        cls,
        *,
        snapshot: ProductSnapshot,
        signal_state: PrioritySignalState,
    ) -> list[str]:
        if signal_state is PrioritySignalState.TRACKING_ISSUE:
            return [
                f"{snapshot.views} PDP views",
                "Missing collection impression/click coverage",
                "Verify the theme app embed before acting on page content",
            ]
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return [
                f"{snapshot.views} PDP views",
                f"{snapshot.add_to_carts} add-to-carts",
                "Collect more sessions before changing merchandising",
            ]

        evidence = [
            f"{snapshot.views} PDP views",
            f"{snapshot.add_to_carts} add-to-carts ({cls._percent(snapshot.add_to_carts, snapshot.views)})",
            f"{snapshot.orders} orders ({cls._percent(snapshot.orders, snapshot.add_to_carts)} cart-to-order)",
        ]
        if snapshot.impressions > 0:
            evidence.append(
                f"{snapshot.clicks} clicks from {snapshot.impressions} impressions "
                f"({cls._percent(snapshot.clicks, snapshot.impressions)} collection CTR)"
            )
        return evidence

    @classmethod
    def _suspected_friction(
        cls,
        *,
        board: PriorityBoardType,
        signal_state: PrioritySignalState,
        snapshot: ProductSnapshot,
    ) -> str:
        if signal_state is PrioritySignalState.TRACKING_ISSUE:
            return "Collection and PDP tracking coverage is incomplete."
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return "The product does not have enough recent shopper sessions for a confident call."
        if signal_state is PrioritySignalState.WEAK_SIGNAL:
            return "The product has an early pattern, but the sample is still thin."
        if board is PriorityBoardType.HIDDEN_WINNER:
            return "Demand is proving out once shoppers reach the PDP, but exposure is still constrained."

        weak_component = cls._lowest_component_ctr(snapshot)
        if weak_component is not None:
            return f"{weak_component} is visible but rarely clicked, which can weaken buying confidence."
        if cls._rate(snapshot.orders, snapshot.add_to_carts) < 0.35:
            return "Shoppers show buy-box intent but do not complete the order."
        return "Shoppers reach the PDP, but the page is not converting that attention into buying action."

    @classmethod
    def _first_fix(
        cls,
        *,
        board: PriorityBoardType,
        signal_state: PrioritySignalState,
        snapshot: ProductSnapshot,
    ) -> str:
        if signal_state is PrioritySignalState.TRACKING_ISSUE:
            return "Verify the theme app embed and event delivery before changing product content."
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return "Wait for more PDP views or drive a small traffic test before making a page change."
        if signal_state is PrioritySignalState.WEAK_SIGNAL:
            return "Treat this as a watch item and re-check after the next traffic window."
        if board is PriorityBoardType.HIDDEN_WINNER:
            return "Give this SKU more collection, search, or campaign placement while monitoring conversion."

        weak_component = cls._lowest_component_ctr(snapshot)
        if weak_component is not None:
            return f"Move {weak_component} closer to the buy box and make its value obvious above the fold."
        if cls._rate(snapshot.orders, snapshot.add_to_carts) < 0.35:
            return "Clarify shipping, returns, and checkout confidence near the add-to-cart button."
        return "Test one above-the-fold trust or fit cue and compare the next window."

    @classmethod
    def _lowest_component_ctr(cls, snapshot: ProductSnapshot) -> str | None:
        candidates: list[tuple[float, str]] = []
        for component_id, impressions in snapshot.component_impressions_distribution.items():
            if impressions <= 0:
                continue
            clicks = snapshot.component_clicks_distribution.get(component_id, 0)
            candidates.append((cls._rate(clicks, impressions), component_id))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (item[0], item[1]))[0][1]

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
    def _rate(numerator: int, denominator: int) -> float:
        return 0.0 if denominator == 0 else numerator / denominator

    @classmethod
    def _percent(cls, numerator: int, denominator: int) -> str:
        return f"{cls._rate(numerator, denominator):.1%}"

    @staticmethod
    def _store_average_cr(snapshots: dict[str, ProductSnapshot]) -> float:
        total_views = sum(snapshot.views for snapshot in snapshots.values())
        total_orders = sum(snapshot.orders for snapshot in snapshots.values())
        return 0.0 if total_views == 0 else total_orders / total_views
