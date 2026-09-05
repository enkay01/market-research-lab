"""Contract and unit tests for the Strategy Verdict Engine foundation (Issue #114)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from market_research_lab.backtest import BacktestError, ExecutionModelAssumptions
from market_research_lab.market_data import DailyBar
from market_research_lab.strategy_verdict import (
    FrictionTier,
    PartitionMetrics,
    StrategyVerdictResult,
    StrategyVerdictSpecification,
    evaluate_gate_1,
    evaluate_gate_2,
    evaluate_strategy_verdict,
    partition_chronological_data,
)


def _make_dates(n: int, start: str = "2024-01-02") -> list[str]:
    """Generate n calendar dates starting from start."""
    first = date.fromisoformat(start)
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def _make_bar(
    session_date: str,
    *,
    security_id: str = "AAPL",
    open_price: float,
    close_price: float,
) -> DailyBar:
    """Build a DailyBar with point-in-time available_at metadata."""
    return DailyBar(
        security_id=security_id,
        session_date=session_date,
        open=open_price,
        high=max(open_price, close_price) * 1.01,
        low=min(open_price, close_price) * 0.99,
        close=close_price,
        volume=100_000.0,
        source="test",
        available_at=f"{session_date}T21:00:00Z",
    )


def test_chronological_partitioning_75_25() -> None:
    """Verify 75/25 default chronological split across 20 trading sessions."""
    dates = _make_dates(20)
    in_sample, out_of_sample = partition_chronological_data(dates, holdout_ratio=0.25)

    assert len(in_sample) == 15
    assert len(out_of_sample) == 5
    assert in_sample == tuple(dates[:15])
    assert out_of_sample == tuple(dates[15:])
    # Strict monotonic ordering with zero overlap
    assert in_sample[-1] < out_of_sample[0]


def test_chronological_partitioning_custom_split() -> None:
    """Verify 80/20 and 70/30 split ratios."""
    dates = _make_dates(10)
    is_80, oos_20 = partition_chronological_data(dates, holdout_ratio=0.20)
    assert len(is_80) == 8
    assert len(oos_20) == 2

    is_70, oos_30 = partition_chronological_data(dates, holdout_ratio=0.30)
    assert len(is_70) == 7
    assert len(oos_30) == 3


def test_chronological_partitioning_too_few_sessions() -> None:
    """Verify error raised when fewer than 2 session dates are provided."""
    with pytest.raises(BacktestError, match="at least 2 sessions"):
        partition_chronological_data(["2024-01-02"])


def test_evaluate_gate_1_pass() -> None:
    """Gate 1 passes when strategy net return exceeds benchmark return."""
    gate = evaluate_gate_1(
        net_strategy_return=0.25,
        benchmark_return=0.10,
        benchmark_symbol="SPY",
    )
    assert gate.gate_number == 1
    assert gate.name == "Benchmark Hurdle"
    assert gate.passed is True
    assert gate.metric_label == "Strategy Return"
    assert gate.metric_value == "+25.0%"
    assert gate.threshold_label == "SPY Benchmark"
    assert gate.threshold_value == "+10.0%"
    assert "+15.0% Net Edge over Benchmark after friction" in gate.verdict_note


def test_evaluate_gate_1_fail() -> None:
    """Gate 1 fails with exact message when net return does not exceed benchmark."""
    gate = evaluate_gate_1(
        net_strategy_return=0.08,
        benchmark_return=0.12,
        benchmark_symbol="SPY",
    )
    assert gate.gate_number == 1
    assert gate.passed is False
    assert gate.metric_value == "+8.0%"
    assert gate.threshold_value == "+12.0%"
    assert gate.verdict_note == "Loses to benchmark after costs"


def test_evaluate_gate_1_fail_on_tie() -> None:
    """Gate 1 fails when net return strictly equals benchmark (no excess edge)."""
    gate = evaluate_gate_1(
        net_strategy_return=0.10,
        benchmark_return=0.10,
        benchmark_symbol="SPY",
    )
    assert gate.passed is False
    assert gate.verdict_note == "Loses to benchmark after costs"


def test_evaluate_gate_2_requires_strict_positive_return_and_profit_factor() -> None:
    tier = FrictionTier(
        multiplier=3,
        commission_bps=15.0,
        slippage_bps=6.0,
        borrow_fee_bps=0.0,
        total_return_pct=0.0,
        net_profit_usd=0.0,
        profit_factor=1.01,
        max_drawdown_pct=0.0,
        commission_paid_usd=0.0,
        slippage_drag_usd=0.0,
        borrow_paid_usd=0.0,
    )
    assert evaluate_gate_2(tier).passed is False
    assert evaluate_gate_2(replace(tier, total_return_pct=0.1, profit_factor=1.0)).verdict_note == (
        "Edge disappears under realistic fee stress"
    )
    assert evaluate_gate_2(replace(tier, total_return_pct=0.1, profit_factor=1.01)).passed is True


def test_strategy_verdict_full_execution_pass() -> None:
    """Full verdict execution on rising bars where moving average strategy beats benchmark."""
    dates = _make_dates(16)
    strat_closes = [
        10.0, 10.5, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0,
        17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0,
    ]
    bench_closes = [100.0 + i * 0.5 for i in range(16)]

    bars: list[DailyBar] = []
    for d, c in zip(dates, strat_closes, strict=True):
        bars.append(_make_bar(d, security_id="AAPL", open_price=c, close_price=c))
    for d, c in zip(dates, bench_closes, strict=True):
        bars.append(_make_bar(d, security_id="SPY", open_price=c, close_price=c))

    spec = StrategyVerdictSpecification(
        strategy_name="long_flat_moving_average",
        universe=("AAPL",),
        benchmark_security_id="SPY",
        start_date=dates[0],
        end_date=dates[-1],
        starting_cash=100_000.0,
        parameters={"fast_period": 2, "slow_period": 4},
        holdout_ratio=0.25,
        execution=ExecutionModelAssumptions(commission_rate=0.0001, slippage_rate=0.0001),
    )

    result = evaluate_strategy_verdict(spec, bars=bars)

    assert isinstance(result, StrategyVerdictResult)
    assert len(result.gates) == 2
    assert result.gates[0].gate_number == 1
    assert result.gates[0].passed is True
    assert result.gates[1].gate_number == 2
    assert len(result.friction_ladder) == 3
    assert [tier.multiplier for tier in result.friction_ladder] == [1, 2, 3]
    assert result.overall_passed is result.gates[1].passed
    assert result.rejection_reason == (
        None if result.gates[1].passed else "Edge disappears under realistic fee stress"
    )

    # Check partition metrics
    assert isinstance(result.in_sample_metrics, PartitionMetrics)
    assert isinstance(result.out_of_sample_metrics, PartitionMetrics)
    assert isinstance(result.combined_metrics, PartitionMetrics)

    # Check equity curve with holdout flags
    assert len(result.equity_curve) > 0
    is_points = [p for p in result.equity_curve if not p.is_holdout]
    oos_points = [p for p in result.equity_curve if p.is_holdout]
    assert len(is_points) > 0
    assert len(oos_points) > 0
    assert is_points[-1].session_date < oos_points[0].session_date


def test_strategy_verdict_full_execution_fail() -> None:
    """Full verdict execution where strategy underperforms benchmark -> Gate 1 fails."""
    dates = _make_dates(16)
    strat_closes = [20.0 - (i * 0.5) for i in range(16)]
    bench_closes = [100.0 + (i * 10.0) for i in range(16)]

    bars: list[DailyBar] = []
    for d, c in zip(dates, strat_closes, strict=True):
        bars.append(_make_bar(d, security_id="AAPL", open_price=c, close_price=c))
    for d, c in zip(dates, bench_closes, strict=True):
        bars.append(_make_bar(d, security_id="SPY", open_price=c, close_price=c))

    spec = StrategyVerdictSpecification(
        strategy_name="long_flat_moving_average",
        universe=("AAPL",),
        benchmark_security_id="SPY",
        start_date=dates[0],
        end_date=dates[-1],
        starting_cash=100_000.0,
        parameters={"fast_period": 2, "slow_period": 4},
        holdout_ratio=0.25,
    )

    result = evaluate_strategy_verdict(spec, bars=bars)

    assert result.overall_passed is False
    assert result.gates[0].passed is False
    assert result.gates[0].verdict_note == "Loses to benchmark after costs"
    assert result.rejection_reason == "Loses to benchmark after costs"
    assert "Loses to benchmark after costs" in result.headline_verdict
