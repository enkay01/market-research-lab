"""Domain unit tests for the market-wide diagnostic screener sweep engine (Issue #118)."""

from __future__ import annotations

import pandas as pd
import pytest

from market_research_lab.backtest import BacktestError, ExecutionModelAssumptions
from market_research_lab.market_data import DailyBar
from market_research_lab.strategy_screener import (
    DiagnosticBanner,
    ScreenerCandidate,
    StrategyScreenerSpecification,
    build_diagnostic_banner,
    evaluate_screener_sweep,
)


def _make_daily_bars(
    symbol: str,
    prices: list[float],
    start_date: str = "2024-01-02",
) -> list[DailyBar]:
    dates = pd.date_range(start_date, periods=len(prices), freq="B").strftime("%Y-%m-%d").tolist()
    bars: list[DailyBar] = []
    for d, p in zip(dates, prices):
        bars.append(
            DailyBar(
                security_id=symbol,
                session_date=d,
                open=p,
                high=p * 1.02,
                low=p * 0.98,
                close=p,
                volume=100_000.0,
                source="test",
                available_at=f"{d}T21:00:00Z",
            )
        )
    return bars


def test_screener_sweep_calculates_net_edge_and_sorts_descending() -> None:
    """Screener calculates net edge as strategy - benchmark return and sorts candidates descending."""
    # Strong upward trend for AAPL (lots of gains)
    aapl_prices = [100.0 + i * 3.0 for i in range(25)]
    # Flat / mild chop for MSFT
    msft_prices = [100.0 + (i % 3) * 0.5 for i in range(25)]
    # Downward trend for TSLA
    tsla_prices = [200.0 - i * 2.5 for i in range(25)]
    # Moderate benchmark trend for SPY (+1.0 per bar)
    spy_prices = [400.0 + i * 1.0 for i in range(25)]

    all_bars = (
        _make_daily_bars("AAPL", aapl_prices)
        + _make_daily_bars("MSFT", msft_prices)
        + _make_daily_bars("TSLA", tsla_prices)
        + _make_daily_bars("SPY", spy_prices)
    )

    spec = StrategyScreenerSpecification(
        strategy_name="trend_exhaustion",
        universe=("AAPL", "MSFT", "TSLA"),
        benchmark_security_id="SPY",
        parameters={"fast_period": 2, "slow_period": 5},
    )

    result = evaluate_screener_sweep(spec, bars=all_bars)

    assert result.benchmark_symbol == "SPY"
    assert len(result.candidates) == 3

    # Ranking must be 1, 2, 3
    assert [c.rank for c in result.candidates] == [1, 2, 3]

    # Verify descending sort order by net edge
    net_edges = [c.net_edge for c in result.candidates]
    assert net_edges == sorted(net_edges, reverse=True)

    # Net edge must equal strategy_return - benchmark_return (within rounding tolerance)
    for c in result.candidates:
        expected_edge = round(c.strategy_return - c.benchmark_return, 6)
        assert abs(c.net_edge - expected_edge) < 1e-5

    # Check candidate metadata enrichment
    aapl_cand = next(c for c in result.candidates if c.symbol == "AAPL")
    assert aapl_cand.name == "Apple Inc."
    assert aapl_cand.sector == "Technology"


def test_screener_sweep_diagnostic_banner_market_wide_edge() -> None:
    """Banner classifies edge as systematic market-wide when >= 50% have positive net edge."""
    candidates = [
        ScreenerCandidate(
            rank=1,
            symbol="AAPL",
            name="Apple Inc.",
            sector="Technology",
            strategy_return=0.25,
            benchmark_return=0.10,
            net_edge=0.15,
            win_rate=0.70,
            profit_factor=2.5,
            trades_count=10,
            status="PASS",
        ),
        ScreenerCandidate(
            rank=2,
            symbol="MSFT",
            name="Microsoft Corp.",
            sector="Technology",
            strategy_return=0.18,
            benchmark_return=0.10,
            net_edge=0.08,
            win_rate=0.60,
            profit_factor=1.8,
            trades_count=8,
            status="PASS",
        ),
        ScreenerCandidate(
            rank=3,
            symbol="TSLA",
            name="Tesla Inc.",
            sector="Consumer Discretionary",
            strategy_return=0.05,
            benchmark_return=0.10,
            net_edge=-0.05,
            win_rate=0.40,
            profit_factor=0.8,
            trades_count=6,
            status="FAIL",
        ),
    ]

    banner = build_diagnostic_banner(candidates, benchmark_symbol="SPY")

    assert banner.market_edge_detected is True
    assert banner.edge_distribution == "MARKET_WIDE"
    assert banner.headline == "Market-Wide Systematic Edge"
    assert banner.total_securities == 3
    assert banner.positive_edge_securities == 2
    assert banner.market_breadth_pct == 66.7
    assert "2 of 3 securities" in banner.summary
    assert "SPY" in banner.summary


