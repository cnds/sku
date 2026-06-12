from __future__ import annotations

from config import Settings
from repositories.installations import InstallationRepository
from schemas import (
    IntegrationCheckStatus,
    IntegrationHealthCheck,
    IntegrationHealthResponse,
    OnboardingChecklistItem,
    OnboardingChecklistStatus,
    OnboardingStatusResponse,
    TimeWindow,
)
from services.integration_health import IntegrationHealthService
from services.shopify import build_app_embed_deep_link, build_ingest_endpoint, normalize_shop_domain


class OnboardingStatusService:
    def __init__(
        self,
        settings: Settings,
        *,
        health_service: IntegrationHealthService | None = None,
        installation_repository: InstallationRepository | None = None,
    ) -> None:
        self._settings = settings
        self._health_service = health_service or IntegrationHealthService()
        self._installation_repository = installation_repository or InstallationRepository()

    async def get_status(
        self,
        *,
        shop_id: str,
        window: TimeWindow,
    ) -> OnboardingStatusResponse:
        shop_domain = normalize_shop_domain(shop_id)
        installation = await self._installation_repository.get_by_shop_domain(shop_domain)
        health = await self._health_service.get_health(shop_id=shop_domain, window=window)
        return OnboardingStatusResponse(
            shop_id=shop_domain,
            installed=installation is not None,
            public_token=installation.public_token if installation is not None else None,
            ingest_endpoint=build_ingest_endpoint(self._settings),
            app_embed_deep_link=build_app_embed_deep_link(
                settings=self._settings,
                shop_domain=shop_domain,
            ),
            integration_health=health,
            last_raw_event_at=health.last_event_at,
            checklist=self._checklist(health=health, installed=installation is not None),
        )

    @staticmethod
    def _checklist(
        *,
        health: IntegrationHealthResponse,
        installed: bool,
    ) -> list[OnboardingChecklistItem]:
        checks = {check.key: check for check in health.checks}
        return [
            OnboardingChecklistItem(
                key="install",
                label="Install SKU Lens",
                status=OnboardingChecklistStatus.DONE if installed else OnboardingChecklistStatus.ACTION,
                message=(
                    "Shop installation is connected."
                    if installed
                    else "Start the Shopify install flow before configuring the theme app embed."
                ),
            ),
            OnboardingStatusService._event_item(
                checks=checks,
                key="first_raw_event",
                label="Receive first raw event",
                source_key="storefront_events",
                pending_message="Open the storefront after enabling the app embed.",
            ),
            OnboardingStatusService._event_item(
                checks=checks,
                key="pdp_views",
                label="Track PDP views",
                source_key="pdp_views",
                pending_message="Visit a product detail page with the app embed enabled.",
            ),
            OnboardingStatusService._event_item(
                checks=checks,
                key="component_tracking",
                label="Track PDP component coverage",
                source_key="component_tracking",
                pending_message="Interact with product media, description, fit, or buy-box controls.",
            ),
            OnboardingStatusService._event_item(
                checks=checks,
                key="add_to_cart",
                label="Track add-to-cart coverage",
                source_key="buy_box_add_to_cart",
                pending_message="Use the product form add-to-cart path on a product page.",
            ),
            OnboardingStatusService._event_item(
                checks=checks,
                key="orders",
                label="Confirm order webhook coverage",
                source_key="orders_webhook",
                pending_message="Order coverage appears after Shopify order webhooks reach SKU Lens.",
            ),
        ]

    @staticmethod
    def _event_item(
        *,
        checks: dict[str, IntegrationHealthCheck],
        key: str,
        label: str,
        pending_message: str,
        source_key: str,
    ) -> OnboardingChecklistItem:
        check = checks.get(source_key)
        if check is not None and check.status == IntegrationCheckStatus.OK:
            return OnboardingChecklistItem(
                key=key,
                label=label,
                status=OnboardingChecklistStatus.DONE,
                message=check.message,
            )
        return OnboardingChecklistItem(
            key=key,
            label=label,
            status=(
                OnboardingChecklistStatus.ACTION if key == "component_tracking" else OnboardingChecklistStatus.PENDING
            ),
            message=pending_message,
        )
