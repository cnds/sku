from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import delete
from sqlmodel import select

from config import Settings, get_settings
from db import create_session_factory, db_session_context, get_db_session, init_db
from logging_utils import configure_logging
from models import DailyProductStat, EventType, ProductDiagnosis, RawEvent
from repositories.analytics import AnalyticsRepository
from schemas import IngestEvent, LeaderboardType, ProductSnapshot, TimeWindow
from services.analysis import ProductAnalysisService
from services.diagnosis import ProductDiagnosisService
from services.ingestion import EventIngestionService
from services.shop_installations import ShopInstallationService
from services.shop_time import ensure_utc_datetime, local_date_for_shop

LOGGER = logging.getLogger(__name__)

DEFAULT_PUBLIC_TOKEN = "demo-public-token"  # noqa: S105 - demo seed uses a local public token value.
DEFAULT_SHOP_DOMAIN = "demo.myshopify.com"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_WEB_BASE_URL = "http://localhost:3000"


@dataclass(frozen=True, slots=True)
class DemoProductPlan:
    product_id: str
    views: int
    add_to_carts: int
    orders: int
    component_clicks: dict[str, int]
    problem: str
    cause: str
    recommendations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DemoSeedSummary:
    shop_domain: str
    dashboard_url: str
    blackboard_top_product_id: str
    redboard_top_product_id: str
    raw_event_count: int
    daily_stat_count: int
    diagnosis_count: int


DEMO_PRODUCTS: tuple[DemoProductPlan, ...] = (
    DemoProductPlan(
        product_id="demo-underperformer",
        views=60,
        add_to_carts=8,
        orders=1,
        component_clicks={
            "hero_cta": 5,
            "review_tab": 2,
            "size_chart": 1,
        },
        problem="Traffic is landing on the PDP, but orders are lagging the store benchmark.",
        cause=(
            "The page gets enough views, but trust and sizing components are being "
            "used less than the benchmark product."
        ),
        recommendations=(
            "Move social proof higher on the page.",
            "Expose the size chart closer to the buy box.",
            "Tighten the CTA copy around shipping and returns.",
        ),
    ),
    DemoProductPlan(
        product_id="demo-benchmark",
        views=70,
        add_to_carts=20,
        orders=12,
        component_clicks={
            "hero_cta": 14,
            "review_tab": 10,
            "size_chart": 8,
        },
        problem="This product is already acting as the conversion benchmark for the shop.",
        cause="Customers reach supporting content early and continue through the funnel without a large drop-off.",
        recommendations=(
            "Reuse this page layout as the reference for lower-performing PDPs.",
            "Keep the review module and sizing guidance above the fold.",
            "Reuse this content structure for similar high-intent products.",
        ),
    ),
    DemoProductPlan(
        product_id="demo-hidden-gem",
        views=18,
        add_to_carts=7,
        orders=3,
        component_clicks={
            "hero_cta": 4,
            "review_tab": 2,
            "size_chart": 2,
        },
        problem="The PDP is converting well once shoppers discover it, but traffic is still limited.",
        cause="Add-to-cart and order rates are strong, yet the total view volume is much lower than the shop average.",
        recommendations=(
            "Feature this SKU in collection pages and merchandising blocks.",
            "Drive paid or email traffic toward this PDP.",
            "Promote this SKU next to weaker products with stronger traffic.",
        ),
    ),
)


