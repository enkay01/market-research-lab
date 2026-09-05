"""Contract and unit tests for the Strategy Verdict Engine foundation (Issue #114)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from market_research_lab.backtest import BacktestError, ExecutionModelAssumptions, Trade
from market_research_lab.market_data import DailyBar
from market_research_lab.strategy_verdict import (
    MonteCarloOptions,
    MonteCarloSimulationInput,
    PartitionMetrics,
    PsrMomentsInput,
    StrategyVerdictResult,
    StrategyVerdictSpecification,
    compute_probabilistic_sharpe_ratio,
    evaluate_gate_1,
    evaluate_gate_3,
    evaluate_gate_4,
    evaluate_gate_5,
    evaluate_strategy_verdict,
    partition_chronological_data,
    run_monte_carlo_random_entry,
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


def test_evaluate_gate_3_pass() -> None:
    """Gate 3 passes when closed trades count is at least 30."""
    gate = evaluate_gate_3(trades_count=30, min_trades=30)
    assert gate.gate_number == 3
    assert gate.name == "Sample Size"
    assert gate.passed is True
    assert gate.metric_label == "Closed Trades"
    assert gate.metric_value == "30 Trades"
    assert gate.threshold_label == "Minimum Sample Size"
    assert gate.threshold_value == "30 Trades"
    assert "Sample size statistically sufficient (N = 30 >= 30)" in gate.verdict_note

    gate_surplus = evaluate_gate_3(trades_count=52, min_trades=30)
    assert gate_surplus.passed is True
    assert gate_surplus.metric_value == "52 Trades"


def test_evaluate_gate_3_fail() -> None:
    """Gate 3 fails with exact message when closed trades are fewer than 30."""
    gate = evaluate_gate_3(trades_count=29, min_trades=30)
    assert gate.gate_number == 3
    assert gate.passed is False
    assert gate.metric_value == "29 Trades"
    assert gate.threshold_value == "30 Trades"
    assert gate.verdict_note == "Insufficient trade sample size (N < 30)"

    gate_zero = evaluate_gate_3(trades_count=0, min_trades=30)
    assert gate_zero.passed is False
    assert gate_zero.verdict_note == "Insufficient trade sample size (N < 30)"


def test_compute_probabilistic_sharpe_ratio_normal() -> None:
    """Verify closed-form PSR accuracy for a normal distribution baseline."""
    # N = 101 -> sqrt(N - 1) = 10.0
    # SR = 0.2, skewness = 0.0, excess_kurtosis = 0.0 (gamma_4 = 3.0)
    # denom_variance = 1.0 + 0.5 * (0.2^2) = 1.02
    # z = (0.2 * 10) / sqrt(1.02) = 2.0 / 1.0099505 = 1.980295
    # NormalDist(0, 1).cdf(1.980295) = 0.97616
    psr = compute_probabilistic_sharpe_ratio(
        moments=PsrMomentsInput(
            mean=0.2,
            stdev=1.0,
            skewness=0.0,
            excess_kurtosis=0.0,
            sample_size=101,
        ),
        benchmark_sharpe=0.0,
    )
    assert abs(psr - 0.97616) < 1e-4


def test_compute_probabilistic_sharpe_ratio_non_normal() -> None:
    """Verify closed-form PSR accuracy against non-normal distributions with skew and kurtosis."""
    # Negative skewness and high excess kurtosis (fat crash tails) increase estimator variance
    # N = 101, SR = 0.2, skewness = -1.5, excess_kurtosis = 5.0 (gamma_4 = 8.0)
    # denom_variance = 1.0 - (-1.5 * 0.2) + (7.0 / 4.0) * (0.04) = 1.0 + 0.3 + 0.07 = 1.37
    # z = 2.0 / sqrt(1.37) = 2.0 / 1.17047 = 1.70870
    # NormalDist(0, 1).cdf(1.70870) = 0.95624
    psr_non_normal = compute_probabilistic_sharpe_ratio(
        moments=PsrMomentsInput(
            mean=0.2,
            stdev=1.0,
            skewness=-1.5,
            excess_kurtosis=5.0,
            sample_size=101,
        ),
        benchmark_sharpe=0.0,
    )
    assert abs(psr_non_normal - 0.95624) < 1e-4

    # Confidence under fat tails and negative skew must be lower than under normality
    psr_normal = compute_probabilistic_sharpe_ratio(
        moments=PsrMomentsInput(
            mean=0.2,
            stdev=1.0,
            skewness=0.0,
            excess_kurtosis=0.0,
            sample_size=101,
        ),
        benchmark_sharpe=0.0,
    )
    assert psr_non_normal < psr_normal


def test_compute_probabilistic_sharpe_ratio_from_returns() -> None:
    """Verify moments and PSR computation directly from return sequence."""
    # Consistently positive returns
    positive_returns = [0.01, 0.02, 0.015, 0.03, 0.008, 0.012, 0.025, 0.018, 0.011, 0.014] * 10
    psr_high = compute_probabilistic_sharpe_ratio(returns=positive_returns)
    assert psr_high > 0.99

    # Negative drift returns
    negative_returns = [-0.01, -0.02, 0.005, -0.015, -0.008, -0.012] * 10
    psr_low = compute_probabilistic_sharpe_ratio(returns=negative_returns)
    assert psr_low < 0.10


def test_compute_probabilistic_sharpe_ratio_edge_cases() -> None:
    """Verify PSR behavior on boundary conditions and degenerate inputs."""
    # Fewer than 2 observations returns 0.0
    assert compute_probabilistic_sharpe_ratio(moments=PsrMomentsInput(sample_size=1)) == 0.0
    assert compute_probabilistic_sharpe_ratio(returns=[0.05]) == 0.0

    # Zero standard deviation
    assert (
        compute_probabilistic_sharpe_ratio(
            moments=PsrMomentsInput(mean=0.0, stdev=0.0, sample_size=50)
        )
        == 0.5
    )
    assert (
        compute_probabilistic_sharpe_ratio(
            moments=PsrMomentsInput(mean=0.05, stdev=0.0, sample_size=50)
        )
        == 1.0
    )
    assert (
        compute_probabilistic_sharpe_ratio(
            moments=PsrMomentsInput(mean=-0.05, stdev=0.0, sample_size=50)
        )
        == 0.0
    )


def test_evaluate_gate_4_pass() -> None:
    """Gate 4 passes when PSR confidence exceeds 60%."""
    gate = evaluate_gate_4(
        moments=PsrMomentsInput(
            mean=0.02,
            stdev=0.05,
            skewness=0.0,
            excess_kurtosis=0.0,
            sample_size=50,
        ),
        confidence_threshold=0.60,
    )
    assert gate.gate_number == 4
    assert gate.name == "Probabilistic Sharpe Ratio"
    assert gate.passed is True
    assert gate.metric_label == "PSR Confidence"
    assert "confidence true Sharpe > 0" in gate.verdict_note


def test_evaluate_gate_4_fail() -> None:
    """Gate 4 fails with exact message when confidence is below 60%."""
    # Marginal or negative Sharpe ratio
    gate = evaluate_gate_4(
        moments=PsrMomentsInput(
            mean=-0.01,
            stdev=0.05,
            skewness=0.0,
            excess_kurtosis=0.0,
            sample_size=50,
        ),
        confidence_threshold=0.60,
    )
    assert gate.gate_number == 4
    assert gate.passed is False
    assert gate.verdict_note == "Sharpe ratio is not statistically distinguishable from zero"


def test_run_monte_carlo_random_entry_determinism() -> None:
    """Verify seeded Monte Carlo simulation is strictly deterministic."""
    dates = _make_dates(100)
    bars = [
        _make_bar(d, security_id="AAPL", open_price=100.0 + i, close_price=100.0 + i)
        for i, d in enumerate(dates)
    ]
    trades = [
        Trade(
            trade_id=f"t-{i}",
            security_id="AAPL",
            entry_date=dates[i * 2],
            exit_date=dates[i * 2 + 2],
            entry_price=100.0 + i * 2,
            exit_price=102.0 + i * 2,
            quantity=10.0,
            entry_cost=1000.0,
            exit_proceeds=1020.0,
            pnl=20.0,
            return_pct=0.02,
        )
        for i in range(30)
    ]
    exec_assumptions = ExecutionModelAssumptions(commission_rate=0.0001, slippage_rate=0.0001)
    sim_input = MonteCarloSimulationInput(
        bars=bars,
        trades=trades,
        execution=exec_assumptions,
    )

    run_1 = run_monte_carlo_random_entry(
        sim_input,
        options=MonteCarloOptions(num_simulations=100, random_seed=12345),
    )
    run_2 = run_monte_carlo_random_entry(
        sim_input,
        options=MonteCarloOptions(num_simulations=100, random_seed=12345),
    )
    run_diff_seed = run_monte_carlo_random_entry(
        sim_input,
        options=MonteCarloOptions(num_simulations=100, random_seed=99999),
    )

    assert len(run_1) == 100
    assert len(run_2) == 100
    assert run_1 == run_2
    assert run_1 != run_diff_seed


def test_evaluate_gate_5_pass_and_fail() -> None:
    """Verify Gate 5 pass when beating 75th percentile and fail with exact message otherwise."""
    dates = _make_dates(100)
    bars = [
        _make_bar(d, security_id="AAPL", open_price=100.0 + (i % 5), close_price=100.0 + (i % 5))
        for i, d in enumerate(dates)
    ]
    trades = [
        Trade(
            trade_id=f"t-{i}",
            security_id="AAPL",
            entry_date=dates[i * 2],
            exit_date=dates[i * 2 + 2],
            entry_price=100.0,
            exit_price=105.0,
            quantity=10.0,
            entry_cost=1000.0,
            exit_proceeds=1050.0,
            pnl=50.0,
            return_pct=0.05,
        )
        for i in range(30)
    ]
    exec_assumptions = ExecutionModelAssumptions(commission_rate=0.0001, slippage_rate=0.0001)
    sim_input = MonteCarloSimulationInput(
        bars=bars,
        trades=trades,
        execution=exec_assumptions,
    )

    # Strategy with large positive return beating random entries
    pass_gate = evaluate_gate_5(
        strategy_return=2.50,  # +250% return
        simulation_input=sim_input,
        options=MonteCarloOptions(random_seed=42),
    )
    assert pass_gate.gate_number == 5
    assert pass_gate.passed is True
    assert pass_gate.name == "Random Timing Luck"
    assert "Net Edge over 75th percentile random baseline" in pass_gate.verdict_note

    # Strategy with negative return falling below 75th percentile
    fail_gate = evaluate_gate_5(
        strategy_return=-0.50,  # -50% return
        simulation_input=sim_input,
        options=MonteCarloOptions(random_seed=42),
    )
    assert fail_gate.gate_number == 5
    assert fail_gate.passed is False
    assert fail_gate.verdict_note == "Performance is indistinguishable from random entry timing"


def test_strategy_verdict_full_execution_fails_gate_3_when_sample_too_small() -> None:
    """Backtest with fewer than 30 closed trades fails Gate 3."""
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
    assert len(result.gates) == 4
    # Gate 1 (Benchmark) passed
    assert result.gates[0].gate_number == 1
    assert result.gates[0].passed is True
    # Gate 3 (Sample size) failed
    assert result.gates[1].gate_number == 3
    assert result.gates[1].passed is False
    assert result.gates[1].verdict_note == "Insufficient trade sample size (N < 30)"
    assert result.overall_passed is False
    assert result.rejection_reason == "Insufficient trade sample size (N < 30)"
    assert "Insufficient trade sample size (N < 30)" in result.headline_verdict


def test_strategy_verdict_full_execution_all_gates_pass() -> None:
    """Full verdict execution where strategy generates >= 30 trades and clears all statistical hurdles."""
    # Generate 140 bars: 35 cycles of 4 bars creating oscillating crossovers with upward drift
    dates = _make_dates(210)
    bars: list[DailyBar] = []

    for i, d in enumerate(dates):
        step = i % 6
        if step == 0:
            o, c = 130.0, 100.0
        elif step == 1:
            o, c = 100.0, 100.0
        elif step == 2:
            o, c = 100.0, 110.0
        elif step == 3:
            o, c = 110.0, 120.0
        elif step == 4:
            o, c = 120.0, 105.0
        elif step == 5:
            o, c = 120.0, 100.0

        bars.append(_make_bar(d, security_id="AAPL", open_price=o, close_price=c))
        bars.append(_make_bar(d, security_id="SPY", open_price=100.0, close_price=100.0))

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
    assert len(result.gates) == 4
    assert [g.gate_number for g in result.gates] == [1, 3, 4, 5]

    # Gate 1: Benchmark hurdle
    assert result.gates[0].passed is True
    # Gate 3: Sample size >= 30
    assert result.gates[1].passed is True
    assert result.combined_metrics.trades_count >= 30
    # Gate 4: PSR
    assert result.gates[2].passed is True
    assert result.confidence_score is not None
    assert result.confidence_score >= 0.60
    # Gate 5: Monte Carlo
    assert result.gates[3].passed is True

    # Overall verdict
    assert result.overall_passed is True
    assert result.rejection_reason is None
    assert "Clears Gate 1" in result.headline_verdict


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

