from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from repositories.installations import InstallationRepository
from services.rollups import DailyRollupService
from services.shop_time import (
    ensure_utc_datetime,
    initial_last_completed_local_date,
    local_date_for_shop,
    normalize_shop_timezone,
    rollup_due_at_utc,
)
from tasks.runtime import task_session_context

LOGGER = logging.getLogger(__name__)


async def run_due_shop_rollups(now_utc: datetime | None = None) -> int:
    reference = ensure_utc_datetime(now_utc or datetime.now(UTC))

    async with task_session_context():
        due_installations = await InstallationRepository().list_due_for_rollup(now_utc=reference)

    processed = 0
    for installation in due_installations:
        processed += await _process_due_shop_rollups(
            now_utc=reference,
            shop_domain=installation.shop_domain,
        )
    return processed


async def _process_due_shop_rollups(*, now_utc: datetime, shop_domain: str) -> int:
    async with task_session_context():
        installation = await InstallationRepository().get_by_shop_domain(shop_domain)
        if installation is None:
            return 0

        timezone_name = normalize_shop_timezone(installation.timezone_name)
        if installation.last_completed_local_date is None:
            installation.last_completed_local_date = initial_last_completed_local_date(
                installed_at=installation.installed_at,
                timezone_name=timezone_name,
            )

        local_today = local_date_for_shop(
            instant=now_utc,
            timezone_name=timezone_name,
        )
        processed = 0
        next_local_date = installation.last_completed_local_date + timedelta(days=1)

        while next_local_date < local_today:
            await DailyRollupService().rollup_day(
                shop_id=installation.shop_domain,
                stat_date=next_local_date,
                timezone_name=timezone_name,
            )
            installation.last_completed_local_date = next_local_date
            processed += 1
            next_local_date = installation.last_completed_local_date + timedelta(days=1)

        installation.next_rollup_at_utc = rollup_due_at_utc(
            local_date=installation.last_completed_local_date + timedelta(days=1),
            timezone_name=timezone_name,
        )
        if processed:
            LOGGER.info(
                "rollup backfill completed shop_domain=%s processed=%s",
                shop_domain,
                processed,
            )
        return processed
