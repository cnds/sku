from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select

from db import get_db_session
from models import AiRefreshUsage, ShopSubscription


def ensure_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class SubscriptionRepository:
    async def get_by_shop_id(self, shop_id: str) -> ShopSubscription | None:
        return (
            await get_db_session().exec(select(ShopSubscription).where(ShopSubscription.shop_id == shop_id))
        ).first()

    async def save(self, subscription: ShopSubscription) -> ShopSubscription:
        subscription.updated_at = datetime.now(UTC)
        get_db_session().add(subscription)
        return subscription


class AiRefreshUsageRepository:
    async def get_usage(self, *, period_key: str, shop_id: str) -> AiRefreshUsage | None:
        return (
            await get_db_session().exec(
                select(AiRefreshUsage).where(
                    AiRefreshUsage.shop_id == shop_id,
                    AiRefreshUsage.period_key == period_key,
                )
            )
        ).first()

    async def increment(self, *, period_key: str, shop_id: str) -> AiRefreshUsage:
        usage = await self.get_usage(period_key=period_key, shop_id=shop_id)
        if usage is None:
            usage = AiRefreshUsage(shop_id=shop_id, period_key=period_key, manual_refresh_count=0)
            get_db_session().add(usage)
        usage.manual_refresh_count += 1
        usage.updated_at = datetime.now(UTC)
        return usage
