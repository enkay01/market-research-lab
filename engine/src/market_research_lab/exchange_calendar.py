"""Deterministic exchange calendar functions for listed equities."""

from __future__ import annotations

import functools
from datetime import date, timedelta


def _to_date(value: date | str) -> date:
    """Normalize date or ISO date string into a date object."""
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _easter_date(year: int) -> date:
    """Calculate the date of Western Easter Sunday using the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    calendar_l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * calendar_l) // 451
    month = (h + calendar_l - 7 * m + 114) // 31
    day = ((h + calendar_l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed_date(fixed_date: date, *, observe_saturday_on_friday: bool = True) -> date:
    """Apply standard US exchange observation rules (Sunday -> Monday, Saturday -> Friday)."""
    weekday = fixed_date.weekday()
    if weekday == 6:  # Sunday
        return fixed_date + timedelta(days=1)
    if weekday == 5 and observe_saturday_on_friday:  # Saturday
        return fixed_date - timedelta(days=1)
    return fixed_date


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the n-th occurrence of weekday (0=Monday..6=Sunday) in the given year/month."""
    first_of_month = date(year, month, 1)
    first_weekday_offset = (weekday - first_of_month.weekday()) % 7
    day = 1 + first_weekday_offset + (n - 1) * 7
    return date(year, month, day)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of weekday in the given year/month."""
    if month == 12:
        last_of_month = date(year, 12, 31)
    else:
        last_of_month = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last_of_month.weekday() - weekday) % 7
    return last_of_month - timedelta(days=offset)


@functools.lru_cache(maxsize=64)
def get_us_exchange_holidays(year: int) -> set[date]:
    """Return the set of official US exchange (NYSE/NASDAQ) holidays for a given year."""
    holidays: set[date] = set()

    # 1. New Year's Day (Jan 1, observed Monday if Sunday)
    nyd = date(year, 1, 1)
    if nyd.weekday() == 6:
        holidays.add(date(year, 1, 2))
    elif nyd.weekday() != 5:
        holidays.add(nyd)

    # 2. Martin Luther King Jr. Day (3rd Monday in January, official NYSE holiday since 1998)
    if year >= 1998:
        holidays.add(_nth_weekday(year, 1, 0, 3))

    # 3. Washington's Birthday / Presidents' Day (3rd Monday in February)
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # 4. Good Friday (Friday before Easter)
    easter = _easter_date(year)
    holidays.add(easter - timedelta(days=2))

    # 5. Memorial Day (Last Monday in May)
    holidays.add(_last_weekday(year, 5, 0))

    # 6. Juneteenth National Independence Day (June 19, observed since 2021/2022)
    if year >= 2021:
        holidays.add(_observed_date(date(year, 6, 19)))

    # 7. Independence Day (July 4)
    holidays.add(_observed_date(date(year, 7, 4)))

    # 8. Labor Day (1st Monday in September)
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # 9. Thanksgiving Day (4th Thursday in November)
    holidays.add(_nth_weekday(year, 11, 3, 4))

    # 10. Christmas Day (December 25)
    holidays.add(_observed_date(date(year, 12, 25)))

    return holidays


def is_weekend(dt: date | str) -> bool:
    """Return True if the date is a Saturday or Sunday."""
    d = _to_date(dt)
    return d.weekday() in (5, 6)


def is_exchange_holiday(dt: date | str, exchange: str = "US") -> bool:
    """Return True if the date is an exchange holiday."""
    d = _to_date(dt)
    if exchange.upper() == "US":
        return d in get_us_exchange_holidays(d.year)
    return False


def is_trading_day(dt: date | str, exchange: str = "US") -> bool:
    """Return True if the date is an active trading session."""
    d = _to_date(dt)
    if is_weekend(d):
        return False
    if is_exchange_holiday(d, exchange=exchange):
        return False
    return True


def next_trading_day(session_date: str, exchange: str = "US") -> str:
    """Advance to the next active exchange trading day following session_date."""
    current = date.fromisoformat(session_date) + timedelta(days=1)
    while not is_trading_day(current, exchange=exchange):
        current += timedelta(days=1)
    return current.isoformat()


def previous_trading_day(session_date: str, exchange: str = "US") -> str:
    """Step back to the previous active exchange trading day before session_date."""
    current = date.fromisoformat(session_date) - timedelta(days=1)
    while not is_trading_day(current, exchange=exchange):
        current -= timedelta(days=1)
    return current.isoformat()


def get_trading_days(start_date: str, end_date: str, exchange: str = "US") -> list[str]:
    """Return a sorted list of all active trading session dates in [start_date, end_date]."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        return []

    days: list[str] = []
    current = start
    while current <= end:
        if is_trading_day(current, exchange=exchange):
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days
