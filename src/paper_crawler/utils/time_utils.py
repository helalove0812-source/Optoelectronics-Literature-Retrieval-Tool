from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def within_lookback_window(
    value: datetime, hours: int, now: datetime | None = None
) -> bool:
    reference = now or utc_now()
    return value >= reference - timedelta(hours=hours)
