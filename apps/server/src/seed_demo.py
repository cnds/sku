from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import delete, desc
from sqlmodel import select

from config import Settings, get_settings
from db import create_session_factory, db_session_context, get_db_session, init_db
from logging_utils import configure_logging
from models import DailyProductStat, EventType, ProductDiagnosis, RawEvent, ShopInstallation
from repositories.analytics import AnalyticsRepository
from schemas import IngestEvent, LeaderboardType, ProductSnapshot, TimeWindow
from services.analysis import ProductAnalysisService
from services.diagnosis import ProductDiagnosisService
from services.ingestion import SHOPIFY_PIXEL_EVENT_TYPES, EventIngestionService
from services.shop_installations import ShopInstallationService
from services.shop_time import ensure_utc_datetime, local_date_for_shop
from services.shopify import normalize_shop_domain

LOGGER = logging.getLogger(__name__)

DEFAULT_PUBLIC_TOKEN = "demo-public-token"  # noqa: S105 - demo seed uses a local public token value.
DEFAULT_SHOP_DOMAIN = "sku-dev-uaop8pff.myshopify.com"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_WEB_BASE_URL = "http://localhost:3000"


@dataclass(frozen=True, slots=True)
class DemoProductScenario:
    product_id: str
    impressions: int
    clicks: int
    views: int
    add_to_carts: int
    orders: int
    media_interactions: int
    variant_changes: int
    dwell_ms: int
    scroll_pct: int
    component_clicks: dict[str, int]
    component_impressions: dict[str, int]
    observed: str
    suspected_friction: str
    first_fix: str


@dataclass(frozen=True, slots=True)
class DemoSeedSummary:
    shop_domain: str
    dashboard_url: str
    blackboard_top_product_id: str
    redboard_top_product_id: str
    raw_event_count: int
    daily_stat_count: int
    diagnosis_count: int


SHOPIFY_ADMIN_SCENARIOS: tuple[DemoProductScenario, ...] = (
    DemoProductScenario(
        product_id="demo-size-confidence-leaker",
        impressions=240,
        clicks=44,
        views=120,
        add_to_carts=8,
        orders=1,
        media_interactions=12,
        variant_changes=9,
        dwell_ms=17000,
        scroll_pct=58,
        component_clicks={
            "product_media": 8,
            "product_description": 3,
            "review_tab": 4,
            "shipping_returns": 2,
            "size_chart": 1,
        },
        component_impressions={
            "product_media": 82,
            "product_description": 68,
            "review_tab": 58,
            "shipping_returns": 54,
            "size_chart": 76,
        },
        observed="Shoppers reach the PDP, but very few continue from viewing to add-to-cart.",
        suspected_friction="Size confidence is weak because the size chart is visible but rarely opened.",
        first_fix="Move the size chart beside the variant selector and repeat fit guidance near the buy box.",
    ),
    DemoProductScenario(
        product_id="demo-media-trust-leaker",
        impressions=210,
        clicks=39,
        views=100,
        add_to_carts=10,
        orders=2,
        media_interactions=1,
        variant_changes=5,
        dwell_ms=13000,
        scroll_pct=45,
        component_clicks={
            "product_media": 1,
            "product_description": 5,
            "review_tab": 1,
            "shipping_returns": 1,
            "size_chart": 4,
        },
        component_impressions={
            "product_media": 90,
            "product_description": 74,
            "review_tab": 70,
            "shipping_returns": 62,
            "size_chart": 50,
        },
        observed="The PDP earns clicks, but shoppers do not inspect media or trust proof before dropping.",
        suspected_friction="Media and reviews are not pulling enough attention to reduce hesitation.",
        first_fix="Bring one strong product video and the review summary above the fold.",
    ),
    DemoProductScenario(
        product_id="demo-hidden-winner",
        impressions=65,
        clicks=28,
        views=30,
        add_to_carts=14,
        orders=7,
        media_interactions=10,
        variant_changes=8,
        dwell_ms=24000,
        scroll_pct=78,
        component_clicks={
            "product_media": 6,
            "recommendations": 4,
            "review_tab": 7,
            "size_chart": 5,
        },
        component_impressions={
            "product_media": 20,
            "recommendations": 18,
            "review_tab": 30,
            "size_chart": 25,
        },
        observed="The product converts strongly once discovered, but traffic is still low.",
        suspected_friction="Discovery is the constraint rather than PDP persuasion.",
        first_fix="Give this SKU a higher collection slot and one campaign placement for the next window.",
    ),
    DemoProductScenario(
        product_id="demo-benchmark",
        impressions=260,
        clicks=58,
        views=120,
        add_to_carts=24,
        orders=16,
        media_interactions=18,
        variant_changes=12,
        dwell_ms=26000,
        scroll_pct=82,
        component_clicks={
            "product_media": 14,
            "product_description": 12,
            "recommendations": 9,
            "review_tab": 12,
            "shipping_returns": 8,
            "size_chart": 10,
        },
        component_impressions={
            "product_media": 86,
            "product_description": 80,
            "recommendations": 58,
            "review_tab": 68,
            "shipping_returns": 60,
            "size_chart": 72,
        },
        observed="This product is acting as the conversion benchmark for the shop.",
        suspected_friction="No primary friction is visible in the current window.",
        first_fix="Reuse this page structure as the reference for weaker PDPs.",
    ),
)

