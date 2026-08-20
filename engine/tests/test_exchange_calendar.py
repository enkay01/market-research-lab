"""Contract tests for exchange calendar and trading session calculations."""

from datetime import date

from market_research_lab.exchange_calendar import (
    get_trading_days,
    get_us_exchange_holidays,
    is_exchange_holiday,
    is_trading_day,
    is_weekend,
    next_trading_day,
    previous_trading_day,
)


def test_weekend_detection() -> None:
    """Saturdays and Sundays are detected as weekends."""
    assert is_weekend("2024-01-06")  # Saturday
    assert is_weekend("2024-01-07")  # Sunday
    assert not is_weekend("2024-01-05")  # Friday
    assert not is_weekend("2024-01-08")  # Monday


def test_us_exchange_holidays_2024() -> None:
    """All 10 US market holidays in 2024 are correctly identified."""
    holidays_2024 = get_us_exchange_holidays(2024)
    expected_2024 = {
        date(2024, 1, 1),  # New Year's Day
        date(2024, 1, 15),  # MLK Jr. Day (3rd Mon Jan)
        date(2024, 2, 19),  # Washington's Birthday (3rd Mon Feb)
        date(2024, 3, 29),  # Good Friday (Easter - 2 days)
        date(2024, 5, 27),  # Memorial Day (Last Mon May)
        date(2024, 6, 19),  # Juneteenth
        date(2024, 7, 4),  # Independence Day
        date(2024, 9, 2),  # Labor Day (1st Mon Sep)
        date(2024, 11, 28),  # Thanksgiving (4th Thu Nov)
        date(2024, 12, 25),  # Christmas Day
    }
    assert holidays_2024 == expected_2024


def test_holiday_observation_rules() -> None:
    """Sunday holidays shift to Monday; Saturday holidays shift to Friday."""
    # July 4, 2021 was a Sunday -> observed Monday July 5
    assert is_exchange_holiday("2021-07-05")
    assert not is_trading_day("2021-07-05")

    # December 25, 2021 was a Saturday -> observed Friday December 24
    assert is_exchange_holiday("2021-12-24")
    assert not is_trading_day("2021-12-24")

    # January 1, 2023 was a Sunday -> observed Monday January 2
    assert is_exchange_holiday("2023-01-02")
    assert not is_trading_day("2023-01-02")


def test_good_friday_computus_across_years() -> None:
    """Good Friday calculation matches official exchange closings across multiple years."""
    # 2023: Easter Apr 9 -> Good Friday Apr 7
    assert is_exchange_holiday("2023-04-07")
    # 2024: Easter Mar 31 -> Good Friday Mar 29
    assert is_exchange_holiday("2024-03-29")
    # 2025: Easter Apr 20 -> Good Friday Apr 18
    assert is_exchange_holiday("2025-04-18")


def test_next_trading_day_advances_across_weekends_and_holidays() -> None:
    """next_trading_day skips weekends and consecutive holidays."""
    # Regular weekday to next weekday
    assert next_trading_day("2024-01-02") == "2024-01-03"

    # Friday to Monday
    assert next_trading_day("2024-01-05") == "2024-01-08"

    # Friday before MLK holiday (Jan 12, 2024 -> Monday Jan 15 is holiday -> Tuesday Jan 16)
    assert next_trading_day("2024-01-12") == "2024-01-16"

    # Thursday before Good Friday (Mar 28, 2024 -> Friday Mar 29 holiday -> Monday Apr 1)
    assert next_trading_day("2024-03-28") == "2024-04-01"


def test_previous_trading_day() -> None:
    """previous_trading_day steps back skipping weekends and holidays."""
    # Monday to Friday
    assert previous_trading_day("2024-01-08") == "2024-01-05"

    # Tuesday after MLK holiday
    assert previous_trading_day("2024-01-16") == "2024-01-12"


def test_get_trading_days() -> None:
    """get_trading_days returns only valid trading sessions in the date window."""
    # Jan 1 to Jan 5, 2024 (Jan 1 is holiday)
    days = get_trading_days("2024-01-01", "2024-01-05")
    assert days == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    # Invalid inverted range returns empty list
    assert get_trading_days("2024-01-05", "2024-01-01") == []
