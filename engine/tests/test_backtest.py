"""Contract tests for the deterministic Backtest engine (Issue #24).

The tests drive the ``long_flat_moving_average`` Strategy with fast_period=2 /
slow_period=4 SMA, for which bullish/bearish price sequences are proven in
``test_strategies.py``. Every bar carries an ``available_at`` eligibility
timestamp; signals decided at a bar's close fill at the NEXT bar's open.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import pytest

from market_research_lab.backtest import (
    BacktestError,
    BacktestParameterError,
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from market_research_lab.market_data import DailyBar
from market_research_lab.strategies import StrategyEvaluationError

_ROUND_TRIP_CLOSES = [
    10.0,
    11.0,
    12.0,
    13.0,
    14.0,
    15.0,
    16.0,
    15.0,
    14.0,
    13.0,
    12.0,
    11.0,
    10.0,
]
_RISING_CLOSES = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]


def make_dates(n: int, start: str = "2024-01-02") -> list[str]:
    """Return n sequential calendar dates starting at start."""
    first = date.fromisoformat(start)
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def make_bar(session_date: str, open: float, close: float) -> DailyBar:
    """Build a DailyBar with full point-in-time eligibility metadata."""
    return DailyBar(
        security_id="AAPL",
        session_date=session_date,
        open=open,
        high=max(open, close),
        low=min(open, close),
        close=close,
        volume=1000.0,
        source="test",
        retrieval_time="",
        available_at=f"{session_date}T21:00:00Z",
        eligibility_provenance="test",
    )


def make_bar_without_provenance(session_date: str, open: float, close: float) -> DailyBar:
    """Build a DailyBar that lacks a point-in-time availability timestamp."""
    return DailyBar(
        security_id="AAPL",
        session_date=session_date,
        open=open,
        high=max(open, close),
        low=min(open, close),
        close=close,
        volume=1000.0,
        source="test",
        retrieval_time="",
        available_at=None,
        eligibility_provenance="test",
    )


def make_execution(
    commission_rate: float = 0.0, slippage_rate: float = 0.0
) -> ExecutionModelAssumptions:
    """Build execution assumptions with the given cost rates."""
    return ExecutionModelAssumptions(
        schedule="daily", commission_rate=commission_rate, slippage_rate=slippage_rate
    )


def make_spec(
    start_date: str,
    end_date: str,
    starting_cash: float,
    *,
    strategy_name: str = "long_flat_moving_average",
) -> BacktestSpecification:
    """Build a BacktestSpecification with the standard long/flat SMA defaults."""
    return BacktestSpecification(
        strategy_name=strategy_name,
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=start_date,
        end_date=end_date,
        starting_cash=starting_cash,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        price_field="close",
        execution=ExecutionModelAssumptions(),
    )


def make_round_trip_bars() -> list[DailyBar]:
    """Build the bullish-then-bearish single-trade price sequence."""
    dates = make_dates(len(_ROUND_TRIP_CLOSES))
    return [make_bar(d, c, c) for d, c in zip(dates, _ROUND_TRIP_CLOSES)]


def test_backtest_rejects_unknown_strategy():
    bars = [make_bar("2024-01-02", 10.0, 10.0)]
    spec = make_spec("2024-01-02", "2024-01-02", 100000.0, strategy_name="mystery_strategy")
    with pytest.raises(StrategyEvaluationError):
        run_backtest(spec, bars=bars)


def test_backtest_rejects_nonpositive_starting_cash():
    bars = [make_bar("2024-01-02", 10.0, 10.0)]
    spec = make_spec("2024-01-02", "2024-01-02", 0.0)
    with pytest.raises(BacktestParameterError):
        run_backtest(spec, bars=bars)


def test_backtest_rejects_start_after_end():
    bars = [make_bar("2024-01-02", 10.0, 10.0)]
    spec = make_spec("2024-01-05", "2024-01-02", 100000.0)
    with pytest.raises(BacktestParameterError):
        run_backtest(spec, bars=bars)


def test_backtest_rejects_missing_available_at():
    bars = [
        make_bar("2024-01-02", 10.0, 10.0),
        make_bar_without_provenance("2024-01-03", 11.0, 11.0),
    ]
    spec = make_spec("2024-01-02", "2024-01-03", 100000.0)
    with pytest.raises(BacktestError, match="available_at"):
        run_backtest(spec, bars=bars)


def test_backtest_rejects_empty_window():
    bars = [
        make_bar("2024-02-01", 10.0, 10.0),
        make_bar("2024-02-02", 11.0, 11.0),
    ]
    spec = make_spec("2024-01-01", "2024-01-31", 100000.0)
    with pytest.raises(BacktestError, match="no bars within"):
        run_backtest(spec, bars=bars)


def test_signal_fills_only_on_next_bar():
    bars = [make_bar(d, c, c) for d, c in zip(make_dates(7), _RISING_CLOSES)]
    spec = make_spec(bars[0].session_date, bars[-1].session_date, 100000.0)
    result = run_backtest(spec, bars=bars)

    first_bullish = next(i for i, s in enumerate(result.signals) if s.weight > 0)
    bar_k = bars[first_bullish]
    bar_next = bars[first_bullish + 1]

    assert result.signals[first_bullish].decision_time == bar_k.available_at
    assert result.fills[0].decision_time == result.signals[first_bullish].decision_time
    assert result.fills[0].session_date == bar_next.session_date
    assert result.fills[0].price == pytest.approx(bar_next.open)
    assert len(result.fills) == 1


def test_warmup_emits_flat_and_no_fills():
    closes = [10.0, 11.0, 12.0]
    bars = [make_bar(d, c, c) for d, c in zip(make_dates(len(closes)), closes)]
    spec = make_spec(bars[0].session_date, bars[-1].session_date, 100000.0)
    result = run_backtest(spec, bars=bars)

    assert len(result.fills) == 0
    assert all(signal.weight == 0 for signal in result.signals)
    assert any("No fills occurred" in warning for warning in result.warnings)


def test_round_trip_produces_one_trade_and_hit_rate():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    result = run_backtest(spec, bars=make_round_trip_bars())

    assert len(result.trades) == 1
    assert result.fills[0].side == "buy"
    assert result.fills[-1].side == "sell"
    assert result.trades[0].quantity == pytest.approx(result.fills[0].quantity)
    assert result.metrics.hit_rate is not None


def test_ledger_arithmetic_holds_every_row():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    result = run_backtest(spec, bars=make_round_trip_bars())

    assert len(result.ledger) == len(_ROUND_TRIP_CLOSES)
    for row in result.ledger:
        assert row.position_value == pytest.approx(row.shares * row.close_price)
        assert row.cash + row.position_value == pytest.approx(row.portfolio_value)


def test_deterministic_replay_is_identical():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    bars = make_round_trip_bars()

    first = run_backtest(spec, bars=bars)
    second = run_backtest(spec, bars=bars)

    assert first.to_json() == second.to_json()


def test_future_data_does_not_alter_earlier_decisions():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    base = run_backtest(spec, bars=make_round_trip_bars())
    extended = run_backtest(
        spec, bars=[*make_round_trip_bars(), make_bar("2024-01-22", 5.0, 5.0)]
    )

    assert base.signals == extended.signals
    assert base.fills == extended.fills
    assert base.trades == extended.trades


def test_commission_and_slippage_applied():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    spec = dataclasses.replace(spec, execution=make_execution(0.01, 0.001))
    bars = make_round_trip_bars()
    result = run_backtest(spec, bars=bars)

    buy = result.fills[0]
    assert buy.price == pytest.approx(bars[4].open * (1 + 0.001))
    assert buy.commission == pytest.approx(abs(buy.notional) * 0.01)
    assert buy.slippage_cost == pytest.approx(abs(buy.quantity) * bars[4].open * 0.001)

    sell = result.fills[1]
    assert sell.price == pytest.approx(bars[9].open * (1 - 0.001))
    assert sell.commission == pytest.approx(abs(sell.notional) * 0.01)


def test_next_bar_fill_uses_open_not_close():
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    opens = [10.0, 11.0, 12.0, 13.0, 20.0, 15.0, 16.0]
    bars = [make_bar(d, o, c) for d, o, c in zip(make_dates(len(closes)), opens, closes)]
    spec = make_spec(bars[0].session_date, bars[-1].session_date, 100000.0)
    result = run_backtest(spec, bars=bars)

    assert result.fills[0].price == pytest.approx(bars[4].open)
    assert result.fills[0].price != pytest.approx(bars[4].close)


def test_manifest_records_specification():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    result = run_backtest(spec, bars=make_round_trip_bars())

    manifest = result.manifest
    assert manifest["strategy_revision"] == "v1"
    assert manifest["dataset_version_id"] == "ds-1"
    assert manifest["security_id"] == "AAPL"
    assert manifest["starting_cash"] == 100000.0
    assert manifest["execution"]["fill_price"] == "next_open"
    assert manifest["costs"]["total_costs"] >= 0
    assert "total_commission" in manifest["costs"]
    assert "total_slippage" in manifest["costs"]


def test_hold_does_not_emit_new_fill():
    bars = [make_bar(d, c, c) for d, c in zip(make_dates(7), _RISING_CLOSES)]
    spec = make_spec(bars[0].session_date, bars[-1].session_date, 100000.0)
    result = run_backtest(spec, bars=bars)

    assert len(result.fills) == 1
    assert result.fills[0].side == "buy"
    assert all(fill.side == "buy" for fill in result.fills)


def test_metrics_are_reported_and_sane():
    spec = make_spec("2024-01-02", "2024-01-14", 100000.0)
    result = run_backtest(spec, bars=make_round_trip_bars())

    metrics = result.metrics
    assert isinstance(metrics.total_return, float)
    assert metrics.max_drawdown <= 0
    assert metrics.turnover >= 0
    assert metrics.gross_exposure >= 0
    assert metrics.num_fills == len(result.fills)
    assert metrics.num_trades == len(result.trades)
