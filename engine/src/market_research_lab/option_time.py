"""Time parsing shared by the options backtest seams."""

from datetime import datetime
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def parse_option_timestamp(value: str) -> datetime:
    """Parse an options timestamp and normalize it to New York time."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=NEW_YORK)
    return parsed.astimezone(NEW_YORK)


def option_minute(value: str) -> datetime:
    """Parse an options timestamp at minute precision."""
    return parse_option_timestamp(value).replace(second=0, microsecond=0)
