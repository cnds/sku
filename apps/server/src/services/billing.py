from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select

from config import Settings
from db import get_db_session
from models import BillingInterval, BillingPlan, BillingStatus, DailyProductStat, ShopInstallation, ShopSubscription
from repositories.billing import AiRefreshUsageRepository, SubscriptionRepository, ensure_aware
from repositories.installations import InstallationRepository
from schemas import BillingQuotaResponse, BillingStatusResponse, BillingSubscribeResponse, PdpViewsQuotaResponse
from services.plans import PLAN_CONFIGS, PLAN_RANK, TRIAL_DAYS, plan_matrix
from services.shopify import normalize_shop_domain

LOGGER = logging.getLogger(__name__)

APP_SUBSCRIPTION_CREATE_MUTATION = """
mutation AppSubscriptionCreate(
  $name: String!,
  $lineItems: [AppSubscriptionLineItemInput!]!,
  $returnUrl: URL!,
  $trialDays: Int,
  $replacementBehavior: AppSubscriptionReplacementBehavior,
  $test: Boolean
) {
  appSubscriptionCreate(
    name: $name,
    lineItems: $lineItems,
    returnUrl: $returnUrl,
    trialDays: $trialDays,
    replacementBehavior: $replacementBehavior,
    test: $test
  ) {
    userErrors { field message }
    appSubscription { id name status createdAt currentPeriodEnd }
    confirmationUrl
  }
}
"""

CURRENT_APP_SUBSCRIPTION_QUERY = """
query CurrentAppSubscription {
  currentAppInstallation {
    activeSubscriptions {
      id
      name
      status
      test
      createdAt
      currentPeriodEnd
      lineItems {
        plan {
          pricingDetails {
            __typename
            ... on AppRecurringPricing {
              interval
              price { amount currencyCode }
            }
          }
        }
      }
    }
  }
}
"""

APP_SUBSCRIPTION_CANCEL_MUTATION = """
mutation AppSubscriptionCancel($id: ID!, $prorate: Boolean) {
  appSubscriptionCancel(id: $id, prorate: $prorate) {
    userErrors { field message }
    appSubscription { id name status currentPeriodEnd }
  }
}
"""


class BillingError(Exception):
    pass


class BillingSubscriptionRequiredError(BillingError):
    def __init__(self) -> None:
        super().__init__("A paid subscription or active trial is required.")


class AiRefreshQuotaExceededError(BillingError):
    def __init__(self) -> None:
        super().__init__("AI refresh quota exceeded for the current billing period.")


class BillingShopNotInstalledError(BillingError):
    def __init__(self) -> None:
        super().__init__("Shop installation is required before billing can start.")


