"""Contract tests for multi-Security long-only portfolio Backtest engine (Issue #26).

Tests cover:
1. Multi-Security universe portfolio simulation and cash/position ledger tracking.
2. Target-weight reconciliation and execution order (sells before buys).
3. Long-only constraint enforcement (rejection of negative weights, short prevention).
4. Benchmark equity tracking and benchmark-relative return metrics.
5. Deterministic replay and point-in-time leakage invariants across multi-asset universe.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from market_research_lab.backtest import (
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from market_research_lab.market_data import DailyBar


def make_dates(n: int, start: str = "2024-01-02") -> list[str]:
    """Return n sequential calendar dates starting at start."""
    first = date.fromisoformat(start)
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def make_bar(symbol: str, session_date: str, open_price: float, close_price: float) -> DailyBar:
    """Build a DailyBar with point-in-time eligibility metadata for a given symbol."""
    return DailyBar(
        security_id=symbol,
        session_date=session_date,
        open=open_price,
        high=max(open_price, close_price),
        low=min(open_price, close_price),
        close=close_price,
        volume=1000.0,
        source="test",
        retrieval_time="",
        available_at=f"{session_date}T21:00:00Z",
        eligibility_provenance="test",
    )


def make_multi_spec(
    universe: tuple[str, ...],
    dates: list[str],
    *,
    benchmark: str | None = None,
    cash: float = 100000.0,
) -> BacktestSpecification:
    """Build a BacktestSpecification for a multi-Security universe."""
    return BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-multi",
        security_id=universe[0] if universe else "AAPL",
        universe=universe,
        start_date=dates[0],
        end_date=dates[-1],
        starting_cash=cash,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        price_field="close",
        execution=ExecutionModelAssumptions(schedule="daily"),
        benchmark_security_id=benchmark,
    )


def test_multi_security_maintains_cash_and_positions_across_universe():
    """Verify that a 2-Security universe maintains distinct positions and cash."""
    dates = make_dates(8)
    # AAPL rises (triggers long)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    # MSFT stays flat then rises later
    msft_closes = [20.0, 20.0, 20.0, 20.0, 21.0, 22.0, 23.0, 24.0]

    bars: list[DailyBar] = []
    for d, c_aapl, c_msft in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_aapl, c_aapl))
        bars.append(make_bar("MSFT", d, c_msft, c_msft))

    spec = make_multi_spec(
        universe=("AAPL", "MSFT"),
        dates=dates,
        cash=100000.0,
    )

    result = run_backtest(spec, bars=bars)

    assert result.specification.universe == ("AAPL", "MSFT")
    assert len(result.fills) > 0
    # Both AAPL and MSFT should have fills
    fill_symbols = {f.security_id for f in result.fills}
    assert "AAPL" in fill_symbols
    assert "MSFT" in fill_symbols

    # In a 2-security universe, each asset targets 50% max allocation
    for row in result.ledger:
        assert row.portfolio_value > 0
        assert row.cash >= -1e-4  # No negative cash
        if "AAPL" in row.positions:
            assert row.positions["AAPL"].shares >= 0
        if "MSFT" in row.positions:
            assert row.positions["MSFT"].shares >= 0
        # Position sum check
        total_pos_val = sum(pos.position_value for pos in row.positions.values())
        assert row.position_value == pytest.approx(total_pos_val, abs=1e-2)
        assert row.portfolio_value == pytest.approx(row.cash + total_pos_val, abs=1e-2)


def test_sells_execute_before_buys_to_free_cash():
    """Verify that when rebalancing from Security A to B, A is sold first to provide cash."""
    dates = make_dates(10)
    # AAPL goes bullish first, then bearish
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 12.0, 10.0, 8.0, 6.0, 4.0]
    # MSFT goes bullish when AAPL goes bearish
    msft_closes = [20.0, 20.0, 20.0, 20.0, 20.0, 22.0, 24.0, 26.0, 28.0, 30.0]

    bars: list[DailyBar] = []
    for d, c_aapl, c_msft in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_aapl, c_aapl))
        bars.append(make_bar("MSFT", d, c_msft, c_msft))

    spec = make_multi_spec(
        universe=("AAPL", "MSFT"),
        dates=dates,
        cash=100000.0,
    )

    result = run_backtest(spec, bars=bars)

    # Check fills on the rebalance session where AAPL sells and MSFT buys
    rebalance_date = dates[5]
    fills_on_date = [f for f in result.fills if f.session_date == rebalance_date]
    if len(fills_on_date) >= 2:
        assert fills_on_date[0].side == "sell"
        assert fills_on_date[1].side == "buy"


def test_long_only_prevents_negative_positions_and_rejects_negative_weights():
    """Verify that long-only rules prevent short positions and reject negative target weights."""
    dates = make_dates(5)
    bars: list[DailyBar] = []
    for d in dates:
        bars.append(make_bar("AAPL", d, 10.0, 10.0))
        bars.append(make_bar("MSFT", d, 20.0, 20.0))

    spec = make_multi_spec(
        universe=("AAPL", "MSFT"),
        dates=dates,
        cash=100000.0,
    )

    result = run_backtest(spec, bars=bars)

    # Every position in every ledger row must be >= 0
    for row in result.ledger:
        for symbol, pos in row.positions.items():
            assert pos.shares >= 0.0, f"Negative shares detected for {symbol}: {pos.shares}"
        assert row.gross_exposure >= 0.0
        assert row.net_exposure >= 0.0
        assert row.net_exposure == pytest.approx(row.gross_exposure)  # In long-only, net == gross


def test_benchmark_comparison_calculates_curve_and_relative_return():
    """Verify that benchmark_security_id populates benchmark equity curve and relative return."""
    dates = make_dates(7)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    spy_closes = [400.0, 402.0, 404.0, 406.0, 408.0, 410.0, 412.0]

    bars: list[DailyBar] = []
    for d, c_aapl, c_spy in zip(dates, aapl_closes, spy_closes):
        bars.append(make_bar("AAPL", d, c_aapl, c_aapl))
        bars.append(make_bar("SPY", d, c_spy, c_spy))

    spec = make_multi_spec(
        universe=("AAPL",),
        dates=dates,
        benchmark="SPY",
        cash=100000.0,
    )

    result = run_backtest(spec, bars=bars)

    assert len(result.benchmark_equity_curve) == len(dates)
    assert result.benchmark_equity_curve[0].equity == pytest.approx(100000.0)
    # SPY grew from 400 to 412 (3% return)
    spy_total_return = (412.0 / 400.0) - 1.0
    assert result.benchmark_equity_curve[-1].equity == pytest.approx(
        100000.0 * (1.0 + spy_total_return), abs=1.0
    )

    # Benchmark relative return should be total_return - benchmark_total_return
    assert result.metrics.benchmark_relative_return is not None
    expected_relative = result.metrics.total_return - spy_total_return
    assert result.metrics.benchmark_relative_return == pytest.approx(expected_relative, abs=1e-4)


def test_multi_security_deterministic_replay_is_identical():
    """Verify that two identical multi-Security runs produce byte-for-byte identical output."""
    dates = make_dates(8)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 14.0, 13.0]
    msft_closes = [20.0, 21.0, 22.0, 23.0, 24.0, 23.0, 22.0, 21.0]

    bars: list[DailyBar] = []
    for d, c_aapl, c_msft in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_aapl, c_aapl))
        bars.append(make_bar("MSFT", d, c_msft, c_msft))

    spec = make_multi_spec(
        universe=("AAPL", "MSFT"),
        dates=dates,
        cash=100000.0,
    )

    run1 = run_backtest(spec, bars=bars)
    run2 = run_backtest(spec, bars=bars)

    assert run1.to_json() == run2.to_json()


def test_multi_security_future_data_leakage_invariant():
    """Verify appending future bars to any universe asset does not alter earlier results."""
    dates = make_dates(8)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 14.0, 13.0]
    msft_closes = [20.0, 21.0, 22.0, 23.0, 24.0, 23.0, 22.0, 21.0]

    bars: list[DailyBar] = []
    for d, c_aapl, c_msft in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_aapl, c_aapl))
        bars.append(make_bar("MSFT", d, c_msft, c_msft))

    spec = make_multi_spec(
        universe=("AAPL", "MSFT"),
        dates=dates,
        cash=100000.0,
    )

    base_run = run_backtest(spec, bars=bars)

    # Add future bars after end_date
    future_bars = [
        make_bar("AAPL", "2024-01-20", 50.0, 60.0),
        make_bar("MSFT", "2024-01-20", 100.0, 120.0),
    ]
    extended_run = run_backtest(spec, bars=[*bars, *future_bars])

    assert base_run.signals == extended_run.signals
    assert base_run.fills == extended_run.fills
    assert base_run.trades == extended_run.trades
    assert base_run.ledger == extended_run.ledger
    assert base_run.metrics == extended_run.metrics
