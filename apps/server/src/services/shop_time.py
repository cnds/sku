from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_SHOP_TIMEZONE = "UTC"


def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timezone-aware datetime required.")
    return value.astimezone(UTC)


def normalize_shop_timezone(timezone_name: str | None) -> str:
    candidate = timezone_name or DEFAULT_SHOP_TIMEZONE
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return DEFAULT_SHOP_TIMEZONE
    return candidate


def local_date_for_shop(*, instant: datetime, timezone_name: str | None) -> date:
    timezone = ZoneInfo(normalize_shop_timezone(timezone_name))
    return ensure_utc_datetime(instant).astimezone(timezone).date()


def utc_bounds_for_shop_date(*, local_date: date, timezone_name: str | None) -> tuple[datetime, datetime]:
    timezone = ZoneInfo(normalize_shop_timezone(timezone_name))
    local_start = datetime.combine(local_date, time.min, tzinfo=timezone)
    local_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=timezone)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def rollup_due_at_utc(*, local_date: date, timezone_name: str | None) -> datetime:
    _, utc_end = utc_bounds_for_shop_date(local_date=local_date, timezone_name=timezone_name)
    return utc_end


def initial_last_completed_local_date(*, installed_at: datetime, timezone_name: str | None) -> date:
    return local_date_for_shop(instant=installed_at, timezone_name=timezone_name) - timedelta(days=1)
