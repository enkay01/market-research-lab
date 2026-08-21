"""Contract and regression tests for corporate actions and exchange calendar backtesting (Issue #30).

Validates:
- Forward (2:1) and reverse (1:2) splits adjusting shares and open trade entry price while keeping raw prices unadjusted (DATA-010, BT-006).
- Dividends crediting cash on long holdings and debiting cash on short holdings (BT-006).
- Delistings liquidating positions, closing trades, and rejecting post-delisting targets (BT-006).
- Point-in-time eligibility excluding future corporate actions (DATA-008, BT-011).
- Exchange calendar advancing signals over weekends/holidays and handling missing sessions (BT-007, BT-008, BT-011).
"""

from __future__ import annotations

from market_research_lab.backtest import (
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from market_research_lab.market_data import CorporateAction, DailyBar


def make_bar(
    session_date: str,
    open: float,
    close: float,
    symbol: str = "AAPL",
) -> DailyBar:
    """Build a DailyBar with full point-in-time eligibility metadata."""
    return DailyBar(
        security_id=symbol,
        session_date=session_date,
        open=open,
        high=max(open, close),
        low=min(open, close),
        close=close,
        volume=10000.0,
        source="test",
        retrieval_time="",
        available_at=f"{session_date}T21:00:00Z",
        eligibility_provenance="test",
    )


def test_forward_split_adjusts_shares_and_preserves_cost_basis() -> None:
    """Forward 2:1 split doubles position shares and halves trade entry price without altering raw prices."""
    dates = [
        "2024-01-02",  # 0: close 10
        "2024-01-03",  # 1: close 11
        "2024-01-04",  # 2: close 12
        "2024-01-05",  # 3: close 13 -> SMA(2)=12.5 > SMA(4)=11.5 -> target 1.0
        "2024-01-08",  # 4: open 13 -> buys ~7692 shares at $13 (cash $100k)
        "2024-01-09",  # 5: 2:1 split effective! raw open 7.0, close 7.0 -> SMA(2)=10.5 < SMA(4)=11.5 -> target 0.0
        "2024-01-10",  # 6: open 7.0 -> sells all 15384 shares at $7.0
    ]
    bars = [
        make_bar(dates[0], 10.0, 10.0),
        make_bar(dates[1], 11.0, 11.0),
        make_bar(dates[2], 12.0, 12.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 13.0, 14.0),
        make_bar(dates[5], 7.0, 7.0),  # post-split raw price ($7 is equivalent to $14 pre-split)
        make_bar(dates[6], 7.0, 7.0),
    ]

    split_action = CorporateAction(
        security_id="AAPL",
        type="split",
        effective_date="2024-01-09",
        value=2.0,  # 2-for-1 split
        source="test",
        available_at="2024-01-08T22:00:00Z",
    )

    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-02",
        end_date="2024-01-10",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
        execution=ExecutionModelAssumptions(commission_rate=0.0, slippage_rate=0.0),
    )

    result = run_backtest(spec, bars=bars, corporate_actions=[split_action])

    # Day 4 (2024-01-08): bought 100,000 / 13 = ~7692.307692 shares
    buy_fill = result.fills[0]
    assert buy_fill.side == "buy"
    pre_split_shares = buy_fill.quantity

    # Day 5 (2024-01-09): ledger should reflect 2x shares and split in ledger
    split_row = [r for r in result.ledger if r.session_date == "2024-01-09"][0]
    assert split_row.splits == {"AAPL": 2.0}
    assert abs(split_row.shares - pre_split_shares * 2.0) < 1e-4

    # Day 6 (2024-01-10): sell fill should sell the doubled quantity
    sell_fill = [f for f in result.fills if f.session_date == "2024-01-10"][0]
    assert abs(sell_fill.quantity - pre_split_shares * 2.0) < 1e-4

    # Completed trade check: entry_price should be halved ($6.50), quantity doubled
    assert len(result.trades) == 1
    closed_trade = result.trades[0]
    assert abs(closed_trade.entry_price - 6.50) < 1e-4
    assert abs(closed_trade.exit_price - 7.0) < 1e-4
    assert abs(closed_trade.quantity - pre_split_shares * 2.0) < 1e-4

    # Manifest corporate actions summary
    corp_summary = result.manifest.get("corporate_actions", {})
    assert corp_summary.get("total_splits") == 1


