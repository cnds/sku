from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Text, UniqueConstraint
from sqlmodel import Column, Field, SQLModel


class EventType(StrEnum):
    PAGE_VIEW = "page_view"
    PRODUCT_VIEW = "product_view"
    COLLECTION_VIEW = "collection_view"
    SEARCH_SUBMITTED = "search_submitted"
    CART_VIEW = "cart_view"
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    CHECKOUT_STARTED = "checkout_started"
    CHECKOUT_STEP = "checkout_step"
    CHECKOUT_COMPLETED = "checkout_completed"
    ORDER_COMPLETED = "order_completed"
    PRODUCT_IMPRESSION = "product_impression"
    PRODUCT_CLICK = "product_click"
    COMPONENT_IMPRESSION = "component_impression"
    COMPONENT_CLICK = "component_click"
    MEDIA_INTERACTION = "media_interaction"
    VARIANT_INTENT = "variant_intent"
    ENGAGE = "engage"


class DiagnosisStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class RecommendationFeedbackAction(StrEnum):
    WILL_TRY = "will_try"
    NOT_USEFUL = "not_useful"
    ALREADY_FIXED = "already_fixed"
    REMIND_LATER = "remind_later"


class RawEvent(SQLModel, table=True):
    __tablename__ = "raw_events"
    __table_args__ = (UniqueConstraint("shop_id", "channel", "dedupe_key", name="uq_raw_event_dedupe"),)

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(index=True)
    shop_domain: str = Field(index=True)
    visitor_id: str = Field(index=True)
    session_id: str = Field(index=True)
    event_type: EventType = Field(index=True)
    component_id: str | None = Field(default=None, index=True)
    product_id: str | None = Field(default=None, index=True)
    variant_id: str | None = Field(default=None, index=True)
    channel: str = Field(index=True)
    event_id: str | None = Field(default=None, index=True)
    source_event_name: str | None = Field(default=None, index=True)
    dedupe_key: str | None = Field(default=None, index=True)
    occurred_at: datetime = Field(index=True)
    context_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )


class DailyProductStat(SQLModel, table=True):
    __tablename__ = "daily_stats"
    __table_args__ = (UniqueConstraint("shop_id", "product_id", "stat_date", name="uq_daily_stats"),)

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(index=True)
    product_id: str = Field(index=True)
    stat_date: date = Field(index=True)
    views: int = Field(default=0)
    add_to_carts: int = Field(default=0)
    orders: int = Field(default=0)
    component_clicks_distribution: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column("component_clicks_distribution", JSON, nullable=False),
    )
    impressions: int = Field(default=0)
    clicks: int = Field(default=0)
    media_interactions: int = Field(default=0)
    variant_changes: int = Field(default=0)
    total_dwell_ms: int = Field(default=0)
    engage_count: int = Field(default=0)
    avg_scroll_pct: int = Field(default=0)
    component_impressions_distribution: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column("component_impressions_distribution", JSON, nullable=False),
    )


class ProductDiagnosis(SQLModel, table=True):
    __tablename__ = "product_diagnoses"
    __table_args__ = (UniqueConstraint("shop_id", "product_id", "window", name="uq_product_diagnosis"),)

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(index=True)
    product_id: str = Field(index=True)
    window: str = Field(index=True)
    snapshot_hash: str = Field(index=True)
    status: DiagnosisStatus = Field(index=True)
    report_markdown: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    summary_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    generated_at: datetime | None = Field(default=None)


class ShopInstallation(SQLModel, table=True):
    __tablename__ = "shop_installations"
    __table_args__ = (UniqueConstraint("shop_domain", name="uq_shop_domain"),)

    id: int | None = Field(default=None, primary_key=True)
    shop_domain: str = Field(index=True)
    access_token: str | None = Field(default=None)
    public_token: str = Field(index=True)
    timezone_name: str = Field(default="UTC")
    installed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_completed_local_date: date | None = Field(default=None, index=True)
    next_rollup_at_utc: datetime | None = Field(default=None, index=True)


class RecommendationFeedback(SQLModel, table=True):
    __tablename__ = "recommendation_feedback"

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(index=True)
    product_id: str = Field(index=True)
    window: str = Field(index=True)
    board: str | None = Field(default=None, index=True)
    board_date: date | None = Field(default=None, index=True)
    window_start_date: date | None = Field(default=None, index=True)
    window_end_date: date | None = Field(default=None, index=True)
    card_rank: int | None = Field(default=None)
    action: str = Field(index=True)
    context_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
