from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from models import ShopInstallation
from repositories.installations import InstallationRepository
from services.shop_time import (
    initial_last_completed_local_date,
    normalize_shop_timezone,
    rollup_due_at_utc,
)


class ShopInstallationService:
    def __init__(
        self,
        repository: InstallationRepository | None = None,
        *,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository or InstallationRepository()
        self._time_provider = time_provider or (lambda: datetime.now(UTC))

    async def upsert_installation(
        self,
        *,
        shop_domain: str,
        public_token: str,
        access_token: str | None,
        timezone_name: str | None = None,
    ) -> ShopInstallation:
        normalized_timezone = normalize_shop_timezone(timezone_name)
        existing = await self._repository.get_by_shop_domain(shop_domain)
        timezone_changed = (
            normalize_shop_timezone(existing.timezone_name if existing is not None else None)
            != normalized_timezone
        )
        installation = await self._repository.upsert(
            shop_domain=shop_domain,
            public_token=public_token,
            access_token=access_token,
            timezone_name=normalized_timezone,
        )
        if (
            installation.last_completed_local_date is None
            or installation.next_rollup_at_utc is None
            or timezone_changed
        ):
            installation.last_completed_local_date = initial_last_completed_local_date(
                installed_at=installation.installed_at,
                timezone_name=normalized_timezone,
            )
            installation.next_rollup_at_utc = rollup_due_at_utc(
                local_date=installation.last_completed_local_date + timedelta(days=1),
                timezone_name=normalized_timezone,
            )
        return installation

    async def get_by_shop_domain(self, shop_domain: str) -> ShopInstallation | None:
        return await self._repository.get_by_shop_domain(shop_domain)