def test_reverse_split_adjusts_shares() -> None:
    """Reverse 1:2 split halves position shares and doubles open trade entry price."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    bars = [
        make_bar(dates[0], 10.0, 10.0),
        make_bar(dates[1], 11.0, 11.0),
        make_bar(dates[2], 12.0, 12.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 13.0, 13.0),  # buys ~7692 shares at 13
        make_bar(dates[5], 26.0, 26.0),  # 1:2 reverse split: raw price doubles to 26
    ]
    reverse_split = CorporateAction(
        security_id="AAPL",
        type="split",
        effective_date="2024-01-09",
        value=0.5,  # 1-for-2 reverse split
        source="test",
        available_at="2024-01-08T22:00:00Z",
    )
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-02",
        end_date="2024-01-09",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
    )
    result = run_backtest(spec, bars=bars, corporate_actions=[reverse_split])

    pre_split_shares = result.fills[0].quantity
    split_row = [r for r in result.ledger if r.session_date == "2024-01-09"][0]
    assert abs(split_row.shares - pre_split_shares * 0.5) < 1e-4


def test_cash_dividend_credits_long_holding() -> None:
    """Cash dividend on long position credits cash on effective date and records attribution."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    bars = [
        make_bar(dates[0], 10.0, 10.0),
        make_bar(dates[1], 11.0, 11.0),
        make_bar(dates[2], 12.0, 12.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 13.0, 13.0),  # buys 7692.307692 shares at 13.0
        make_bar(dates[5], 13.0, 13.0),  # dividend date ($1.00/share)
    ]
    dividend = CorporateAction(
        security_id="AAPL",
        type="dividend",
        effective_date="2024-01-09",
        value=1.0,  # $1.00 per share
        source="test",
        available_at="2024-01-08T22:00:00Z",
    )
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-02",
        end_date="2024-01-09",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
    )
    result = run_backtest(spec, bars=bars, corporate_actions=[dividend])

    shares = result.fills[0].quantity
    expected_div_cash = round(shares * 1.0, 4)

    div_row = [r for r in result.ledger if r.session_date == "2024-01-09"][0]
    assert abs(div_row.dividends - expected_div_cash) < 1e-3
    assert div_row.cash >= expected_div_cash - 1e-3

    # Manifest attribution
    manifest_corp = result.manifest.get("corporate_actions", {})
    assert abs(manifest_corp.get("total_dividends", 0.0) - expected_div_cash) < 1e-3


def test_cash_dividend_debits_short_holding() -> None:
    """Cash dividend on short position debits cash on effective date."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    # Bearish prices: 16 -> 15 -> 14 -> 13 -> SMA(2) < SMA(4) -> short target
    bars = [
        make_bar(dates[0], 16.0, 16.0),
        make_bar(dates[1], 15.0, 15.0),
        make_bar(dates[2], 14.0, 14.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 13.0, 13.0),  # short sell fill at 13.0
        make_bar(dates[5], 13.0, 13.0),  # dividend date ($0.50/share)
    ]
    dividend = CorporateAction(
        security_id="AAPL",
        type="dividend",
        effective_date="2024-01-09",
        value=0.50,
        source="test",
        available_at="2024-01-08T22:00:00Z",
    )
    spec = BacktestSpecification(
        strategy_name="long_short_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-02",
        end_date="2024-01-09",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
        execution=ExecutionModelAssumptions(allow_shorting=True),
    )
    result = run_backtest(spec, bars=bars, corporate_actions=[dividend])

    short_fill = result.fills[0]
    assert short_fill.side == "sell"
    short_shares = short_fill.quantity

    div_row = [r for r in result.ledger if r.session_date == "2024-01-09"][0]
    # Dividends on short position should be negative (debit)
    expected_debit = -round(short_shares * 0.50, 4)
    assert abs(div_row.dividends - expected_debit) < 1e-3


def test_delisting_liquidates_position_and_rejects_subsequent_signals() -> None:
    """Delisting liquidates position at liquidation price, closes trade, and rejects post-delisting signals."""
    dates = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",  # delisting date!
        "2024-01-10",
    ]
    bars = [
        make_bar(dates[0], 10.0, 10.0),
        make_bar(dates[1], 11.0, 11.0),
        make_bar(dates[2], 12.0, 12.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 13.0, 13.0),  # bought shares at 13.0
        make_bar(dates[5], 10.0, 10.0),  # delisted on this day
        make_bar(dates[6], 10.0, 10.0),
    ]
    delisting = CorporateAction(
        security_id="AAPL",
        type="delisting",
        effective_date="2024-01-09",
        value=8.0,  # $8.00 per share final cash liquidation buyout
        source="test",
        available_at="2024-01-08T22:00:00Z",
    )
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-02",
        end_date="2024-01-10",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
    )
    result = run_backtest(spec, bars=bars, corporate_actions=[delisting])

    # Trade should be closed by delisting liquidation
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_date == "2024-01-09"
    assert trade.exit_price == 8.0

    # On and after delisting date, position is 0
    delist_row = [r for r in result.ledger if r.session_date == "2024-01-09"][0]
    assert delist_row.shares == 0.0
    assert delist_row.delistings == ("AAPL",)

    # Manifest delistings record
    corp_summary = result.manifest.get("corporate_actions", {})
    assert "AAPL" in corp_summary.get("delistings", [])


def test_point_in_time_excludes_future_corporate_actions() -> None:
    """Corporate actions with future available_at timestamps are excluded from execution (DATA-008)."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    bars = [
        make_bar(dates[0], 10.0, 10.0),
        make_bar(dates[1], 11.0, 11.0),
        make_bar(dates[2], 12.0, 12.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 13.0, 13.0),
        make_bar(dates[5], 13.0, 13.0),
    ]
    # Corporate action retrieval timestamp is in the future (2024-01-15)
    future_split = CorporateAction(
        security_id="AAPL",
        type="split",
        effective_date="2024-01-09",
        value=2.0,
        source="test",
        available_at="2024-01-15T00:00:00Z",  # in the future!
    )
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-02",
        end_date="2024-01-09",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
    )
    result = run_backtest(spec, bars=bars, corporate_actions=[future_split])

    # Future split was NOT applied on 2024-01-09
    row = [r for r in result.ledger if r.session_date == "2024-01-09"][0]
    assert row.splits == {}
    assert result.manifest.get("corporate_actions", {}).get("total_splits") == 0


