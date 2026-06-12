from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from models import DiagnosisStatus, EventType, RecommendationFeedbackAction


class TimeWindow(StrEnum):
    HOURS_24 = "24h"
    DAYS_7 = "7d"
    DAYS_30 = "30d"

    @property
    def delta(self) -> timedelta:
        if self is TimeWindow.HOURS_24:
            return timedelta(hours=24)
        if self is TimeWindow.DAYS_7:
            return timedelta(days=7)
        return timedelta(days=30)

    def start_date(self, *, now: datetime | None = None) -> datetime.date:
        return self.start_date_from_reference_date(reference_date=(now or datetime.now(UTC)).date())

    def start_date_from_reference_date(self, *, reference_date: date) -> date:
        reference = datetime.combine(reference_date, time.min, tzinfo=UTC)
        return (reference - self.delta).date()


class LeaderboardType(StrEnum):
    BLACK = "black"
    RED = "red"


class PriorityBoardType(StrEnum):
    LEAKER = "leaker"
    HIDDEN_WINNER = "hidden_winner"


class PrioritySignalState(StrEnum):
    READY = "Ready"
    WEAK_SIGNAL = "Weak signal"
    INSUFFICIENT_DATA = "Insufficient data"
    TRACKING_ISSUE = "Tracking issue"


class PriorityTrendState(StrEnum):
    NEW = "New"
    WORSENING = "Worsening"
    IMPROVING = "Improving"
    STABLE = "Stable"


class IntegrationHealthStatus(StrEnum):
    HEALTHY = "healthy"
    PARTIAL = "partial"
    NOT_CONNECTED = "not_connected"


class IntegrationCheckStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"


class OnboardingChecklistStatus(StrEnum):
    DONE = "done"
    ACTION = "action"
    PENDING = "pending"


class IngestEvent(BaseModel):
    event_type: EventType
    occurred_at: datetime
    product_id: str | None = None
    variant_id: str | None = None
    component_id: str | None = None
    event_id: str | None = None
    source_event_name: str | None = None
    dedupe_key: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class IngestBatchRequest(BaseModel):
    shop_domain: str
    visitor_id: str
    session_id: str
    events: list[IngestEvent]


class ShopifyPixelEvent(BaseModel):
    source_event_name: str
    event_id: str
    occurred_at: datetime
    product_id: str | None = None
    variant_id: str | None = None
    component_id: str | None = None
    dedupe_key: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ShopifyPixelBatchRequest(BaseModel):
    shop_domain: str
    visitor_id: str
    session_id: str
    events: list[ShopifyPixelEvent]


class IngestAcceptedResponse(BaseModel):
    accepted: int


class ShopifyOAuthCallbackResponse(BaseModel):
    shop: str
    public_token: str


class ShopifyWebhookAcceptedResponse(BaseModel):
    accepted: bool
    enqueued: int


class OnboardingChecklistItem(BaseModel):
    key: str
    label: str
    status: OnboardingChecklistStatus
    message: str


class OnboardingStatusResponse(BaseModel):
    shop_id: str
    installed: bool
    public_token: str | None
    ingest_endpoint: str
    app_embed_deep_link: str
    integration_health: IntegrationHealthResponse
    last_raw_event_at: datetime | None
    checklist: list[OnboardingChecklistItem]


class RecommendationFeedbackRequest(BaseModel):
    shop_id: str
    product_id: str
    window: TimeWindow = TimeWindow.HOURS_24
    action: RecommendationFeedbackAction
    board: PriorityBoardType | None = None
    board_date: date | None = None
    window_start_date: date | None = None
    window_end_date: date | None = None
    card_rank: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class RecommendationFeedbackResponse(BaseModel):
    accepted: bool
    latest_action: RecommendationFeedbackAction
    product_id: str
    shop_id: str
    window: TimeWindow


class LeaderboardEntry(BaseModel):
    product_id: str
    views: int
    add_to_carts: int
    orders: int
    impressions: int = 0
    clicks: int = 0
    score: float


class FunnelSnapshot(BaseModel):
    views: int
    add_to_carts: int
    orders: int
    impressions: int = 0
    clicks: int = 0
    media_interactions: int = 0
    variant_changes: int = 0
    total_dwell_ms: int = 0
    engage_count: int = 0
    avg_scroll_pct: int = 0
    component_clicks_distribution: dict[str, int] = Field(default_factory=dict)
    component_impressions_distribution: dict[str, int] = Field(default_factory=dict)


class FunnelComparison(BaseModel):
    target: FunnelSnapshot
    benchmark: FunnelSnapshot


class ComponentComparison(BaseModel):
    component_id: str
    target_clicks: int
    benchmark_clicks: int
    target_ctr: float
    benchmark_ctr: float
    delta: float


class ProductSnapshot(BaseModel):
    views: int
    add_to_carts: int
    orders: int
    component_clicks_distribution: dict[str, int] = Field(default_factory=dict)
    impressions: int = 0
    clicks: int = 0
    media_interactions: int = 0
    variant_changes: int = 0
    total_dwell_ms: int = 0
    engage_count: int = 0
    avg_scroll_pct: int = 0
    component_impressions_distribution: dict[str, int] = Field(default_factory=dict)


class ProductAnalysisResult(BaseModel):
    product_id: str
    benchmark_product_id: str
    gap: float
    funnel: FunnelComparison
    component_comparisons: list[ComponentComparison]


class PriorityCard(BaseModel):
    product_id: str
    board: PriorityBoardType
    board_date: date
    window_start_date: date
    window_end_date: date
    card_rank: int
    signal_state: PrioritySignalState
    trend_state: PriorityTrendState
    trend_reason: str
    flag_reason: str
    primary_step: str
    evidence: list[str]
    suspected_friction: str
    first_fix: str
    views: int
    add_to_carts: int
    orders: int
    impressions: int
    clicks: int
    score: float


class DiagnosisResult(BaseModel):
    status: DiagnosisStatus
    snapshot_hash: str
    report_markdown: str | None
    summary_json: dict[str, Any]
    generated_at: datetime | None


class IntegrationHealthCoverage(BaseModel):
    impressions: int
    clicks: int
    views: int
    component_clicks: int
    add_to_carts: int
    orders: int


class IntegrationHealthCheck(BaseModel):
    key: str
    label: str
    status: IntegrationCheckStatus
    message: str


class IntegrationHealthResponse(BaseModel):
    status: IntegrationHealthStatus
    last_event_at: datetime | None
    coverage: IntegrationHealthCoverage
    checks: list[IntegrationHealthCheck]


class InternalCardReviewItem(BaseModel):
    priority_card: PriorityCard
    raw_event_counts: dict[str, int]
    aggregate_evidence: dict[str, Any]
    derived_signal: dict[str, Any]
    ai_summary: dict[str, Any]
    merchant_copy: dict[str, Any]


class InternalCardReviewResponse(BaseModel):
    shop_id: str
    window: TimeWindow
    cards: list[InternalCardReviewItem]