LEGACY_DEMO_PRODUCT_IDS = (
    "demo-underperformer",
    "demo-hidden-gem",
)


async def seed_demo_data(
    *,
    settings: Settings,
    shop_domain: str | None = None,
    public_token: str | None = None,
    timezone_name: str | None = None,
    now_utc: datetime | None = None,
    web_base_url: str = DEFAULT_WEB_BASE_URL,
) -> DemoSeedSummary:
    resolved_now = ensure_utc_datetime(now_utc or datetime.now(UTC))
    session_factory = create_session_factory(settings.database_url)

    await init_db(session_factory.engine)

    try:
        async with db_session_context(session_factory) as session:
            target_shop_domain = await _target_shop_domain(shop_domain=shop_domain)
            installation = await _ensure_seed_installation(
                public_token=public_token,
                shop_domain=target_shop_domain,
                timezone_name=timezone_name,
            )
            await _clear_existing_demo_records(shop_domain=target_shop_domain)
            await _persist_scenarios(
                now_utc=resolved_now,
                shop_domain=target_shop_domain,
                timezone_name=installation.timezone_name,
            )
            await _seed_diagnoses(
                now_utc=resolved_now,
                settings=settings,
                shop_domain=target_shop_domain,
                timezone_name=installation.timezone_name,
            )
            await session.commit()

            blackboard, redboard = await _fetch_seeded_leaderboards(
                now_utc=resolved_now,
                settings=settings,
                shop_domain=target_shop_domain,
            )
            raw_event_count = await _count_rows(RawEvent, shop_domain=target_shop_domain)
            daily_stat_count = await _count_rows(DailyProductStat, shop_domain=target_shop_domain)
            diagnosis_count = await _count_rows(ProductDiagnosis, shop_domain=target_shop_domain)

            return DemoSeedSummary(
                shop_domain=target_shop_domain,
                dashboard_url=_dashboard_url(shop_domain=target_shop_domain, web_base_url=web_base_url),
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
        description=(
            "Seed Shopify-visible demo data for the most recently installed shop. "
            "Pass --shop-domain to target a specific development store."
        ),
    )
    parser.add_argument(
        "--shop-domain",
        default=None,
        help=(
            "Shopify shop domain to seed. If omitted, the latest installed shop is used; "
            f"if no installation exists, {DEFAULT_SHOP_DOMAIN} is used."
        ),
    )
    parser.add_argument(
        "--public-token",
        default=None,
        help="Override the shop public ingest token. Existing installed shops keep their token by default.",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help="Override the shop IANA timezone. Existing installed shops keep their timezone by default.",
    )
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
            "shopify-visible demo data seeded shop_domain=%s raw_events=%s daily_stats=%s "
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


async def _target_shop_domain(*, shop_domain: str | None) -> str:
    if shop_domain is not None:
        return normalize_shop_domain(shop_domain)

    session = get_db_session()
    latest_oauth_installation = (
        await session.exec(
            select(ShopInstallation)
            .where(ShopInstallation.access_token.is_not(None))
            .order_by(
                desc(ShopInstallation.installed_at),
                desc(ShopInstallation.id),
            )
        )
    ).first()
    if latest_oauth_installation is not None:
        return normalize_shop_domain(latest_oauth_installation.shop_domain)

    latest_installation = (
        await session.exec(
            select(ShopInstallation).order_by(
                desc(ShopInstallation.installed_at),
                desc(ShopInstallation.id),
            )
        )
    ).first()
    if latest_installation is None:
        return DEFAULT_SHOP_DOMAIN
    return normalize_shop_domain(latest_installation.shop_domain)


async def _ensure_seed_installation(
    *,
    public_token: str | None,
    shop_domain: str,
    timezone_name: str | None,
) -> ShopInstallation:
    service = ShopInstallationService()
    existing = await service.get_by_shop_domain(shop_domain)
    return await service.upsert_installation(
        shop_domain=shop_domain,
        public_token=public_token or (existing.public_token if existing is not None else DEFAULT_PUBLIC_TOKEN),
        access_token=existing.access_token if existing is not None else None,
        timezone_name=timezone_name or (existing.timezone_name if existing is not None else DEFAULT_TIMEZONE),
    )