def test_screener_sweep_diagnostic_banner_isolated_edge() -> None:
    """Banner classifies edge as isolated when > 0 but < 50% have positive net edge."""
    candidates = [
        ScreenerCandidate(
            rank=1,
            symbol="NVDA",
            name="NVIDIA Corp.",
            sector="Technology",
            strategy_return=0.35,
            benchmark_return=0.10,
            net_edge=0.25,
            win_rate=0.80,
            profit_factor=3.0,
            trades_count=12,
            status="PASS",
        ),
        ScreenerCandidate(
            rank=2,
            symbol="XOM",
            name="Exxon Mobil Corp.",
            sector="Energy",
            strategy_return=0.02,
            benchmark_return=0.10,
            net_edge=-0.08,
            win_rate=0.35,
            profit_factor=0.7,
            trades_count=5,
            status="FAIL",
        ),
        ScreenerCandidate(
            rank=3,
            symbol="JNJ",
            name="Johnson & Johnson",
            sector="Health Care",
            strategy_return=-0.04,
            benchmark_return=0.10,
            net_edge=-0.14,
            win_rate=0.20,
            profit_factor=0.4,
            trades_count=4,
            status="FAIL",
        ),
    ]

    banner = build_diagnostic_banner(candidates, benchmark_symbol="SPY")

    assert banner.market_edge_detected is False
    assert banner.edge_distribution == "ISOLATED"
    assert banner.headline == "Edge Isolated to Specific Securities"
    assert banner.total_securities == 3
    assert banner.positive_edge_securities == 1
    assert banner.market_breadth_pct == 33.3
    assert "isolated to 1 of 3" in banner.summary


def test_screener_sweep_diagnostic_banner_no_edge() -> None:
    """Banner classifies edge as none when zero candidates beat the benchmark."""
    candidates = [
        ScreenerCandidate(
            rank=1,
            symbol="AAPL",
            name="Apple Inc.",
            sector="Technology",
            strategy_return=0.04,
            benchmark_return=0.10,
            net_edge=-0.06,
            win_rate=0.30,
            profit_factor=0.6,
            trades_count=4,
            status="FAIL",
        ),
        ScreenerCandidate(
            rank=2,
            symbol="MSFT",
            name="Microsoft Corp.",
            sector="Technology",
            strategy_return=-0.02,
            benchmark_return=0.10,
            net_edge=-0.12,
            win_rate=0.25,
            profit_factor=0.5,
            trades_count=3,
            status="FAIL",
        ),
    ]

    banner = build_diagnostic_banner(candidates, benchmark_symbol="SPY")

    assert banner.market_edge_detected is False
    assert banner.edge_distribution == "NONE"
    assert banner.headline == "No Market Edge Detected"
    assert banner.positive_edge_securities == 0
    assert banner.market_breadth_pct == 0.0


def test_screener_sweep_validation_errors() -> None:
    """Validation errors for empty universe, non-positive starting cash, or missing benchmark."""
    prices = [100.0 + i for i in range(10)]
    bars = _make_daily_bars("AAPL", prices)

    # Empty universe
    with pytest.raises(BacktestError, match="requires at least one security"):
        evaluate_screener_sweep(
            StrategyScreenerSpecification(strategy_name="trend_exhaustion", universe=()),
            bars=bars,
        )

    # Starting cash <= 0
    with pytest.raises(BacktestError, match="starting_cash must be strictly positive"):
        evaluate_screener_sweep(
            StrategyScreenerSpecification(
                strategy_name="trend_exhaustion",
                universe=("AAPL",),
                starting_cash=0.0,
            ),
            bars=bars,
        )

    # Missing benchmark bars
    with pytest.raises(BacktestError, match="has no daily bars"):
        evaluate_screener_sweep(
            StrategyScreenerSpecification(
                strategy_name="trend_exhaustion",
                universe=("AAPL",),
                benchmark_security_id="NONEXISTENT",
            ),
            bars=bars,
        )


def test_screener_sweep_insufficient_bars_handled_gracefully() -> None:
    """Security with fewer than 2 bars does not crash sweep and is ranked at the bottom."""
    aapl_bars = _make_daily_bars("AAPL", [100.0 + i for i in range(20)])
    spy_bars = _make_daily_bars("SPY", [400.0 + i for i in range(20)])
    # Single bar for TINY
    tiny_bar = DailyBar(
        security_id="TINY",
        session_date="2024-01-02",
        open=50.0,
        high=51.0,
        low=49.0,
        close=50.0,
        volume=1000.0,
        source="test",
        available_at="2024-01-02T21:00:00Z",
    )

    spec = StrategyScreenerSpecification(
        strategy_name="trend_exhaustion",
        universe=("AAPL", "TINY"),
        benchmark_security_id="SPY",
        parameters={"fast_period": 2, "slow_period": 5},
    )

    result = evaluate_screener_sweep(spec, bars=[*aapl_bars, tiny_bar, *spy_bars])
    assert len(result.candidates) == 2
    tiny_cand = next(c for c in result.candidates if c.symbol == "TINY")
    assert tiny_cand.trades_count == 0
    assert tiny_cand.strategy_return == 0.0
    assert tiny_cand.status == "FAIL"
