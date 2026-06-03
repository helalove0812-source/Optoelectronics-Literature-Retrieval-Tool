from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def within_lookback_window(value: datetime, hours: int) -> bool:
    return value >= utc_now() - timedelta(hours=hours)