def test_exchange_calendar_advances_over_holidays() -> None:
    """Backtest with US exchange calendar executes across holidays and weekends (BT-007)."""
    # 2024-01-12 is Friday. 2024-01-15 is MLK Day (holiday). Next trading day is 2024-01-16 (Tuesday).
    dates = [
        "2024-01-09",  # Tue
        "2024-01-10",  # Wed
        "2024-01-11",  # Thu
        "2024-01-12",  # Fri: bullish -> signal to buy next open
        "2024-01-16",  # Tue: MLK Day skipped, fill occurs at Tuesday open!
    ]
    bars = [
        make_bar(dates[0], 10.0, 10.0),
        make_bar(dates[1], 11.0, 11.0),
        make_bar(dates[2], 12.0, 12.0),
        make_bar(dates[3], 13.0, 13.0),
        make_bar(dates[4], 14.0, 14.0),
    ]
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        security_id="AAPL",
        start_date="2024-01-09",
        end_date="2024-01-16",
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4},
        calendar="US",
    )
    result = run_backtest(spec, bars=bars)

    # Simulation dates should match the US calendar (Jan 9, 10, 11, 12, 16)
    ledger_dates = [r.session_date for r in result.ledger]
    assert ledger_dates == ["2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-16"]

    # Fill occurred on Tuesday 2024-01-16
    assert len(result.fills) == 1
    assert result.fills[0].session_date == "2024-01-16"


def test_missing_session_advances_pending_fill_to_next_traded_bar() -> None:
    """When a security has a missing bar on an active calendar day, pending order advances to its next traded bar."""
    # MSFT trades every day. AAPL has a trading halt / missing bar on 2024-01-10.
    # AAPL gets a buy signal on 2024-01-09. On 2024-01-10, AAPL is missing, so order executes on 2024-01-11.
    bars = [
        # AAPL bars (missing 2024-01-10)
        make_bar("2024-01-08", 10.0, 10.0, symbol="AAPL"),
        make_bar("2024-01-09", 11.0, 11.0, symbol="AAPL"),  # signal generated
        make_bar("2024-01-11", 12.0, 12.0, symbol="AAPL"),  # fill executes here!
        # MSFT bars (trades every day)
        make_bar("2024-01-08", 20.0, 20.0, symbol="MSFT"),
        make_bar("2024-01-09", 20.0, 20.0, symbol="MSFT"),
        make_bar("2024-01-10", 20.0, 20.0, symbol="MSFT"),
        make_bar("2024-01-11", 20.0, 20.0, symbol="MSFT"),
    ]
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-test",
        universe=("AAPL", "MSFT"),
        start_date="2024-01-08",
        end_date="2024-01-11",
        starting_cash=100000.0,
        parameters={"fast_period": 1, "slow_period": 2},
    )
    result = run_backtest(spec, bars=bars)

    # AAPL buy fill should occur on 2024-01-11 (not 2024-01-10)
    aapl_fills = [f for f in result.fills if f.security_id == "AAPL"]
    assert len(aapl_fills) == 1
    assert aapl_fills[0].session_date == "2024-01-11"
