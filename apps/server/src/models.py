from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Text, UniqueConstraint
from sqlmodel import Column, Field, SQLModel


class EventType(StrEnum):
    VIEW = "view"
    COMPONENT_CLICK = "component_click"
    ADD_TO_CART = "add_to_cart"
    ORDER = "order"
    IMPRESSION = "impression"
    CLICK = "click"
    MEDIA = "media"
    VARIANT = "variant"
    ENGAGE = "engage"


class DiagnosisStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class RawEvent(SQLModel, table=True):
    __tablename__ = "raw_events"

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
    occurred_at: datetime = Field(index=True)
    context_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )


class DailyProductStat(SQLModel, table=True):
    __tablename__ = "daily_stats"
    __table_args__ = (
        UniqueConstraint("shop_id", "product_id", "stat_date", name="uq_daily_stats"),
    )

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
    __table_args__ = (
        UniqueConstraint("shop_id", "product_id", "window", name="uq_product_diagnosis"),
    )

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
