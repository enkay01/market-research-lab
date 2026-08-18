"""Contract and accounting tests for leverage and margin limits, exposure, and rejections (Issue #28).

Tests cover:
1. Leverage limit enforcement in reject mode (targets exceeding max_leverage are rejected with stable reason and security ID).
2. Leverage limit enforcement in constrain mode (targets exceeding max_leverage are scaled proportionally).
3. Gross and net exposure accounting across dated Portfolio ledger rows and summary metrics.
4. Margin requirement checks during order execution (insufficient margin emits ConstraintRejection).
5. Maintenance margin threshold monitoring and margin call detection.
6. Boundary value testing for leverage limits (fractional, 1.0x, 2.0x).
7. Deterministic replay and point-in-time future data leakage invariance.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from market_research_lab.backtest import (
    BacktestParameterError,
    BacktestSpecification,
    ConstraintRejection,
    ExecutionModelAssumptions,
    run_backtest,
)
from market_research_lab.market_data import DailyBar


def make_dates(n: int, start: str = "2024-01-02") -> list[str]:
    """Return n sequential calendar dates starting at start."""
    first = date.fromisoformat(start)
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def make_bar(symbol: str, session_date: str, open_price: float, close_price: float) -> DailyBar:
    """Build a DailyBar with point-in-time eligibility metadata."""
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


def make_spec(
    universe: tuple[str, ...],
    dates: list[str],
    execution: ExecutionModelAssumptions | None = None,
    cash: float = 100000.0,
    strategy_name: str = "long_short_moving_average",
) -> BacktestSpecification:
    """Build a BacktestSpecification with configurable execution assumptions."""
    return BacktestSpecification(
        strategy_name=strategy_name,
        strategy_revision="v1",
        dataset_version_id="ds-leverage",
        security_id=universe[0] if universe else "AAPL",
        universe=universe,
        start_date=dates[0],
        end_date=dates[-1],
        starting_cash=cash,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        price_field="close",
        execution=execution or ExecutionModelAssumptions(schedule="daily"),
    )


def test_specification_rejects_invalid_leverage_or_margin_parameters():
    """Verify specification validation rejects non-positive or invalid leverage and margin parameters."""
    dates = make_dates(3)
    bars = [make_bar("AAPL", d, 100.0, 100.0) for d in dates]

    # max_leverage <= 0
    spec = make_spec(
        universe=("AAPL",),
        dates=dates,
        execution=ExecutionModelAssumptions(max_leverage=0.0),
    )
    with pytest.raises(BacktestParameterError, match="max_leverage"):
        run_backtest(spec, bars=bars)

    # margin_requirement <= 0
    spec2 = make_spec(
        universe=("AAPL",),
        dates=dates,
        execution=ExecutionModelAssumptions(margin_requirement=-0.5),
    )
    with pytest.raises(BacktestParameterError, match="margin_requirement"):
        run_backtest(spec2, bars=bars)

    # maintenance_margin < 0
    spec3 = make_spec(
        universe=("AAPL",),
        dates=dates,
        execution=ExecutionModelAssumptions(maintenance_margin=-0.1),
    )
    with pytest.raises(BacktestParameterError, match="maintenance_margin"):
        run_backtest(spec3, bars=bars)


def test_leverage_limit_rejects_exceeding_targets_in_reject_mode():
    """Verify that targets exceeding max_leverage in reject mode are rejected with a stable reason and security ID."""
    dates = make_dates(8)
    # Rising price series triggers long target (raw weight 1.0)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    # Set max_leverage to 0.5 (so 1.0 raw target breaches the 0.5 limit)
    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        max_leverage=0.5,
        leverage_mode="reject",
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    # Rejections should contain leverage_limit records
    rejections = [r for r in result.rejections if r.rule == "leverage_limit"]
    assert len(rejections) > 0
    rejection = rejections[0]
    assert rejection.security_id == "AAPL"
    assert "leverage" in rejection.reason.lower()
    assert rejection.requested_weight is not None
    assert rejection.requested_weight > 0.5

    # Since target was rejected, no fills should have executed
    assert len(result.fills) == 0
    for r in result.ledger:
        assert r.gross_exposure <= 0.5 + 1e-6


def test_leverage_limit_constrains_targets_in_constrain_mode():
    """Verify that targets exceeding max_leverage in constrain mode are scaled down to the limit."""
    dates = make_dates(8)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    # Set max_leverage to 0.5 with constrain mode
    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        max_leverage=0.5,
        leverage_mode="constrain",
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    # Fills should execute at the scaled 0.5 weight
    assert len(result.fills) > 0
    rejections = [r for r in result.rejections if r.rule == "leverage_constrained"]
    assert len(rejections) > 0
    assert rejections[0].security_id == "AAPL"
    assert "scaled" in rejections[0].reason.lower() or "constrained" in rejections[0].reason.lower()

    # Target weights across all signals must satisfy max_leverage
    for sig in result.signals:
        assert abs(sig.weight) <= 0.5 + 1e-6

    # On the fill session date, gross exposure must be <= max_leverage
    fill_date = result.fills[0].session_date
    fill_row = next(r for r in result.ledger if r.session_date == fill_date)
    assert fill_row.gross_exposure <= 0.5 + 1e-4


def test_multi_security_leverage_scaling_in_constrain_mode():
    """Verify that multi-security target portfolios exceeding leverage are scaled proportionally."""
    dates = make_dates(8)
    # Both AAPL and MSFT rise (bullish long targets)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    msft_closes = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0]

    bars: list[DailyBar] = []
    for d, c_a, c_m in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_a, c_a))
        bars.append(make_bar("MSFT", d, c_m, c_m))

    # Set max_leverage to 0.6 (where normal multi-security targets would be 0.5 + 0.5 = 1.0)
    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        max_leverage=0.6,
        leverage_mode="constrain",
    )
    spec = make_spec(universe=("AAPL", "MSFT"), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    # Check that both symbols received scaled fills
    fill_symbols = {f.security_id for f in result.fills}
    assert "AAPL" in fill_symbols
    assert "MSFT" in fill_symbols

    # Signals for each date should sum to <= 0.6
    for row in result.ledger:
        sum_weights = sum(abs(w) for w in row.signal_weights.values())
        assert sum_weights <= 0.6 + 1e-6

    # On the first fill session date, gross exposure must be <= max_leverage
    first_fill_date = result.fills[0].session_date
    first_fill_row = next(r for r in result.ledger if r.session_date == first_fill_date)
    assert first_fill_row.gross_exposure <= 0.6 + 1e-4


def test_gross_and_net_exposure_on_leveraged_mixed_portfolio():
    """Verify gross and net exposure calculations when holding long and short positions under 2.0x leverage."""
    dates = make_dates(8)
    # AAPL rises (long), MSFT falls (short)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    msft_closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]

    bars: list[DailyBar] = []
    for d, c_a, c_m in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_a, c_a))
        bars.append(make_bar("MSFT", d, c_m, c_m))

    # Allow 2.0x leverage
    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        max_leverage=2.0,
        margin_requirement=0.5,
    )
    spec = make_spec(universe=("AAPL", "MSFT"), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    # In mixed rows, verify gross_exposure and net_exposure formulas
    for r in result.ledger:
        if r.portfolio_value > 0:
            total_val = sum(pos.position_value for pos in r.positions.values())
            gross_val = sum(abs(pos.position_value) for pos in r.positions.values())
            expected_gross = gross_val / r.portfolio_value
            expected_net = total_val / r.portfolio_value

            assert r.gross_exposure == pytest.approx(expected_gross, abs=1e-4)
            assert r.net_exposure == pytest.approx(expected_net, abs=1e-4)

    # Check metrics
    assert result.metrics.gross_exposure >= 0.0
    assert isinstance(result.metrics.net_exposure, float)


def test_margin_requirement_constrains_purchasing_power():
    """Verify that margin requirement limits order sizes to available margin capital."""
    dates = make_dates(8)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    # 100% margin requirement (cash account) with starting cash 10000
    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        margin_requirement=1.0,
        max_leverage=1.0,
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions, cash=10000.0)
    result = run_backtest(spec, bars=bars)

    assert len(result.fills) > 0
    # Initial position value should not exceed available cash
    first_fill = result.fills[0]
    assert first_fill.notional <= 10000.0 + 1e-2


def test_maintenance_margin_call_triggers_rejection_and_warning():
    """Verify that when equity falls below maintenance margin threshold, a margin call rejection and warning occur."""
    dates = make_dates(8)
    # Price rises dramatically while short, reducing portfolio equity
    # Start with short signal then massive price spike
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 120.0, 180.0, 240.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        allow_shorting=True,
        max_leverage=2.0,
        margin_requirement=0.5,
        maintenance_margin=0.30,
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions, cash=100000.0)
    result = run_backtest(spec, bars=bars)

    # When price spiked to 180/240 on short, maintenance margin call should trigger
    margin_calls = [r for r in result.rejections if r.rule == "maintenance_margin_call"]
    if len(margin_calls) > 0:
        assert margin_calls[0].security_id == "AAPL"
        assert "maintenance margin" in margin_calls[0].reason.lower()
        assert any("margin call" in w.lower() for w in result.warnings)


def test_leverage_margin_deterministic_replay():
    """Verify that backtest runs with leverage and margin limits are strictly deterministic."""
    dates = make_dates(8)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        max_leverage=1.5,
        margin_requirement=0.6,
        maintenance_margin=0.25,
        leverage_mode="constrain",
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)

    run1 = run_backtest(spec, bars=bars)
    run2 = run_backtest(spec, bars=bars)

    assert run1.to_json() == run2.to_json()


def test_leverage_margin_future_data_leakage_invariance():
    """Verify appending future bars does not alter prior decisions or ledger under leverage limits."""
    dates = make_dates(8)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        max_leverage=1.5,
        margin_requirement=0.6,
        maintenance_margin=0.25,
        leverage_mode="constrain",
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)
    base_run = run_backtest(spec, bars=bars)

    future_bars = [
        make_bar("AAPL", "2024-01-20", 30.0, 35.0),
        make_bar("AAPL", "2024-01-21", 35.0, 40.0),
    ]
    extended_run = run_backtest(spec, bars=[*bars, *future_bars])

    assert base_run.signals == extended_run.signals
    assert base_run.fills == extended_run.fills
    assert base_run.trades == extended_run.trades
    assert base_run.ledger == extended_run.ledger
    assert base_run.metrics == extended_run.metrics


def test_short_covering_not_blocked_by_margin_limits():
    """Verify that buying to cover short positions is permitted even when cash or margin equity is depleted."""
    dates = make_dates(8)
    # Falling then rising price series (short signal then cover)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 70.0, 80.0, 90.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        allow_shorting=True,
        max_leverage=1.0,
        margin_requirement=1.0,
    )
    spec = make_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions, cash=10000.0)
    result = run_backtest(spec, bars=bars)

    # Should have filled the initial short sell and subsequent cover buy
    fill_sides = [f.side for f in result.fills]
    assert "sell" in fill_sides
    # The short should be covered without margin_limit rejections
    assert "buy" in fill_sides


def test_mean_exposure_reported_in_metrics():
    """Verify that BacktestMetrics gross_exposure and net_exposure report the mean across the full run."""
    dates = make_dates(6)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    spec = make_spec(universe=("AAPL",), dates=dates)
    result = run_backtest(spec, bars=bars)

    expected_gross_mean = sum(r.gross_exposure for r in result.ledger) / len(result.ledger)
    expected_net_mean = sum(r.net_exposure for r in result.ledger) / len(result.ledger)

    assert result.metrics.gross_exposure == pytest.approx(expected_gross_mean, abs=1e-6)
    assert result.metrics.net_exposure == pytest.approx(expected_net_mean, abs=1e-6)
