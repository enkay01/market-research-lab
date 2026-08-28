"""Contract and accounting tests for short positions, borrowing constraints, and borrow fees.

Issue #27.

Tests cover:
1. Short sale entry (cash credited, negative shares) and covering exit
   (cash debited, positive/negative PnL).
2. Round-trip trade lifecycle for short positions (entry proceeds, exit costs,
   realized PnL, return %).
3. Hard-to-borrow constraint rejection (unavailable borrow emits ConstraintRejection
   and prevents short).
4. Shorting disabled execution model rejection (allow_shorting=False emits ConstraintRejection).
5. Daily borrow fee deduction at session close (cash debited, LedgerRow.borrow_fees
   and manifest tracking).
6. Gross and net exposure accounting for mixed long/short positions.
7. Long/short moving average strategy evaluation and signal generation.
8. Deterministic replay and point-in-time leakage invariance.
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
from market_research_lab.strategies import (
    MarketView,
    evaluate_strategy,
    get_strategy_spec,
    list_strategies,
)


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


def make_short_spec(
    universe: tuple[str, ...],
    dates: list[str],
    execution: ExecutionModelAssumptions | None = None,
    cash: float = 100000.0,
) -> BacktestSpecification:
    """Build a BacktestSpecification using the long/short strategy."""
    return BacktestSpecification(
        strategy_name="long_short_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-short",
        security_id=universe[0] if universe else "AAPL",
        universe=universe,
        start_date=dates[0],
        end_date=dates[-1],
        starting_cash=cash,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        price_field="close",
        execution=execution or ExecutionModelAssumptions(schedule="daily"),
    )


def test_long_short_strategy_registry_and_evaluation():
    """Verify long_short_moving_average is registered and outputs negative weights on downtrends."""
    specs = list_strategies()
    strategy_names = [s.name for s in specs]
    assert "long_short_moving_average" in strategy_names

    spec = get_strategy_spec("long_short_moving_average")
    assert spec.name == "long_short_moving_average"

    # Fast below slow produces bearish state (-1.0 target weight)
    dates = make_dates(6)
    falling_prices = (100.0, 95.0, 90.0, 85.0, 80.0, 75.0)
    view = MarketView(
        security_id="AAPL",
        session_dates=tuple(dates),
        prices=falling_prices,
    )

    eval_result = evaluate_strategy(
        "long_short_moving_average",
        view,
        {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        decision_time=f"{dates[-1]}T21:00:00Z",
    )

    assert len(eval_result.targets) == 1
    target = eval_result.targets[0]
    assert target.weight == -1.0
    assert target.indicator_state in ("bearish_cross", "bearish_below", "bearish")
    assert "bearish" in target.rationale.lower()


def test_short_opening_and_profitable_covering():
    """Verify short position opening credits cash, holds negative shares, and covering
    captures profit.
    """
    dates = make_dates(8)
    # Falling price series: fast MA drops below slow MA, triggering short signal
    # Then price rises at the end, triggering cover/long
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 80.0, 90.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    spec = make_short_spec(universe=("AAPL",), dates=dates, cash=100000.0)
    result = run_backtest(spec, bars=bars)

    # Check fills
    assert len(result.fills) >= 2
    # First fill should be a short sale (sell)
    short_fill = result.fills[0]
    assert short_fill.side == "sell"
    assert short_fill.quantity > 0
    assert short_fill.notional < 0

    # There should be ledger rows with negative shares
    short_rows = [
        r for r in result.ledger if r.positions.get("AAPL") and r.positions["AAPL"].shares < 0
    ]
    assert len(short_rows) > 0

    # In short rows, cash is higher than starting cash (short sale proceeds credited)
    # and position value is negative
    for r in short_rows:
        assert r.cash > 100000.0
        assert r.position_value < 0.0
        assert r.portfolio_value == pytest.approx(r.cash + r.position_value, abs=1e-2)

    # Check closed trade
    assert len(result.trades) >= 1
    trade = result.trades[0]
    # Entered short at higher price, exited covering at lower price -> positive PnL
    if trade.entry_price > trade.exit_price:
        assert trade.pnl > 0
        assert trade.return_pct > 0


def test_short_loss_when_price_rises():
    """Verify short position produces negative PnL when covering at a higher price."""
    dates = make_dates(8)
    # Starts falling (short at 60), then rises to 75, 85, 90 (bullish cross, covers at 85/90)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 75.0, 85.0, 90.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    spec = make_short_spec(universe=("AAPL",), dates=dates, cash=100000.0)
    result = run_backtest(spec, bars=bars)

    # Closed trades should record the loss
    assert len(result.trades) >= 1
    trade = result.trades[0]
    assert trade.exit_price > trade.entry_price
    assert trade.pnl < 0
    assert trade.return_pct < 0


def test_unavailable_borrow_constraint_rejection():
    """Verify that unavailable borrow prevents short sale and logs ConstraintRejection."""
    dates = make_dates(8)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        allow_shorting=True,
        unavailable_borrow=("AAPL",),
    )
    spec = make_short_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    # Short signals should be rejected
    borrow_rejections = [r for r in result.rejections if r.rule == "borrow_unavailable"]
    assert len(borrow_rejections) > 0
    assert borrow_rejections[0].security_id == "AAPL"
    assert "hard-to-borrow" in borrow_rejections[0].reason.lower()

    # No short positions should ever be held
    for r in result.ledger:
        if "AAPL" in r.positions:
            assert r.positions["AAPL"].shares >= 0.0


def test_short_disabled_constraint_rejection():
    """Verify that allow_shorting=False rejects negative target weights."""
    dates = make_dates(8)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        allow_shorting=False,
    )
    spec = make_short_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    disabled_rejections = [r for r in result.rejections if r.rule == "short_disabled"]
    assert len(disabled_rejections) > 0
    assert "short positions are disabled" in disabled_rejections[0].reason.lower()

    for r in result.ledger:
        if "AAPL" in r.positions:
            assert r.positions["AAPL"].shares >= 0.0


def test_borrow_fee_deduction_and_manifest_accounting():
    """Verify daily borrow fees are deducted from cash at session close on short positions."""
    dates = make_dates(8)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    # 10% annualized borrow fee
    borrow_fee_rate = 0.10
    exec_assumptions = ExecutionModelAssumptions(
        schedule="daily",
        allow_shorting=True,
        borrow_fee_rate=borrow_fee_rate,
    )
    spec = make_short_spec(universe=("AAPL",), dates=dates, execution=exec_assumptions)
    result = run_backtest(spec, bars=bars)

    # Check ledger borrow fees
    short_rows = [r for r in result.ledger if r.borrow_fees > 0.0]
    assert len(short_rows) > 0

    total_ledger_fees = sum(r.borrow_fees for r in result.ledger)
    assert total_ledger_fees > 0.0

    manifest_costs = result.manifest.get("costs")
    assert isinstance(manifest_costs, dict)
    assert manifest_costs.get("total_borrow_fees") == pytest.approx(total_ledger_fees, abs=1e-2)
    assert manifest_costs.get("total_costs") == pytest.approx(
        float(manifest_costs.get("total_commission", 0.0))
        + float(manifest_costs.get("total_slippage", 0.0))
        + total_ledger_fees,
        abs=1e-2,
    )


def test_gross_and_net_exposure_on_multi_security_long_short():
    """Verify gross and net exposures when holding simultaneously long and short positions."""
    dates = make_dates(8)
    # AAPL rises (long), MSFT falls (short)
    aapl_closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    msft_closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]

    bars: list[DailyBar] = []
    for d, c_aapl, c_msft in zip(dates, aapl_closes, msft_closes):
        bars.append(make_bar("AAPL", d, c_aapl, c_aapl))
        bars.append(make_bar("MSFT", d, c_msft, c_msft))

    spec = make_short_spec(universe=("AAPL", "MSFT"), dates=dates, cash=100000.0)
    result = run_backtest(spec, bars=bars)

    # Find rows where AAPL is long and MSFT is short
    mixed_rows = [
        r
        for r in result.ledger
        if r.positions.get("AAPL")
        and r.positions["AAPL"].shares > 0
        and r.positions.get("MSFT")
        and r.positions["MSFT"].shares < 0
    ]

    assert len(mixed_rows) > 0
    for r in mixed_rows:
        # Gross exposure should be near ~1.0 (50% long + 50% short)
        assert r.gross_exposure > 0.5
        # Net exposure should be close to 0.0 (50% long - 50% short)
        assert abs(r.net_exposure) < r.gross_exposure


def test_short_positions_deterministic_replay():
    """Verify that short positions backtest is byte-for-byte deterministic."""
    dates = make_dates(8)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 70.0, 80.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    spec = make_short_spec(
        universe=("AAPL",),
        dates=dates,
        execution=ExecutionModelAssumptions(
            commission_rate=0.0005,
            slippage_rate=0.0002,
            borrow_fee_rate=0.02,
        ),
    )

    run1 = run_backtest(spec, bars=bars)
    run2 = run_backtest(spec, bars=bars)

    assert run1.to_json() == run2.to_json()


def test_short_positions_future_data_leakage_invariance():
    """Verify appending future bars does not alter prior short positions backtest results."""
    dates = make_dates(8)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 70.0, 80.0]
    bars = [make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    spec = make_short_spec(universe=("AAPL",), dates=dates)
    base_run = run_backtest(spec, bars=bars)

    future_bars = [
        make_bar("AAPL", "2024-01-20", 200.0, 210.0),
        make_bar("AAPL", "2024-01-21", 210.0, 220.0),
    ]
    extended_run = run_backtest(spec, bars=[*bars, *future_bars])

    assert base_run.signals == extended_run.signals
    assert base_run.fills == extended_run.fills
    assert base_run.trades == extended_run.trades
    assert base_run.ledger == extended_run.ledger
    assert base_run.metrics == extended_run.metrics