class ShopifyBillingError(BillingError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(slots=True)
class ShopifySubscriptionCreateResult:
    confirmation_url: str
    subscription_id: str | None


@dataclass(slots=True)
class ShopifyActiveSubscription:
    billing_interval: BillingInterval
    current_period_end: datetime | None
    name: str
    plan: BillingPlan
    shopify_subscription_id: str
    status: BillingStatus


class ShopifyBillingClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def create_subscription(
        self,
        *,
        access_token: str,
        billing_interval: BillingInterval,
        plan: BillingPlan,
        replacement_behavior: str,
        return_url: str,
        shop_domain: str,
        test: bool,
        trial_days: int,
    ) -> ShopifySubscriptionCreateResult:
        config = PLAN_CONFIGS[plan]
        amount = config.monthly_price
        interval = "EVERY_30_DAYS"
        if billing_interval is BillingInterval.ANNUAL:
            amount = config.annual_price_monthly_equivalent * 12
            interval = "ANNUAL"

        payload = await self._graphql(
            access_token=access_token,
            query=APP_SUBSCRIPTION_CREATE_MUTATION,
            shop_domain=shop_domain,
            variables={
                "lineItems": [
                    {
                        "plan": {
                            "appRecurringPricingDetails": {
                                "interval": interval,
                                "price": {"amount": amount, "currencyCode": "USD"},
                            }
                        }
                    }
                ],
                "name": config.name,
                "replacementBehavior": replacement_behavior,
                "returnUrl": return_url,
                "test": test,
                "trialDays": trial_days,
            },
        )
        mutation_payload = payload.get("data", {}).get("appSubscriptionCreate", {})
        self._raise_user_errors(mutation_payload, "Shopify subscription creation failed")
        app_subscription = mutation_payload.get("appSubscription") or {}
        return ShopifySubscriptionCreateResult(
            confirmation_url=str(mutation_payload.get("confirmationUrl") or ""),
            subscription_id=app_subscription.get("id"),
        )

    async def fetch_active_subscription(
        self,
        *,
        access_token: str,
        shop_domain: str,
    ) -> ShopifyActiveSubscription | None:
        payload = await self._graphql(
            access_token=access_token,
            query=CURRENT_APP_SUBSCRIPTION_QUERY,
            shop_domain=shop_domain,
            variables={},
        )
        subscriptions = payload.get("data", {}).get("currentAppInstallation", {}).get("activeSubscriptions") or []
        for subscription in subscriptions:
            if not isinstance(subscription, dict):
                continue
            parsed = self._active_subscription_from_payload(subscription)
            if parsed is not None:
                return parsed
        return None

    async def cancel_subscription(
        self,
        *,
        access_token: str,
        prorate: bool,
        shop_domain: str,
        subscription_id: str,
    ) -> None:
        payload = await self._graphql(
            access_token=access_token,
            query=APP_SUBSCRIPTION_CANCEL_MUTATION,
            shop_domain=shop_domain,
            variables={"id": subscription_id, "prorate": prorate},
        )
        mutation_payload = payload.get("data", {}).get("appSubscriptionCancel", {})
        self._raise_user_errors(mutation_payload, "Shopify subscription cancellation failed")

    def _active_subscription_from_payload(self, payload: dict[str, Any]) -> ShopifyActiveSubscription | None:
        plan = _plan_from_subscription_name(str(payload.get("name") or ""))
        if plan is None:
            return None

        return ShopifyActiveSubscription(
            billing_interval=_billing_interval_from_line_items(payload.get("lineItems") or []),
            current_period_end=_parse_shopify_datetime(payload.get("currentPeriodEnd")),
            name=str(payload.get("name") or PLAN_CONFIGS[plan].name),
            plan=plan,
            shopify_subscription_id=str(payload.get("id") or ""),
            status=_billing_status_from_shopify(str(payload.get("status") or "")),
        )

    async def _graphql(
        self,
        *,
        access_token: str,
        query: str,
        shop_domain: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient(timeout=20.0)
        should_close = self._http_client is None
        try:
            response = await client.post(
                f"https://{shop_domain}/admin/api/latest/graphql.json",
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": access_token,
                },
                json={"query": query, "variables": variables},
            )
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors")
            if errors:
                raise ShopifyBillingError(f"Shopify billing GraphQL failed: {errors}")
            return payload
        finally:
            if should_close:
                await client.aclose()

    @staticmethod
    def _raise_user_errors(payload: dict[str, Any], prefix: str) -> None:
        user_errors = payload.get("userErrors") or []
        if user_errors:
            messages = ", ".join(str(error.get("message", "Unknown error")) for error in user_errors)
            raise ShopifyBillingError(f"{prefix}: {messages}")


class UsageService:
    def __init__(self, repository: AiRefreshUsageRepository | None = None) -> None:
        self._repository = repository or AiRefreshUsageRepository()

    async def get_manual_refresh_count(self, *, period_key: str, shop_id: str) -> int:
        usage = await self._repository.get_usage(period_key=period_key, shop_id=shop_id)
        return usage.manual_refresh_count if usage is not None else 0

    async def increment_manual_refresh(self, *, period_key: str, shop_id: str) -> int:
        usage = await self._repository.increment(period_key=period_key, shop_id=shop_id)
        return usage.manual_refresh_count


class BillingService:
    def __init__(
        self,
        settings: Settings,
        *,
        billing_client: ShopifyBillingClient | None = None,
        installation_repository: InstallationRepository | None = None,
        subscription_repository: SubscriptionRepository | None = None,
        time_provider: Callable[[], datetime] | None = None,
        usage_service: UsageService | None = None,
    ) -> None:
        self._settings = settings
        self._billing_client = billing_client or ShopifyBillingClient(settings)
        self._installation_repository = installation_repository or InstallationRepository()
        self._subscription_repository = subscription_repository or SubscriptionRepository()
        self._time_provider = time_provider or (lambda: datetime.now(UTC))
        self._usage_service = usage_service or UsageService()

    async def get_status(self, *, shop_id: str) -> BillingStatusResponse:
        shop_domain = normalize_shop_domain(shop_id)
        installation = await self._installation_repository.get_by_shop_domain(shop_domain)
        subscription = await self._subscription_repository.get_by_shop_id(shop_domain)
        is_entitled = self._is_entitled(subscription)
        current_plan = subscription.current_plan if subscription is not None else None
        config = PLAN_CONFIGS.get(current_plan) if current_plan is not None else None
        period_key = self._period_key(subscription)
        used = await self._usage_service.get_manual_refresh_count(period_key=period_key, shop_id=shop_domain)
        ai_limit = config.ai_refresh_limit if is_entitled and config is not None else 0
        pdp_limit = config.pdp_view_soft_limit if is_entitled and config is not None else 0
        pdp_used = await self._pdp_views_for_period(shop_id=shop_domain, subscription=subscription)
        return BillingStatusResponse(
            ai_refresh=BillingQuotaResponse(
                limit=ai_limit,
                period_key=period_key,
                remaining=max(0, ai_limit - used),
                used=used,
            ),
            billing_interval=subscription.billing_interval if subscription is not None else None,
            current_period_ends_at=(
                ensure_aware(subscription.current_period_ends_at) if subscription is not None else None
            ),
            current_plan=current_plan,
            installed=installation is not None,
            is_entitled=is_entitled,
            pdp_views=PdpViewsQuotaResponse(
                limit=pdp_limit,
                over_limit=pdp_limit > 0 and pdp_used > pdp_limit,
                used=pdp_used,
            ),
            pending_effective_at=ensure_aware(subscription.pending_effective_at) if subscription is not None else None,
            pending_plan=subscription.pending_plan if subscription is not None else None,
            plans=plan_matrix(),
            shop_id=shop_domain,
            subscription_status=subscription.status if subscription is not None else BillingStatus.UNSUBSCRIBED,
            trial_ends_at=ensure_aware(subscription.trial_ends_at) if subscription is not None else None,
        )

    async def subscribe(
        self,
        *,
        billing_interval: BillingInterval,
        plan: BillingPlan,
        shop_id: str,
    ) -> BillingSubscribeResponse:
        shop_domain = normalize_shop_domain(shop_id)
        installation = await self._require_installation(shop_domain)
        replacement_behavior = await self._replacement_behavior(
            billing_interval=billing_interval,
            plan=plan,
            shop_id=shop_domain,
        )
        trial_days = TRIAL_DAYS if replacement_behavior == "STANDARD" else 0
        result = await self._billing_client.create_subscription(
            access_token=installation.access_token or "",
            billing_interval=billing_interval,
            plan=plan,
            replacement_behavior=replacement_behavior,
            return_url=self._billing_return_url(shop_domain),
            shop_domain=shop_domain,
            test=self._settings.shopify_billing_test,
            trial_days=trial_days,
        )
        await self._record_requested_subscription(
            billing_interval=billing_interval,
            plan=plan,
            replacement_behavior=replacement_behavior,
            shop_id=shop_domain,
            shopify_subscription_id=result.subscription_id,
        )
        return BillingSubscribeResponse(
            billing_interval=billing_interval,
            confirmation_url=result.confirmation_url,
            plan=plan,
            replacement_behavior=replacement_behavior,
        )

    async def sync_from_shopify(self, *, shop_id: str) -> ShopSubscription:
        shop_domain = normalize_shop_domain(shop_id)
        installation = await self._require_installation(shop_domain)
        active = await self._billing_client.fetch_active_subscription(
            access_token=installation.access_token or "",
            shop_domain=shop_domain,
        )
        subscription = await self._subscription_repository.get_by_shop_id(shop_domain)
        if subscription is None:
            subscription = ShopSubscription(shop_id=shop_domain)

        now = self._now()
        if active is None:
            subscription.status = BillingStatus.EXPIRED
            await self._subscription_repository.save(subscription)
            return subscription

        pending_plan = subscription.pending_plan
        pending_effective_at = subscription.pending_effective_at

        subscription.current_plan = active.plan
        subscription.status = active.status
        subscription.billing_interval = active.billing_interval
        subscription.shopify_subscription_id = active.shopify_subscription_id
        subscription.current_period_started_at = subscription.current_period_started_at or now
        subscription.current_period_ends_at = active.current_period_end
        if pending_plan is not None and pending_plan is not active.plan:
            subscription.pending_plan = pending_plan
            subscription.pending_effective_at = pending_effective_at or active.current_period_end
        else:
            subscription.pending_plan = None
            subscription.pending_effective_at = None
        if active.status is BillingStatus.TRIALING:
            subscription.trial_started_at = subscription.trial_started_at or now
            subscription.trial_ends_at = active.current_period_end
        await self._subscription_repository.save(subscription)
        return subscription

    async def cancel(self, *, prorate: bool, shop_id: str) -> None:
        shop_domain = normalize_shop_domain(shop_id)
        installation = await self._require_installation(shop_domain)
        subscription = await self._subscription_repository.get_by_shop_id(shop_domain)
        if subscription is None or not subscription.shopify_subscription_id:
            raise BillingSubscriptionRequiredError()
        await self._billing_client.cancel_subscription(
            access_token=installation.access_token or "",
            prorate=prorate,
            shop_domain=shop_domain,
            subscription_id=subscription.shopify_subscription_id,
        )
        subscription.status = BillingStatus.CANCELLED
        await self._subscription_repository.save(subscription)

    async def consume_manual_ai_refresh(self, *, shop_id: str) -> None:
        status = await self.get_status(shop_id=shop_id)
        if not status.is_entitled:
            raise BillingSubscriptionRequiredError()
        if status.ai_refresh.remaining <= 0:
            raise AiRefreshQuotaExceededError()
        await self._usage_service.increment_manual_refresh(
            period_key=status.ai_refresh.period_key,
            shop_id=status.shop_id,
        )

    async def _require_installation(self, shop_domain: str) -> ShopInstallation:
        installation = await self._installation_repository.get_by_shop_domain(shop_domain)
        if installation is None or not installation.access_token:
            raise BillingShopNotInstalledError()
        return installation

    async def _replacement_behavior(
        self,
        *,
        billing_interval: BillingInterval,
        plan: BillingPlan,
        shop_id: str,
    ) -> str:
        subscription = await self._subscription_repository.get_by_shop_id(shop_id)
        if subscription is None or subscription.current_plan is None or not self._is_entitled(subscription):
            return "STANDARD"
        if _is_upgrade(
            current_interval=subscription.billing_interval,
            current_plan=subscription.current_plan,
            next_interval=billing_interval,
            next_plan=plan,
        ):
            return "APPLY_IMMEDIATELY"
        return "APPLY_ON_NEXT_BILLING_CYCLE"

    async def _record_requested_subscription(
        self,
        *,
        billing_interval: BillingInterval,
        plan: BillingPlan,
        replacement_behavior: str,
        shop_id: str,
        shopify_subscription_id: str | None,
    ) -> None:
        subscription = await self._subscription_repository.get_by_shop_id(shop_id)
        if subscription is None:
            subscription = ShopSubscription(shop_id=shop_id)

        if replacement_behavior == "APPLY_ON_NEXT_BILLING_CYCLE" and subscription.current_plan is not None:
            subscription.pending_plan = plan
            subscription.pending_effective_at = subscription.current_period_ends_at
        else:
            subscription.pending_plan = plan
            subscription.pending_effective_at = None
            if subscription.current_plan is None:
                subscription.status = BillingStatus.UNSUBSCRIBED

        subscription.shopify_subscription_id = shopify_subscription_id or subscription.shopify_subscription_id
        await self._subscription_repository.save(subscription)

    def _period_key(self, subscription: ShopSubscription | None) -> str:
        start = ensure_aware(subscription.current_period_started_at) if subscription is not None else None
        return (start or self._now()).strftime("%Y-%m")

    async def _pdp_views_for_period(self, *, shop_id: str, subscription: ShopSubscription | None) -> int:
        start = ensure_aware(subscription.current_period_started_at) if subscription is not None else None
        if start is None:
            return 0
        statement = select(func.coalesce(func.sum(DailyProductStat.views), 0)).where(
            DailyProductStat.shop_id == shop_id,
            DailyProductStat.stat_date >= start.date(),
        )
        return int((await get_db_session().exec(statement)).one()[0] or 0)

    def _billing_return_url(self, shop_domain: str) -> str:
        query = urlencode({"shop": shop_domain})
        return f"{self._settings.shopify_webhook_base_url.rstrip('/')}/shopify/billing/callback?{query}"

    def _is_entitled(self, subscription: ShopSubscription | None) -> bool:
        if subscription is None or subscription.current_plan is None:
            return False
        period_end = ensure_aware(subscription.current_period_ends_at)
        if subscription.status is BillingStatus.CANCELLED:
            return period_end is not None and period_end >= self._now()
        if subscription.status not in {BillingStatus.ACTIVE, BillingStatus.TRIALING}:
            return False
        if period_end is not None and period_end < self._now():
            return False
        trial_end = ensure_aware(subscription.trial_ends_at)
        if subscription.status is BillingStatus.TRIALING and trial_end is not None and trial_end < self._now():
            return False
        return True

    def _now(self) -> datetime:
        value = self._time_provider()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _plan_from_subscription_name(name: str) -> BillingPlan | None:
    normalized = name.strip().lower()
    for plan, config in PLAN_CONFIGS.items():
        if normalized == config.name.lower():
            return plan
    return None


def _billing_interval_from_line_items(line_items: list[Any]) -> BillingInterval:
    for line_item in line_items:
        pricing = (
            line_item.get("plan", {}).get("pricingDetails", {})
            if isinstance(line_item, dict)
            else {}
        )
        if pricing.get("interval") == "ANNUAL":
            return BillingInterval.ANNUAL
    return BillingInterval.MONTHLY


def _billing_status_from_shopify(value: str) -> BillingStatus:
    normalized = value.strip().upper()
    if normalized in {"ACTIVE", "ACCEPTED"}:
        return BillingStatus.ACTIVE
    if normalized in {"PENDING", "TRIALING"}:
        return BillingStatus.TRIALING
    if normalized == "FROZEN":
        return BillingStatus.FROZEN
    if normalized == "CANCELLED":
        return BillingStatus.CANCELLED
    if normalized == "EXPIRED":
        return BillingStatus.EXPIRED
    return BillingStatus.ACTIVE


def _parse_shopify_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _is_upgrade(
    *,
    current_interval: BillingInterval | None,
    current_plan: BillingPlan,
    next_interval: BillingInterval,
    next_plan: BillingPlan,
) -> bool:
    if next_interval is BillingInterval.ANNUAL and current_interval is BillingInterval.MONTHLY:
        return True
    if next_interval is BillingInterval.MONTHLY and current_interval is BillingInterval.ANNUAL:
        return False
    return PLAN_RANK[next_plan] > PLAN_RANK[current_plan]
