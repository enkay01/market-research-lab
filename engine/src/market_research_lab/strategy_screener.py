"""Market-wide diagnostic screener sweep engine (Issue #118).

Evaluates a strategy rule independently across every Security in a dataset
against the benchmark, calculates net edge, win rate, trade count, and profit
factor, ranks candidates descending by net edge, and constructs a diagnostic
banner surfacing whether edge exists systematically across the market or is
isolated to specific Securities.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

from .backtest import (
    BacktestError,
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from .json_types import JsonValue
from .market_data import CorporateAction, DailyBar
from .strategy_verdict import INFINITE_PROFIT_FACTOR

KNOWN_SECURITY_NAMES: dict[str, str] = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "GOOGL": "Alphabet Inc. (Class A)",
    "GOOG": "Alphabet Inc. (Class C)",
    "AMZN": "Amazon.com Inc.",
    "NVDA": "NVIDIA Corp.",
    "META": "Meta Platforms Inc.",
    "TSLA": "Tesla Inc.",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "SPDR Dow Jones Industrial Average ETF",
    "XLK": "Technology Select Sector SPDR Fund",
    "XLF": "Financial Select Sector SPDR Fund",
    "XLE": "Energy Select Sector SPDR Fund",
    "XLV": "Health Care Select Sector SPDR Fund",
    "XLI": "Industrial Select Sector SPDR Fund",
    "XLP": "Consumer Staples Select Sector SPDR Fund",
    "XLY": "Consumer Discretionary Select Sector SPDR Fund",
    "XLU": "Utilities Select Sector SPDR Fund",
    "XLC": "Communication Services Select Sector SPDR Fund",
    "XLB": "Materials Select Sector SPDR Fund",
    "XLRE": "Real Estate Select Sector SPDR Fund",
    "JPM": "JPMorgan Chase & Co.",
    "BAC": "Bank of America Corp.",
    "V": "Visa Inc.",
    "MA": "Mastercard Inc.",
    "WMT": "Walmart Inc.",
    "PG": "Procter & Gamble Co.",
    "JNJ": "Johnson & Johnson",
    "LLY": "Eli Lilly and Co.",
    "UNH": "UnitedHealth Group Inc.",
    "XOM": "Exxon Mobil Corp.",
    "CVX": "Chevron Corp.",
    "HD": "The Home Depot Inc.",
    "COST": "Costco Wholesale Corp.",
    "NFLX": "Netflix Inc.",
    "DIS": "The Walt Disney Company",
}

KNOWN_SECTORS: dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "XLK": "Technology",
    "GOOGL": "Communication Services",
    "GOOG": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    "DIS": "Communication Services",
    "XLC": "Communication Services",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "XLY": "Consumer Discretionary",
    "JPM": "Financials",
    "BAC": "Financials",
    "V": "Financials",
    "MA": "Financials",
    "XLF": "Financials",
    "XOM": "Energy",
    "CVX": "Energy",
    "XLE": "Energy",
    "JNJ": "Health Care",
    "LLY": "Health Care",
    "UNH": "Health Care",
    "XLV": "Health Care",
    "WMT": "Consumer Staples",
    "PG": "Consumer Staples",
    "COST": "Consumer Staples",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "SPY": "Broad Market Index",
    "QQQ": "Large-Cap Growth Index",
    "IWM": "Small-Cap Index",
    "DIA": "Mega-Cap Value Index",
}


@dataclass(frozen=True)
class ScreenerCandidate:
    """One candidate security evaluated in the diagnostic screener sweep."""

    rank: int
    symbol: str
    name: str
    sector: str
    strategy_return: float
    benchmark_return: float
    net_edge: float
    win_rate: float
    profit_factor: float
    trades_count: int
    status: str


@dataclass(frozen=True)
class DiagnosticBanner:
    """Diagnostic market breadth assessment surfacing systematic vs isolated edge."""

    market_edge_detected: bool
    edge_distribution: str
    headline: str
    summary: str
    total_securities: int
    positive_edge_securities: int
    market_breadth_pct: float


@dataclass(frozen=True)
class StrategyScreenerSpecification:
    """Inputs for evaluating one Strategy across all candidate securities."""

    strategy_name: str
    strategy_revision: str = "v1"
    dataset_version_id: str = ""
    universe: tuple[str, ...] = ()
    benchmark_security_id: str = "SPY"
    start_date: str = ""
    end_date: str = ""
    starting_cash: float = 100_000.0
    parameters: dict[str, JsonValue] = field(default_factory=dict)
    execution: ExecutionModelAssumptions = field(default_factory=ExecutionModelAssumptions)
    security_names: dict[str, str] = field(default_factory=dict)
    security_sectors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyScreenerResult:
    """Immutable output of the market-wide diagnostic screener sweep."""

    specification: StrategyScreenerSpecification
    benchmark_symbol: str
    diagnostic_banner: DiagnosticBanner
    candidates: tuple[ScreenerCandidate, ...]


def build_diagnostic_banner(
    candidates: Sequence[ScreenerCandidate],
    benchmark_symbol: str = "SPY",
) -> DiagnosticBanner:
    """Classify cross-market edge breadth from evaluated candidate rankings."""
    total_count = len(candidates)
    if total_count == 0:
        return DiagnosticBanner(
            market_edge_detected=False,
            edge_distribution="NONE",
            headline="No Candidates Evaluated",
            summary="Zero securities were provided for market-wide screening.",
            total_securities=0,
            positive_edge_securities=0,
            market_breadth_pct=0.0,
        )

    positive_count = sum(1 for c in candidates if c.net_edge > 0.0 and c.trades_count > 0)
    breadth_pct = (positive_count / total_count) * 100.0

    if breadth_pct >= 50.0:
        headline = "Market-Wide Systematic Edge"
        edge_distribution = "MARKET_WIDE"
        market_edge_detected = True
        summary = (
            f"Strategy generated positive net edge across {positive_count} of {total_count} "
            f"securities ({breadth_pct:.1f}%). Systematic edge persists across the broad market "
            f"relative to {benchmark_symbol}."
        )
    elif positive_count > 0:
        headline = "Edge Isolated to Specific Securities"
        edge_distribution = "ISOLATED"
        market_edge_detected = False
        summary = (
            f"Strategy edge is isolated to {positive_count} of {total_count} "
            f"securities ({breadth_pct:.1f}%). The majority of the market failed to clear "
            f"{benchmark_symbol}, indicating symbol-specific selection rather than broad market edge."
        )
    else:
        headline = "No Market Edge Detected"
        edge_distribution = "NONE"
        market_edge_detected = False
        summary = (
            f"Strategy failed to generate positive net edge on any of the {total_count} "
            f"screened securities against {benchmark_symbol}."
        )

    return DiagnosticBanner(
        market_edge_detected=market_edge_detected,
        edge_distribution=edge_distribution,
        headline=headline,
        summary=summary,
        total_securities=total_count,
        positive_edge_securities=positive_count,
        market_breadth_pct=round(breadth_pct, 1),
    )


def evaluate_screener_sweep(
    specification: StrategyScreenerSpecification,
    *,
    bars: Sequence[DailyBar],
    corporate_actions: Sequence[CorporateAction] = (),
    benchmark_bars: Sequence[DailyBar] = (),
) -> StrategyScreenerResult:
    """Execute strategy screening sweep across every Security in specification universe."""
    if not specification.universe:
        raise BacktestError("StrategyScreenerSpecification requires at least one security in universe.")

    if specification.starting_cash <= 0.0:
        raise BacktestError("starting_cash must be strictly positive.")

    all_bars = list(bars)
    if benchmark_bars:
        all_bars.extend(benchmark_bars)

    bench_symbol = specification.benchmark_security_id or "SPY"
    has_bench_bars = any(b.security_id == bench_symbol for b in all_bars)
    if not has_bench_bars:
        raise BacktestError(f"Benchmark security '{bench_symbol}' has no daily bars.")

    # Partition bars and corporate actions by security_id
    bars_by_sec: dict[str, list[DailyBar]] = {}
    for bar in all_bars:
        bars_by_sec.setdefault(bar.security_id, []).append(bar)

    actions_by_sec: dict[str, list[CorporateAction]] = {}
    for action in corporate_actions:
        actions_by_sec.setdefault(action.security_id, []).append(action)

    bench_bars_list = bars_by_sec.get(bench_symbol, [])
    bench_actions_list = actions_by_sec.get(bench_symbol, [])

    session_dates = sorted({b.session_date for b in all_bars})
    start_date = specification.start_date or (session_dates[0] if session_dates else "")
    end_date = specification.end_date or (session_dates[-1] if session_dates else "")

    raw_candidates: list[ScreenerCandidate] = []

    for sym in specification.universe:
        sec_bars = bars_by_sec.get(sym, [])
        sec_actions = actions_by_sec.get(sym, [])

        name = specification.security_names.get(sym) or KNOWN_SECURITY_NAMES.get(sym, sym)
        sector = specification.security_sectors.get(sym) or KNOWN_SECTORS.get(sym, "General")

        if len(sec_bars) < 2:
            raw_candidates.append(
                ScreenerCandidate(
                    rank=0,
                    symbol=sym,
                    name=name,
                    sector=sector,
                    strategy_return=0.0,
                    benchmark_return=0.0,
                    net_edge=0.0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    trades_count=0,
                    status="FAIL",
                )
            )
            continue

        # Combine security bars and benchmark bars if different
        sweep_bars = list(sec_bars)
        sweep_actions = list(sec_actions)
        if sym != bench_symbol:
            sweep_bars.extend(bench_bars_list)
            sweep_actions.extend(bench_actions_list)

        backtest_spec = BacktestSpecification(
            strategy_name=specification.strategy_name,
            strategy_revision=specification.strategy_revision,
            dataset_version_id=specification.dataset_version_id,
            universe=(sym,),
            benchmark_security_id=bench_symbol,
            start_date=start_date,
            end_date=end_date,
            starting_cash=specification.starting_cash,
            parameters=specification.parameters,
            execution=specification.execution,
        )

        result = run_backtest(
            backtest_spec,
            bars=sweep_bars,
            corporate_actions=sweep_actions,
        )

        if result.equity_curve:
            strat_start = specification.starting_cash
            strat_end = result.equity_curve[-1].equity
            strat_return = (strat_end - strat_start) / strat_start if strat_start > 0.0 else 0.0
        else:
            strat_return = 0.0

        if result.benchmark_equity_curve:
            bench_start = result.benchmark_equity_curve[0].equity
            bench_end = result.benchmark_equity_curve[-1].equity
            bench_return = (bench_end - bench_start) / bench_start if bench_start > 0.0 else 0.0
        else:
            bench_return = 0.0

        net_edge = strat_return - bench_return
        trades_count = len(result.trades)

        if trades_count > 0:
            wins = sum(1 for t in result.trades if t.pnl > 0.0)
            win_rate = wins / trades_count
            gains = sum(t.pnl for t in result.trades if t.pnl > 0.0)
            losses = sum(abs(t.pnl) for t in result.trades if t.pnl < 0.0)
            if losses > 1e-9:
                profit_factor = gains / losses
            elif gains > 0.0:
                profit_factor = INFINITE_PROFIT_FACTOR
            else:
                profit_factor = 0.0
        else:
            win_rate = 0.0
            profit_factor = 0.0

        status = "PASS" if (net_edge > 0.0 and trades_count > 0) else "FAIL"

        raw_candidates.append(
            ScreenerCandidate(
                rank=0,
                symbol=sym,
                name=name,
                sector=sector,
                strategy_return=round(strat_return, 6),
                benchmark_return=round(bench_return, 6),
                net_edge=round(net_edge, 6),
                win_rate=round(win_rate, 4),
                profit_factor=round(profit_factor, 4),
                trades_count=trades_count,
                status=status,
            )
        )

    # Sort descending by net_edge, then profit_factor, then trades_count
    sorted_candidates = sorted(
        raw_candidates,
        key=lambda c: (c.net_edge, c.profit_factor, c.trades_count),
        reverse=True,
    )

    # Assign 1-indexed rank
    ranked_candidates = tuple(
        replace(c, rank=i + 1) for i, c in enumerate(sorted_candidates)
    )

    banner = build_diagnostic_banner(ranked_candidates, benchmark_symbol=bench_symbol)

    return StrategyScreenerResult(
        specification=specification,
        benchmark_symbol=bench_symbol,
        diagnostic_banner=banner,
        candidates=ranked_candidates,
    )
