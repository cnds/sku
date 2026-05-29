from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

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
    PriorityTrendState,
    ProductAnalysisResult,
    ProductSnapshot,
    TimeWindow,
)
from services.shop_time import ensure_utc_datetime, local_date_for_shop


class ProductAnalysisNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("Product analysis not found.")


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
        target = snapshots.get(product_id)
        if target is None:
            raise ProductAnalysisNotFoundError()

        benchmark_snapshots = await self._repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=TimeWindow.DAYS_30,
            reference_date=reference_date,
        )

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
        window_start_date = window.start_date_from_reference_date(reference_date=reference_date)
        window_end_date = reference_date
        snapshots = await self._repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )
        if not snapshots:
            return []

        previous_start, previous_end = self._previous_window_bounds(
            reference_date=reference_date,
            window=window,
        )
        previous_snapshots = await self._repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=window,
            start_date=previous_start,
            end_date=previous_end,
        )
        previous_entries = {
            PriorityBoardType.LEAKER: self._score_entries(
                board=PriorityBoardType.LEAKER,
                snapshots=previous_snapshots,
            ),
            PriorityBoardType.HIDDEN_WINNER: self._score_entries(
                board=PriorityBoardType.HIDDEN_WINNER,
                snapshots=previous_snapshots,
            ),
        }
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
                    board_date=reference_date,
                    card_rank=len(selected) + 1,
                    entry=entry,
                    previous_entry=previous_entries[PriorityBoardType.LEAKER].get(entry.product_id),
                    snapshot=snapshots[entry.product_id],
                    window=window,
                    window_end_date=window_end_date,
                    window_start_date=window_start_date,
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
                    board_date=reference_date,
                    card_rank=len(selected) + 1,
                    entry=entry,
                    previous_entry=previous_entries[PriorityBoardType.HIDDEN_WINNER].get(entry.product_id),
                    snapshot=snapshots[entry.product_id],
                    window=window,
                    window_end_date=window_end_date,
                    window_start_date=window_start_date,
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
        board_date: date,
        card_rank: int,
        entry: LeaderboardEntry,
        previous_entry: LeaderboardEntry | None,
        snapshot: ProductSnapshot,
        window: TimeWindow,
        window_end_date: date,
        window_start_date: date,
    ) -> PriorityCard:
        signal_state = self.derive_priority_signal_state(snapshot)
        primary_step = self._primary_step(board=board, signal_state=signal_state, snapshot=snapshot)
        trend_state, trend_reason = self._priority_trend(
            board=board,
            current_score=entry.score,
            previous_entry=previous_entry,
            window=window,
        )
        return PriorityCard(
            product_id=entry.product_id,
            board=board,
            board_date=board_date,
            window_start_date=window_start_date,
            window_end_date=window_end_date,
            card_rank=card_rank,
            signal_state=signal_state,
            trend_state=trend_state,
            trend_reason=trend_reason,
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
            return "Not enough sessions to call a Winner or Leaker"
        if signal_state is PrioritySignalState.WEAK_SIGNAL:
            return "Early signal; validate with more traffic"
        if board is PriorityBoardType.HIDDEN_WINNER:
            return "High intent, underexposed"
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
                "Missing event coverage for collection or PDP components",
                "Verify the theme app embed before acting on page content",
            ]
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return [
                f"{snapshot.views} PDP views",
                f"{snapshot.add_to_carts} add-to-carts",
                "Collect more PDP sessions or run a small traffic test",
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
            return "Missing event coverage makes this card a tracking check, not a PDP content recommendation."
        if signal_state is PrioritySignalState.INSUFFICIENT_DATA:
            return "This product needs more recent PDP sessions before SKU Lens can make a confident call."
        if signal_state is PrioritySignalState.WEAK_SIGNAL:
            return "This is a watch item: the pattern is early, and the sample is still thin."
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

    @classmethod
    def _priority_trend(
        cls,
        *,
        board: PriorityBoardType,
        current_score: float,
        previous_entry: LeaderboardEntry | None,
        window: TimeWindow,
    ) -> tuple[PriorityTrendState, str]:
        if previous_entry is None:
            return (
                PriorityTrendState.NEW,
                f"No previous {window.value} comparison window yet.",
            )

        delta = current_score - previous_entry.score
        threshold = max(0.5, abs(previous_entry.score) * 0.1)
        if abs(delta) < threshold:
            return (
                PriorityTrendState.STABLE,
                f"Signal is steady versus the previous {window.value} window.",
            )

        if board is PriorityBoardType.HIDDEN_WINNER:
            if delta > 0:
                return (
                    PriorityTrendState.WORSENING,
                    f"Opportunity gap is growing versus the previous {window.value} window.",
                )
            return (
                PriorityTrendState.IMPROVING,
                f"Opportunity gap is narrowing versus the previous {window.value} window.",
            )

        if delta > 0:
            return (
                PriorityTrendState.WORSENING,
                f"Leaker gap is up versus the previous {window.value} window.",
            )
        return (
            PriorityTrendState.IMPROVING,
            f"Leaker gap is down versus the previous {window.value} window.",
        )

    @classmethod
    def _score_entries(
        cls,
        *,
        board: PriorityBoardType,
        snapshots: dict[str, ProductSnapshot],
    ) -> dict[str, LeaderboardEntry]:
        if not snapshots:
            return {}

        total_views = sum(snapshot.views for snapshot in snapshots.values())
        total_orders = sum(snapshot.orders for snapshot in snapshots.values())
        store_avg_cr = 0.0 if total_views == 0 else total_orders / total_views
        store_avg_views = total_views / len(snapshots)

        entries: dict[str, LeaderboardEntry] = {}
        for product_id, snapshot in snapshots.items():
            if board is PriorityBoardType.HIDDEN_WINNER:
                score = cls._rate(snapshot.add_to_carts, snapshot.views) * store_avg_views - snapshot.views
            else:
                score = snapshot.views * store_avg_cr - snapshot.orders
            entries[product_id] = LeaderboardEntry(
                product_id=product_id,
                views=snapshot.views,
                add_to_carts=snapshot.add_to_carts,
                orders=snapshot.orders,
                impressions=snapshot.impressions,
                clicks=snapshot.clicks,
                score=score,
            )
        return entries

    @staticmethod
    def _previous_window_bounds(
        *,
        reference_date: date,
        window: TimeWindow,
    ) -> tuple[date, date]:
        current_start = window.start_date_from_reference_date(reference_date=reference_date)
        previous_end = current_start - timedelta(days=1)
        bucket_days = max(1, window.delta.days)
        previous_start = previous_end - timedelta(days=bucket_days - 1)
        return previous_start, previous_end

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