async def _persist_scenarios(
    *,
    now_utc: datetime,
    shop_domain: str,
    timezone_name: str,
) -> None:
    ingestion_service = EventIngestionService()
    for index, scenario in enumerate(SHOPIFY_ADMIN_SCENARIOS):
        occurred_at = now_utc - timedelta(hours=index + 1)
        events = _events_for_scenario(scenario=scenario, occurred_at=occurred_at)
        for channel, channel_events in _events_by_channel(events).items():
            await ingestion_service.persist_batch_and_rollup(
                channel=channel,
                events=channel_events,
                session_id=f"seed-session-{scenario.product_id}",
                shop_domain=shop_domain,
                shop_id=shop_domain,
                stat_dates={
                    local_date_for_shop(
                        instant=event.occurred_at,
                        timezone_name=timezone_name,
                    )
                    for event in channel_events
                },
                timezone_name=timezone_name,
                visitor_id=f"seed-visitor-{scenario.product_id}",
            )
    _persist_previous_seven_day_stats(
        now_utc=now_utc,
        shop_domain=shop_domain,
        timezone_name=timezone_name,
    )


def _events_by_channel(events: list[IngestEvent]) -> dict[str, list[IngestEvent]]:
    grouped = {
        "shopify_pixel": [],
        "shopify_webhook": [],
        "sdk_dom": [],
    }
    for event in events:
        if event.event_type in SHOPIFY_PIXEL_EVENT_TYPES:
            channel = "shopify_pixel"
        elif event.event_type is EventType.ORDER_COMPLETED:
            channel = "shopify_webhook"
        else:
            channel = "sdk_dom"
        grouped[channel].append(event)
    return {channel: channel_events for channel, channel_events in grouped.items() if channel_events}


def _persist_previous_seven_day_stats(
    *,
    now_utc: datetime,
    shop_domain: str,
    timezone_name: str,
) -> None:
    reference_date = local_date_for_shop(instant=now_utc, timezone_name=timezone_name)
    previous_stat_date = TimeWindow.DAYS_7.start_date_from_reference_date(reference_date=reference_date) - timedelta(
        days=1
    )
    session = get_db_session()
    session.add_all(
        [
            _previous_daily_stat(
                scenario=scenario,
                shop_domain=shop_domain,
                stat_date=previous_stat_date,
            )
            for scenario in SHOPIFY_ADMIN_SCENARIOS
        ]
    )


def _previous_daily_stat(
    *,
    scenario: DemoProductScenario,
    shop_domain: str,
    stat_date: date,
) -> DailyProductStat:
    scale = 0.33 if scenario.product_id == "demo-hidden-winner" else 1.0
    return DailyProductStat(
        add_to_carts=_scaled_previous_value(scenario.add_to_carts, scale=scale),
        avg_scroll_pct=scenario.scroll_pct,
        clicks=_scaled_previous_value(scenario.clicks, scale=scale),
        component_clicks_distribution=_scaled_previous_distribution(scenario.component_clicks, scale=scale),
        component_impressions_distribution=_scaled_previous_distribution(
            scenario.component_impressions,
            scale=scale,
        ),
        engage_count=1,
        impressions=_scaled_previous_value(scenario.impressions, scale=scale),
        media_interactions=_scaled_previous_value(scenario.media_interactions, scale=scale),
        orders=_scaled_previous_value(scenario.orders, scale=scale),
        product_id=scenario.product_id,
        shop_id=shop_domain,
        stat_date=stat_date,
        total_dwell_ms=_scaled_previous_value(scenario.dwell_ms, scale=scale),
        variant_changes=_scaled_previous_value(scenario.variant_changes, scale=scale),
        views=_scaled_previous_value(scenario.views, scale=scale),
    )


def _scaled_previous_distribution(values: dict[str, int], *, scale: float) -> dict[str, int]:
    return {key: _scaled_previous_value(value, scale=scale) for key, value in values.items()}


def _scaled_previous_value(value: int, *, scale: float) -> int:
    if value == 0:
        return 0
    return max(1, round(value * scale))


