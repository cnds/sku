from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select

from db import get_db_session
from models import EventType, RawEvent
from repositories.analytics import AnalyticsRepository
from repositories.installations import InstallationRepository
from schemas import (
    IntegrationCheckStatus,
    IntegrationHealthCheck,
    IntegrationHealthCoverage,
    IntegrationHealthResponse,
    IntegrationHealthStatus,
    ProductSnapshot,
    TimeWindow,
)
from services.shop_time import local_date_for_shop, utc_bounds_for_shop_date


class IntegrationHealthService:
    def __init__(
        self,
        *,
        analytics_repository: AnalyticsRepository | None = None,
        installation_repository: InstallationRepository | None = None,
    ) -> None:
        self._analytics_repository = analytics_repository or AnalyticsRepository()
        self._installation_repository = installation_repository or InstallationRepository()

    async def get_health(
        self,
        *,
        shop_id: str,
        window: TimeWindow,
    ) -> IntegrationHealthResponse:
        installation = await self._installation_repository.get_by_shop_domain(shop_id)
        timezone_name = installation.timezone_name if installation is not None else None
        reference_date = self._reference_date_for_shop(timezone_name=timezone_name)
        snapshots = await self._analytics_repository.fetch_product_snapshots(
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
        )
        component_clicks = await self._pdp_component_clicks(
            shop_id=shop_id,
            window=window,
            reference_date=reference_date,
            timezone_name=timezone_name,
        )
        coverage = self._coverage_from_snapshots(
            snapshots,
            component_clicks=component_clicks,
        )
        last_event_at = await self._last_event_at(shop_id=shop_id)

        checks = [
            self._check(
                key="installation",
                label="Installation",
                ok=installation is not None,
                ok_message="Shop installation is connected.",
                missing_message="No shop installation record was found.",
            ),
            self._check(
                key="storefront_events",
                label="Storefront events",
                ok=last_event_at is not None,
                ok_message="Recent storefront events are reaching SKU Lens.",
                missing_message="No storefront events have reached SKU Lens yet.",
            ),
            self._check(
                key="pdp_views",
                label="PDP views",
                ok=coverage.views > 0,
                ok_message="PDP view tracking is present.",
                missing_message="No PDP view events are present for this window.",
            ),
            self._check(
                key="component_tracking",
                label="Component tracking",
                ok=coverage.component_clicks > 0,
                ok_message="PDP component interaction tracking is present.",
                missing_message="No PDP component interactions are present for this window.",
            ),
            self._check(
                key="buy_box_add_to_cart",
                label="Buy-box / add-to-cart",
                ok=coverage.add_to_carts > 0,
                ok_message="Add-to-cart coverage is present.",
                missing_message="No buy-box or add-to-cart events are present for this window.",
            ),
            self._check(
                key="orders_webhook",
                label="Orders / webhook",
                ok=coverage.orders > 0,
                ok_message="Order coverage is present.",
                missing_message="No Shopify order webhook events are present for this window.",
            ),
        ]

        if installation is None or last_event_at is None:
            status = IntegrationHealthStatus.NOT_CONNECTED
        elif all(check.status is IntegrationCheckStatus.OK for check in checks):
            status = IntegrationHealthStatus.HEALTHY
        else:
            status = IntegrationHealthStatus.PARTIAL

        return IntegrationHealthResponse(
            status=status,
            last_event_at=last_event_at,
            coverage=coverage,
            checks=checks,
        )

    @staticmethod
    def _coverage_from_snapshots(
        snapshots: dict[str, ProductSnapshot],
        *,
        component_clicks: int,
    ) -> IntegrationHealthCoverage:
        impressions = 0
        clicks = 0
        views = 0
        add_to_carts = 0
        orders = 0
        for snapshot in snapshots.values():
            impressions += snapshot.impressions
            clicks += snapshot.clicks
            views += snapshot.views
            add_to_carts += snapshot.add_to_carts
            orders += snapshot.orders

        return IntegrationHealthCoverage(
            impressions=impressions,
            clicks=clicks,
            views=views,
            component_clicks=component_clicks,
            add_to_carts=add_to_carts,
            orders=orders,
        )

    @staticmethod
    def _reference_date_for_shop(*, timezone_name: str | None) -> date:
        return local_date_for_shop(
            instant=datetime.now(UTC),
            timezone_name=timezone_name,
        )

    @staticmethod
    async def _pdp_component_clicks(
        *,
        shop_id: str,
        window: TimeWindow,
        reference_date: date,
        timezone_name: str | None,
    ) -> int:
        start_date = window.start_date_from_reference_date(reference_date=reference_date)
        start_utc, _ = utc_bounds_for_shop_date(
            local_date=start_date,
            timezone_name=timezone_name,
        )
        statement = (
            select(func.count())
            .select_from(RawEvent)
            .where(
                RawEvent.shop_id == shop_id,
                RawEvent.event_type == EventType.COMPONENT_CLICK,
                RawEvent.product_id.is_not(None),
                RawEvent.component_id.is_not(None),
                RawEvent.occurred_at >= start_utc,
            )
        )
        return int((await get_db_session().exec(statement)).one()[0] or 0)

    @staticmethod
    async def _last_event_at(*, shop_id: str) -> datetime | None:
        statement = select(func.max(RawEvent.occurred_at)).where(RawEvent.shop_id == shop_id)
        value = (await get_db_session().exec(statement)).one()[0]
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _check(
        *,
        key: str,
        label: str,
        ok: bool,
        ok_message: str,
        missing_message: str,
    ) -> IntegrationHealthCheck:
        return IntegrationHealthCheck(
            key=key,
            label=label,
            status=IntegrationCheckStatus.OK if ok else IntegrationCheckStatus.MISSING,
            message=ok_message if ok else missing_message,
        )