async def seed_demo_data(
    *,
    settings: Settings,
    shop_domain: str = DEFAULT_SHOP_DOMAIN,
    public_token: str = DEFAULT_PUBLIC_TOKEN,
    timezone_name: str = DEFAULT_TIMEZONE,
    now_utc: datetime | None = None,
    web_base_url: str = DEFAULT_WEB_BASE_URL,
) -> DemoSeedSummary:
    resolved_now = ensure_utc_datetime(now_utc or datetime.now(UTC))
    session_factory = create_session_factory(settings.database_url)

    await init_db(session_factory.engine)

    try:
        async with db_session_context(session_factory) as session:
            installation = await ShopInstallationService().upsert_installation(
                shop_domain=shop_domain,
                public_token=public_token,
                access_token=None,
                timezone_name=timezone_name,
            )
            normalized_timezone = installation.timezone_name
            await _clear_existing_demo_records(shop_domain=shop_domain)

            ingestion_service = EventIngestionService()
            for index, plan in enumerate(DEMO_PRODUCTS):
                occurred_at = resolved_now - timedelta(hours=index + 1)
                events = _build_events(plan=plan, occurred_at=occurred_at)
                await ingestion_service.persist_batch_and_rollup(
                    channel="sdk",
                    events=events,
                    session_id=f"demo-seed-session-{plan.product_id}",
                    shop_domain=shop_domain,
                    shop_id=shop_domain,
                    stat_dates={
                        local_date_for_shop(
                            instant=event.occurred_at,
                            timezone_name=normalized_timezone,
                        )
                        for event in events
                    },
                    timezone_name=normalized_timezone,
                    visitor_id=f"demo-seed-visitor-{plan.product_id}",
                )

            await _seed_diagnoses(
                now_utc=resolved_now,
                settings=settings,
                shop_domain=shop_domain,
                timezone_name=normalized_timezone,
            )
            await session.commit()

            blackboard, redboard = await _fetch_seeded_leaderboards(
                now_utc=resolved_now,
                settings=settings,
                shop_domain=shop_domain,
            )
            raw_event_count = await _count_rows(RawEvent, shop_domain=shop_domain)
            daily_stat_count = await _count_rows(DailyProductStat, shop_domain=shop_domain)
            diagnosis_count = await _count_rows(ProductDiagnosis, shop_domain=shop_domain)

            return DemoSeedSummary(
                shop_domain=shop_domain,
                dashboard_url=_dashboard_url(shop_domain=shop_domain, web_base_url=web_base_url),
                blackboard_top_product_id=blackboard[0].product_id,
                redboard_top_product_id=redboard[0].product_id,
                raw_event_count=raw_event_count,
                daily_stat_count=daily_stat_count,
                diagnosis_count=diagnosis_count,
            )
    finally:
        await session_factory.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed repeatable demo data so the SKU Lens dashboard has visible local content.",
    )
    parser.add_argument("--shop-domain", default=DEFAULT_SHOP_DOMAIN)
    parser.add_argument("--public-token", default=DEFAULT_PUBLIC_TOKEN)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--web-base-url", default=DEFAULT_WEB_BASE_URL)
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.sku_lens_log_level)
    summary = asyncio.run(
        seed_demo_data(
            settings=settings,
            shop_domain=args.shop_domain,
            public_token=args.public_token,
            timezone_name=args.timezone,
            web_base_url=args.web_base_url,
        )
    )

    LOGGER.info(
        (
            "demo data seeded shop_domain=%s raw_events=%s daily_stats=%s "
            "diagnoses=%s blackboard_top=%s redboard_top=%s dashboard_url=%s"
        ),
        summary.shop_domain,
        summary.raw_event_count,
        summary.daily_stat_count,
        summary.diagnosis_count,
        summary.blackboard_top_product_id,
        summary.redboard_top_product_id,
        summary.dashboard_url,
    )


def _build_events(*, plan: DemoProductPlan, occurred_at: datetime) -> list[IngestEvent]:
    events: list[IngestEvent] = []

    events.extend(
        IngestEvent(
            event_type=EventType.VIEW,
            occurred_at=occurred_at,
            product_id=plan.product_id,
        )
        for _ in range(plan.views)
    )
    events.extend(
        IngestEvent(
            event_type=EventType.ADD_TO_CART,
            occurred_at=occurred_at + timedelta(minutes=1),
            product_id=plan.product_id,
        )
        for _ in range(plan.add_to_carts)
    )
    events.extend(
        IngestEvent(
            event_type=EventType.ORDER,
            occurred_at=occurred_at + timedelta(minutes=2),
            product_id=plan.product_id,
        )
        for _ in range(plan.orders)
    )

    for component_id, count in plan.component_clicks.items():
        events.extend(
            IngestEvent(
                event_type=EventType.COMPONENT_CLICK,
                occurred_at=occurred_at + timedelta(minutes=3),
                product_id=plan.product_id,
                component_id=component_id,
            )
            for _ in range(count)
        )

    return events


