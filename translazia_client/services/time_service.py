from __future__ import annotations

from datetime import datetime, timezone, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re


MOSCOW_TZ_NAME = "Europe/Moscow"


def _timezone_moscow() -> tzinfo:
    try:
        return ZoneInfo(MOSCOW_TZ_NAME)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3), name="MSK")


MOSCOW_TZ = _timezone_moscow()


def now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def moscow_timezone_name() -> str:
    return MOSCOW_TZ_NAME if isinstance(MOSCOW_TZ, ZoneInfo) else "MSK"


def parse_hhmm(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", (value or "").strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute
