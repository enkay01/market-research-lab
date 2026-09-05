"""Deterministic Strategy Verdict engine foundation (Issue #114).

Orchestrates chronological 75/25 in-sample and out-of-sample partitioning,
continuous simulation with slice-based metric isolation, and Gate 1 (Benchmark
hurdle) evaluation.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import NamedTuple, Sequence

from .backtest import (
    BacktestError,
    BacktestSpecification,
    EquityPoint,
    ExecutionModelAssumptions,
    Trade,
    run_backtest,
)
from .json_types import JsonValue
from .market_data import CorporateAction, DailyBar

INFINITE_PROFIT_FACTOR = 100.0


@dataclass(frozen=True)
class StrategyVerdictSpecification:
    """Inputs for evaluating one Strategy verdict against a benchmark hurdle."""

    strategy_name: str
    strategy_revision: str = "v1"
    dataset_version_id: str = ""
    universe: tuple[str, ...] = ()
    security_id: str = ""
    benchmark_security_id: str = "SPY"
    start_date: str = ""
    end_date: str = ""
    starting_cash: float = 100_000.0
    parameters: dict[str, JsonValue] = field(default_factory=dict)
    holdout_ratio: float = 0.25
    execution: ExecutionModelAssumptions = field(default_factory=ExecutionModelAssumptions)


@dataclass(frozen=True)
class GateResult:
    """Result of one sequential hurdle gate evaluation."""

    gate_number: int
    name: str
    passed: bool
    metric_label: str
    metric_value: str
    threshold_label: str
    threshold_value: str
    verdict_note: str


@dataclass(frozen=True)
class PartitionMetrics:
    """Headline performance and risk metrics evaluated on a specific time partition."""

    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    benchmark_return: float
    win_rate: float
    profit_factor: float
    trades_count: int
    exposure_pct: float


@dataclass(frozen=True)
class VerdictEquityPoint:
    """Time-series observation combining strategy equity, benchmark equity, and holdout tag."""

    session_date: str
    strategy_equity: float
    benchmark_equity: float
    drawdown_pct: float
    is_holdout: bool


@dataclass(frozen=True)
class StrategyVerdictResult:
    """Immutable output of the Strategy Verdict engine."""

    specification: StrategyVerdictSpecification
    overall_passed: bool
    headline_verdict: str
    gates: tuple[GateResult, ...]
    in_sample_metrics: PartitionMetrics
    out_of_sample_metrics: PartitionMetrics
    combined_metrics: PartitionMetrics
    equity_curve: tuple[VerdictEquityPoint, ...]
    rejection_reason: str | None = None
    confidence_score: float | None = None



class ChronologicalPartition(NamedTuple):
    """Chronologically partitioned session dates."""

    in_sample: tuple[str, ...]
    out_of_sample: tuple[str, ...]


def partition_chronological_data(
    session_dates: Sequence[str],
    *,
    holdout_ratio: float = 0.25,
) -> ChronologicalPartition:
    """Partition unique session dates chronologically into in-sample and out-of-sample sets."""
    unique_dates = sorted(set(session_dates))
    total_sessions = len(unique_dates)
    if total_sessions < 2:
        raise BacktestError(
            f"Need at least 2 sessions to partition chronological data, got {total_sessions}."
        )

    if not 0.0 < holdout_ratio < 1.0:
        raise BacktestError(
            f"Holdout ratio must be between 0.0 and 1.0 exclusive, got {holdout_ratio}."
        )

    in_sample_count = max(
        1, min(total_sessions - 1, math.floor(total_sessions * (1.0 - holdout_ratio)))
    )
    in_sample = tuple(unique_dates[:in_sample_count])
    out_of_sample = tuple(unique_dates[in_sample_count:])
    return ChronologicalPartition(in_sample=in_sample, out_of_sample=out_of_sample)


def evaluate_gate_1(
    *,
    net_strategy_return: float,
    benchmark_return: float,
    benchmark_symbol: str = "SPY",
) -> GateResult:
    """Evaluate Gate 1 (Benchmark Hurdle).

    Passes if net strategy return strictly exceeds benchmark buy-and-hold return.
    Fails with 'Loses to benchmark after costs' otherwise.
    """
    passed = net_strategy_return > benchmark_return
    edge = net_strategy_return - benchmark_return

    sign_strat = "+" if net_strategy_return >= 0 else ""
    sign_bench = "+" if benchmark_return >= 0 else ""

    metric_value = f"{sign_strat}{net_strategy_return * 100:.1f}%"
    threshold_value = f"{sign_bench}{benchmark_return * 100:.1f}%"

    if passed:
        verdict_note = f"+{edge * 100:.1f}% Net Edge over Benchmark after friction"
    else:
        verdict_note = "Loses to benchmark after costs"

    return GateResult(
        gate_number=1,
        name="Benchmark Hurdle",
        passed=passed,
        metric_label="Strategy Return",
        metric_value=metric_value,
        threshold_label=f"{benchmark_symbol} Benchmark",
        threshold_value=threshold_value,
        verdict_note=verdict_note,
    )


@dataclass(frozen=True)
class MetricContext:
    """Contextual parameters for partition metrics calculation."""

    benchmark_return: float
    baseline_equity: float | None = None
    gross_exposure: float = 0.0


def _compute_metrics(
    equity_points: Sequence[EquityPoint],
    trades: Sequence[Trade],
    context: MetricContext,
) -> PartitionMetrics:
    """Calculate partition performance metrics from equity points and closed trades."""
    benchmark_return = context.benchmark_return
    baseline_equity = context.baseline_equity
    gross_exposure = context.gross_exposure
    if len(equity_points) < 1:
        return PartitionMetrics(
            total_return=0.0,
            cagr=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            benchmark_return=benchmark_return,
            win_rate=0.0,
            profit_factor=0.0,
            trades_count=0,
            exposure_pct=0.0,
        )

    start_equity = baseline_equity if baseline_equity is not None else equity_points[0].equity
    end_equity = equity_points[-1].equity
    total_return = (end_equity - start_equity) / start_equity if start_equity > 0.0 else 0.0

    n_days = len(equity_points)
    if total_return > -1.0 and n_days > 1:
        cagr = (1.0 + total_return) ** (252.0 / n_days) - 1.0
    else:
        cagr = total_return

    daily_returns: list[float] = []
    for i in range(1, len(equity_points)):
        prior = equity_points[i - 1].equity
        if prior > 0.0:
            daily_returns.append((equity_points[i].equity - prior) / prior)

    if len(daily_returns) >= 2:
        mean_return = statistics.fmean(daily_returns)
        stdev_return = statistics.stdev(daily_returns)
        sharpe = (mean_return / stdev_return) * math.sqrt(252.0) if stdev_return > 1e-9 else 0.0

        downside = [min(0.0, r) for r in daily_returns]
        downside_variance = sum(d * d for d in downside) / len(downside)
        downside_stdev = math.sqrt(downside_variance)
        sortino = (
            (mean_return / downside_stdev) * math.sqrt(252.0)
            if downside_stdev > 1e-9
            else 0.0
        )
    else:
        sharpe = 0.0
        sortino = 0.0

    peak = start_equity
    max_dd = 0.0
    for pt in equity_points:
        if pt.equity > peak:
            peak = pt.equity
        current_dd = (pt.equity / peak - 1.0) if peak > 0.0 else 0.0
        if current_dd < max_dd:
            max_dd = current_dd

    trades_count = len(trades)
    if trades_count > 0:
        wins = sum(1 for t in trades if t.pnl > 0.0)
        win_rate = wins / trades_count
        gains = sum(t.pnl for t in trades if t.pnl > 0.0)
        losses = sum(abs(t.pnl) for t in trades if t.pnl < 0.0)
        if losses > 1e-9:
            profit_factor = gains / losses
        elif gains > 0.0:
            profit_factor = INFINITE_PROFIT_FACTOR
        else:
            profit_factor = 0.0
    else:
        win_rate = 0.0
        profit_factor = 0.0

    return PartitionMetrics(
        total_return=total_return,
        cagr=cagr,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        benchmark_return=benchmark_return,
        win_rate=win_rate,
        profit_factor=profit_factor,
        trades_count=trades_count,
        exposure_pct=gross_exposure,
    )


def evaluate_strategy_verdict(
    specification: StrategyVerdictSpecification,
    *,
    bars: Sequence[DailyBar],
    corporate_actions: Sequence[CorporateAction] = (),
    benchmark_bars: Sequence[DailyBar] = (),
) -> StrategyVerdictResult:
    """Execute strategy evaluation, chronological partitioning, and Gate 1 verification."""
    all_bars: list[DailyBar] = list(bars)
    if benchmark_bars:
        all_bars.extend(benchmark_bars)

    effective_universe = specification.universe or (
        (specification.security_id,) if specification.security_id else ()
    )
    if not effective_universe:
        raise BacktestError("StrategyVerdictSpecification requires a universe or security_id.")

    backtest_spec = BacktestSpecification(
        strategy_name=specification.strategy_name,
        strategy_revision=specification.strategy_revision,
        dataset_version_id=specification.dataset_version_id,
        universe=effective_universe,
        benchmark_security_id=specification.benchmark_security_id,
        start_date=specification.start_date,
        end_date=specification.end_date,
        starting_cash=specification.starting_cash,
        parameters=specification.parameters,
        execution=specification.execution,
    )

    backtest_result = run_backtest(
        backtest_spec,
        bars=all_bars,
        corporate_actions=corporate_actions,
    )

    session_dates = [pt.session_date for pt in backtest_result.equity_curve]
    in_sample_dates, out_of_sample_dates = partition_chronological_data(
        session_dates,
        holdout_ratio=specification.holdout_ratio,
    )

    in_sample_set = set(in_sample_dates)
    out_of_sample_set = set(out_of_sample_dates)

    is_equity_points = [
        pt for pt in backtest_result.equity_curve if pt.session_date in in_sample_set
    ]
    oos_equity_points = [
        pt for pt in backtest_result.equity_curve if pt.session_date in out_of_sample_set
    ]

    # Partition trades by exit date
    is_trades = [t for t in backtest_result.trades if t.exit_date in in_sample_set]
    oos_trades = [t for t in backtest_result.trades if t.exit_date in out_of_sample_set]

    # Sliced benchmark returns
    bench_by_date = {pt.session_date: pt.equity for pt in backtest_result.benchmark_equity_curve}
    initial_cash = specification.starting_cash

    if backtest_result.benchmark_equity_curve:
        bench_start = backtest_result.benchmark_equity_curve[0].equity
        bench_end = backtest_result.benchmark_equity_curve[-1].equity
        comb_bench_return = (bench_end - bench_start) / bench_start if bench_start > 0 else 0.0

        is_bench_end = bench_by_date.get(in_sample_dates[-1], bench_start)
        is_bench_return = (is_bench_end - bench_start) / bench_start if bench_start > 0 else 0.0

        oos_bench_end = bench_by_date.get(out_of_sample_dates[-1], is_bench_end)
        oos_bench_return = (
            (oos_bench_end - is_bench_end) / is_bench_end if is_bench_end > 0 else 0.0
        )
    else:
        comb_bench_return = 0.0
        is_bench_return = 0.0
        oos_bench_return = 0.0

    combined_metrics = _compute_metrics(
        backtest_result.equity_curve,
        backtest_result.trades,
        MetricContext(
            benchmark_return=comb_bench_return,
            gross_exposure=backtest_result.metrics.gross_exposure,
        ),
    )

    in_sample_metrics = _compute_metrics(
        is_equity_points,
        is_trades,
        MetricContext(
            benchmark_return=is_bench_return,
            gross_exposure=backtest_result.metrics.gross_exposure,
        ),
    )

    baseline_for_oos = is_equity_points[-1].equity if is_equity_points else initial_cash
    out_of_sample_metrics = _compute_metrics(
        oos_equity_points,
        oos_trades,
        MetricContext(
            benchmark_return=oos_bench_return,
            baseline_equity=baseline_for_oos,
            gross_exposure=backtest_result.metrics.gross_exposure,
        ),
    )

    gate1 = evaluate_gate_1(
        net_strategy_return=combined_metrics.total_return,
        benchmark_return=comb_bench_return,
        benchmark_symbol=specification.benchmark_security_id or "SPY",
    )

    overall_passed = gate1.passed
    if overall_passed:
        headline_verdict = "Strategy Clears Gate 1 (Benchmark Hurdle)"
        rejection_reason = None
    else:
        headline_verdict = "Strategy Rejected: Loses to benchmark after costs"
        rejection_reason = "Loses to benchmark after costs"

    verdict_curve: list[VerdictEquityPoint] = []
    for pt in backtest_result.equity_curve:
        bench_val = bench_by_date.get(pt.session_date, initial_cash)
        verdict_curve.append(
            VerdictEquityPoint(
                session_date=pt.session_date,
                strategy_equity=pt.equity,
                benchmark_equity=bench_val,
                drawdown_pct=pt.drawdown * 100.0,
                is_holdout=(pt.session_date in out_of_sample_set),
            )
        )

    return StrategyVerdictResult(
        specification=specification,
        overall_passed=overall_passed,
        headline_verdict=headline_verdict,
        rejection_reason=rejection_reason,
        confidence_score=None,
        gates=(gate1,),
        in_sample_metrics=in_sample_metrics,
        out_of_sample_metrics=out_of_sample_metrics,
        combined_metrics=combined_metrics,
        equity_curve=tuple(verdict_curve),
    )