async def _clear_existing_demo_records(*, shop_domain: str) -> None:
    session = get_db_session()
    product_ids = tuple(plan.product_id for plan in DEMO_PRODUCTS)

    await session.exec(
        delete(ProductDiagnosis).where(
            ProductDiagnosis.shop_id == shop_domain,
            ProductDiagnosis.product_id.in_(product_ids),
        )
    )
    await session.exec(
        delete(DailyProductStat).where(
            DailyProductStat.shop_id == shop_domain,
            DailyProductStat.product_id.in_(product_ids),
        )
    )
    await session.exec(
        delete(RawEvent).where(
            RawEvent.shop_id == shop_domain,
            RawEvent.product_id.in_(product_ids),
        )
    )


async def _seed_diagnoses(
    *,
    now_utc: datetime,
    settings: Settings,
    shop_domain: str,
    timezone_name: str,
) -> None:
    reference_date = local_date_for_shop(instant=now_utc, timezone_name=timezone_name)
    repository = AnalyticsRepository()
    diagnosis_service = ProductDiagnosisService()
    plans_by_product_id = {plan.product_id: plan for plan in DEMO_PRODUCTS}

    for window in TimeWindow:
        snapshots = await repository.fetch_product_snapshots(
            shop_id=shop_domain,
            window=window,
            reference_date=reference_date,
        )
        for product_id, snapshot in snapshots.items():
            prepared = await diagnosis_service.prepare_report(
                product_id=product_id,
                shop_id=shop_domain,
                snapshot=snapshot,
                window=window,
            )
            plan = plans_by_product_id[product_id]
            await diagnosis_service.store_generated_report(
                product_id=product_id,
                report_markdown=_report_markdown(
                    plan=plan,
                    snapshot=snapshot,
                    window=window,
                ),
                shop_id=shop_domain,
                snapshot_hash=prepared.result.snapshot_hash,
                summary_json={
                    "orders": str(snapshot.orders),
                    "views": str(snapshot.views),
                    "window": window.value,
                },
                window=window,
            )

    analysis_service = ProductAnalysisService(
        settings=settings,
        time_provider=lambda: now_utc,
    )
    for window in TimeWindow:
        for plan in DEMO_PRODUCTS:
            await analysis_service.get_product_analysis(
                product_id=plan.product_id,
                shop_id=shop_domain,
                window=window,
            )


async def _fetch_seeded_leaderboards(
    *,
    now_utc: datetime,
    settings: Settings,
    shop_domain: str,
) -> tuple[list, list]:
    analysis_service = ProductAnalysisService(
        settings=settings,
        time_provider=lambda: now_utc,
    )
    blackboard = await analysis_service.get_leaderboard(
        board=LeaderboardType.BLACK,
        shop_id=shop_domain,
        window=TimeWindow.HOURS_24,
    )
    redboard = await analysis_service.get_leaderboard(
        board=LeaderboardType.RED,
        shop_id=shop_domain,
        window=TimeWindow.HOURS_24,
    )
    if not blackboard or not redboard:
        raise RuntimeError("Demo seed did not produce leaderboard rows.")
    return blackboard, redboard


async def _count_rows(
    model: type[RawEvent] | type[DailyProductStat] | type[ProductDiagnosis],
    *,
    shop_domain: str,
) -> int:
    session = get_db_session()
    rows = (await session.exec(select(model).where(model.shop_id == shop_domain))).all()
    return len(rows)


def _dashboard_url(*, shop_domain: str, web_base_url: str) -> str:
    query = urlencode({"shop": shop_domain, "window": TimeWindow.HOURS_24.value})
    return f"{web_base_url}/?{query}"


def _report_markdown(
    *,
    plan: DemoProductPlan,
    snapshot: ProductSnapshot,
    window: TimeWindow,
) -> str:
    recommendations = "\n".join(f"- {item}" for item in plan.recommendations)
    return (
        "## Problem\n"
        f"{plan.problem}\n\n"
        "## Cause\n"
        f"{plan.cause}\n"
        f"Observed snapshot for {window.value}: {snapshot.views} views, "
        f"{snapshot.add_to_carts} add-to-carts, {snapshot.orders} orders.\n\n"
        "## Recommendations\n"
        f"{recommendations}"
    )
