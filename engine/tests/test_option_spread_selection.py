from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market_research_lab.market_data import (
    DailyBar,
    OptionContract,
    OptionMarketData,
    OptionTrade,
    UnderlyingMinuteBar,
)
from market_research_lab.option_spread_selection import (
    SelectionRules,
    previous_day_volume,
    pullback_passes,
    select_put_credit_spread,
    sma_trend_passes,
)

NEW_YORK = ZoneInfo("America/New_York")
ENTRY = datetime(2024, 1, 2, 10, 0, tzinfo=NEW_YORK)


def _daily_bar(day: date, close: float, available_at: str) -> DailyBar:
    return DailyBar(
        "SPY",
        day.isoformat(),
        close,
        close,
        close,
        close,
        1000.0,
        "test",
        available_at=available_at,
    )


def test_previous_day_volume_uses_only_trades_known_at_selection_time():
    contract = OptionContract(
        "short", "SPY", "2024-02-06", 95.0, "put", available_at="2024-01-01T14:00:00Z"
    )
    trades = (
        OptionTrade("short", "2024-01-01T15:00:00Z", 1.0, 70.0, "2024-01-01T15:01:00Z"),
        OptionTrade("short", "2024-01-01T15:01:00Z", 1.0, 50.0, "2024-01-02T16:00:00Z"),
    )
    data = OptionMarketData(contracts=(contract,), trades=trades)

    assert previous_day_volume(data, "SPY", ENTRY) == 70.0


def test_sma_trend_uses_completed_daily_bars_available_at_selection_time():
    start = date(2023, 5, 1)
    bars = tuple(
        _daily_bar(start + timedelta(days=index), 100.0 + index, "2024-01-01T14:00:00Z")
        for index in range(200)
    )
    future = _daily_bar(date(2024, 1, 1), 1.0, "2024-01-02T16:00:00Z")

    assert sma_trend_passes(bars + (future,), "SPY", ENTRY)
    assert not sma_trend_passes(bars[:199], "SPY", ENTRY)


def test_pullback_requires_two_confirmations_after_a_touch_of_the_200_sma():
    start = date(2023, 5, 1)
    daily = tuple(
        _daily_bar(start + timedelta(days=index), 100.0, "2024-01-01T14:00:00Z")
        for index in range(200)
    )
    closes = (100.0, 100.0, 100.0, 100.0, 100.0, 101.0, 101.0)
    bars = tuple(
        UnderlyingMinuteBar(
            "SPY",
            f"2024-01-02T14:{index:02d}:00Z",
            close,
            close,
            close,
            close,
            available_at=f"2024-01-02T14:{index + 1:02d}:00Z",
        )
        for index, close in enumerate(closes)
    )
    data = OptionMarketData(underlying_bars=bars, daily_bars=daily)

    assert pullback_passes(data, "SPY", ENTRY)
    assert not pullback_passes(
        OptionMarketData(underlying_bars=bars[:-1], daily_bars=daily), "SPY", ENTRY
    )


def _selection_rules() -> SelectionRules:
    return SelectionRules(
        dte_min=30,
        dte_max=45,
        delta_min=0.0,
        delta_max=1.0,
        target_delta=0.175,
        iv_min=0.0,
        iv_max=5.0,
        previous_day_volume_min=0.0,
        preferred_width=2.5,
        fallback_width=5.0,
        risk_free_rate=0.0,
        dividend_yield=0.0,
        automatic_selection=False,
    )


def _selection_data(
    *, expiration: str = "2024-02-06", available_at: str = "2024-01-02T14:00:00Z"
) -> OptionMarketData:
    contracts = (
        OptionContract(
            "preferred-short", "SPY", expiration, 95.0, "put", available_at=available_at
        ),
        OptionContract("preferred-long", "SPY", expiration, 92.5, "put", available_at=available_at),
        OptionContract("fallback-short", "SPY", expiration, 94.0, "put", available_at=available_at),
        OptionContract("fallback-long", "SPY", expiration, 89.0, "put", available_at=available_at),
    )
    trades = tuple(
        OptionTrade(
            contract_id,
            "2024-01-02T15:00:00Z",
            price,
            100.0,
            "2024-01-02T15:01:00Z",
        )
        for contract_id, price in (
            ("preferred-short", 2.0),
            ("preferred-long", 0.5),
            ("fallback-short", 1.5),
            ("fallback-long", 0.25),
        )
    )
    underlying = UnderlyingMinuteBar(
        "SPY",
        "2024-01-02T15:00:00Z",
        100.0,
        100.0,
        100.0,
        100.0,
        available_at="2024-01-02T15:01:00Z",
    )
    return OptionMarketData(contracts=contracts, trades=trades, underlying_bars=(underlying,))


def test_selection_prefers_the_configured_width():
    selected = select_put_credit_spread(
        _selection_rules(),
        market_data=_selection_data(),
        security_id="SPY",
        at=ENTRY,
    )

    assert selected is not None
    assert selected.short_contract.contract_id == "preferred-short"
    assert selected.width == 2.5


def test_selection_rejects_contracts_not_known_at_the_decision_time():
    selected = select_put_credit_spread(
        _selection_rules(),
        market_data=_selection_data(available_at="2024-01-02T16:00:00Z"),
        security_id="SPY",
        at=ENTRY,
    )

    assert selected is None


def test_selection_rejects_expirations_outside_the_dte_range():
    selected = select_put_credit_spread(
        _selection_rules(),
        market_data=_selection_data(expiration="2024-03-01"),
        security_id="SPY",
        at=ENTRY,
    )

    assert selected is None


def test_selection_rejects_short_contracts_outside_the_delta_band():
    rules = replace(_selection_rules(), delta_min=0.99, delta_max=1.0)

    selected = select_put_credit_spread(
        rules, market_data=_selection_data(), security_id="SPY", at=ENTRY
    )

    assert selected is None