def _events_for_scenario(
    *,
    scenario: DemoProductScenario,
    occurred_at: datetime,
) -> list[IngestEvent]:
    events: list[IngestEvent] = []

    events.extend(
        _event(
            EventType.PRODUCT_IMPRESSION,
            occurred_at=occurred_at - timedelta(minutes=2),
            product_id=scenario.product_id,
            component_id="collection_card",
            context={"position": 0},
        )
        for _ in range(scenario.impressions)
    )
    events.extend(
        _event(
            EventType.PRODUCT_CLICK,
            occurred_at=occurred_at - timedelta(minutes=1),
            product_id=scenario.product_id,
            component_id="collection_card",
            context={"target_url": f"/products/{scenario.product_id}"},
        )
        for _ in range(scenario.clicks)
    )
    events.extend(
        _event(
            EventType.PRODUCT_VIEW,
            occurred_at=occurred_at,
            product_id=scenario.product_id,
            context={"page_type": "pdp"},
        )
        for _ in range(scenario.views)
    )
    events.extend(
        _event(EventType.ADD_TO_CART, occurred_at=occurred_at + timedelta(minutes=1), product_id=scenario.product_id)
        for _ in range(scenario.add_to_carts)
    )
    events.extend(
        _event(
            EventType.ORDER_COMPLETED,
            occurred_at=occurred_at + timedelta(minutes=2),
            product_id=scenario.product_id,
        )
        for _ in range(scenario.orders)
    )

    for component_id, count in scenario.component_clicks.items():
        events.extend(
            _event(
                EventType.COMPONENT_CLICK,
                occurred_at=occurred_at + timedelta(minutes=3),
                product_id=scenario.product_id,
                component_id=component_id,
            )
            for _ in range(count)
        )

    for component_id, count in scenario.component_impressions.items():
        events.extend(
            _event(
                EventType.COMPONENT_IMPRESSION,
                occurred_at=occurred_at + timedelta(minutes=3),
                product_id=scenario.product_id,
                component_id=component_id,
                context={"page_type": "pdp"},
            )
            for _ in range(count)
        )

    events.extend(
        _event(
            EventType.MEDIA_INTERACTION,
            occurred_at=occurred_at + timedelta(minutes=4),
            product_id=scenario.product_id,
            context={"action": "gallery"},
        )
        for _ in range(scenario.media_interactions)
    )
    events.extend(
        _event(
            EventType.VARIANT_INTENT,
            occurred_at=occurred_at + timedelta(minutes=5),
            product_id=scenario.product_id,
            context={"options": {"Size": "M"}},
        )
        for _ in range(scenario.variant_changes)
    )
    events.append(
        _event(
            EventType.ENGAGE,
            occurred_at=occurred_at + timedelta(minutes=6),
            product_id=scenario.product_id,
            context={
                "dwell_ms": scenario.dwell_ms,
                "max_scroll_pct": scenario.scroll_pct,
                "page_type": "pdp",
            },
        )
    )

    return events


def _event(
    event_type: EventType,
    *,
    occurred_at: datetime,
    product_id: str,
    component_id: str | None = None,
    context: dict[str, object] | None = None,
) -> IngestEvent:
    return IngestEvent(
        component_id=component_id,
        context=context or {},
        event_type=event_type,
        occurred_at=occurred_at,
        product_id=product_id,
    )


async def _clear_existing_demo_records(*, shop_domain: str) -> None:
    session = get_db_session()
    product_ids = tuple(scenario.product_id for scenario in SHOPIFY_ADMIN_SCENARIOS) + LEGACY_DEMO_PRODUCT_IDS

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
    scenarios_by_product_id = {scenario.product_id: scenario for scenario in SHOPIFY_ADMIN_SCENARIOS}

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
            scenario = scenarios_by_product_id[product_id]
            await diagnosis_service.store_generated_report(
                product_id=product_id,
                report_markdown=_report_markdown(
                    scenario=scenario,
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
        for scenario in SHOPIFY_ADMIN_SCENARIOS:
            await analysis_service.get_product_analysis(
                product_id=scenario.product_id,
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
    rows = (await get_db_session().exec(select(model).where(model.shop_id == shop_domain))).all()
    return len(rows)


def _dashboard_url(*, shop_domain: str, web_base_url: str) -> str:
    query = urlencode({"shop": shop_domain, "window": TimeWindow.HOURS_24.value})
    return f"{web_base_url}/?{query}"


def _report_markdown(
    *,
    scenario: DemoProductScenario,
    snapshot: ProductSnapshot,
    window: TimeWindow,
) -> str:
    return (
        "## Observed\n"
        f"{scenario.observed}\n\n"
        "## Evidence\n"
        f"Observed snapshot for {window.value}: {snapshot.views} views, "
        f"{snapshot.add_to_carts} add-to-carts, {snapshot.orders} orders, "
        f"{snapshot.clicks} clicks from {snapshot.impressions} impressions.\n\n"
        "## Suspected friction\n"
        f"{scenario.suspected_friction}\n\n"
        "## First fix to try\n"
        f"{scenario.first_fix}"
    )
