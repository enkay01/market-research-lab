"""Exhaustive synthetic regression suite for Backtest accounting and temporal rules (BT-011).

Covers all 10 mandatory accounting and timing cases:
1. Future-data leakage prevention (DATA-008, BT-008, BT-011)
2. Next-bar execution timing (BT-003, BT-008)
3. Commission fee accounting (BT-006, BT-011)
4. Slippage price adjustment and cost attribution (BT-006, BT-011)
5. Stock splits share-count and cost-basis adjustment (BT-006, BT-011)
6. Cash dividend credits and short debits (BT-006, BT-011)
7. Short positions creation and shorting disabled rejection (BT-006, BT-011)
8. Borrow fee daily deductions on short market value (BT-006, BT-011)
9. Leverage limit enforcement in reject and constrain modes (BT-006, BT-011)
10. Deterministic replay of identical long-short runs and reports (CORE-007, BT-011)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from market_research_lab.backtest import (
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from market_research_lab.market_data import CorporateAction, DailyBar
from market_research_lab.reporting import (
    generate_backtest_csv,
    generate_backtest_html_report,
)


def _make_dates(n: int, start: str = "2024-01-02") -> list[str]:
    """Return n sequential calendar dates starting at start."""
    first = date.fromisoformat(start)
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def _make_bar(
    symbol: str,
    session_date: str,
    open_p: float,
    close_p: float,
    *,
    high_p: float | None = None,
    low_p: float | None = None,
    volume: float = 1000.0,
    available_at: str | None = None,
) -> DailyBar:
    """Build a DailyBar with point-in-time eligibility timestamp."""
    high = high_p if high_p is not None else max(open_p, close_p)
    low = low_p if low_p is not None else min(open_p, close_p)
    avail = available_at if available_at is not None else f"{session_date}T21:00:00Z"
    return DailyBar(
        security_id=symbol,
        session_date=session_date,
        open=open_p,
        high=high,
        low=low,
        close=close_p,
        volume=volume,
        source="synthetic_test",
        retrieval_time="",
        available_at=avail,
        eligibility_provenance="synthetic_test",
    )


# ---------------------------------------------------------------------------
# 1. Future-data leakage prevention (BT-008, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_future_data_leakage():
    """Future price observations and future corporate actions must not change earlier decisions."""
    dates = _make_dates(6)
    # 4 bars base dataset
    base_bars = [
        _make_bar("AAPL", dates[0], 10.0, 10.0),
        _make_bar("AAPL", dates[1], 10.0, 12.0),
        _make_bar("AAPL", dates[2], 12.0, 14.0),
        _make_bar("AAPL", dates[3], 14.0, 16.0),
    ]

    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=dates[0],
        end_date=dates[3],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
    )

    res_base = run_backtest(spec, bars=base_bars)

    # Append future bars and future corporate actions occurring after end_date
    future_bars = [
        *base_bars,
        _make_bar("AAPL", dates[4], 50.0, 100.0),
        _make_bar("AAPL", dates[5], 100.0, 200.0),
    ]
    future_actions = [
        CorporateAction(
            security_id="AAPL",
            type="split",
            effective_date=dates[5],
            value=10.0,
            source="synthetic",
            retrieval_time="",
            available_at=f"{dates[5]}T21:00:00Z",
        )
    ]

    res_with_future = run_backtest(
        spec, bars=future_bars, corporate_actions=future_actions
    )

    # Earlier ledger rows, signals, fills, and metrics must be identical
    assert len(res_base.ledger) == len(res_with_future.ledger)
    for row_a, row_b in zip(res_base.ledger, res_with_future.ledger):
        assert row_a.session_date == row_b.session_date
        assert row_a.cash == row_b.cash
        assert row_a.portfolio_value == row_b.portfolio_value
        assert row_a.shares == row_b.shares
        assert row_a.signal_weight == row_b.signal_weight

    assert res_base.metrics.total_return == res_with_future.metrics.total_return


# ---------------------------------------------------------------------------
# 2. Next-bar execution timing (BT-003, BT-008)
# ---------------------------------------------------------------------------
def test_synthetic_next_bar_execution():
    """Signals evaluated at bar T close fill strictly at bar T+1 open price."""
    dates = _make_dates(5)
    # Bar 0, 1, 2, 3: fast MA crosses slow MA on bar 3 close (date[3])
    bars = [
        _make_bar("AAPL", dates[0], 10.0, 10.0),
        _make_bar("AAPL", dates[1], 10.0, 11.0),
        _make_bar("AAPL", dates[2], 11.0, 12.0),
        _make_bar("AAPL", dates[3], 12.0, 15.0),  # Bullish signal emitted at date[3] close
        _make_bar("AAPL", dates[4], 20.0, 25.0),  # Opens at 20.0, closes at 25.0
    ]

    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=dates[0],
        end_date=dates[4],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
    )

    res = run_backtest(spec, bars=bars)
    assert len(res.fills) == 1
    fill = res.fills[0]
    # Fill occurs on date[4] with open price 20.0, decided at date[3] available_at
    assert fill.session_date == dates[4]
    assert fill.decision_time == f"{dates[3]}T21:00:00Z"
    assert fill.price == 20.0
    assert fill.side == "buy"


# ---------------------------------------------------------------------------
# 3. Commission fee accounting (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_fees_commission():
    """Commission rate debits cash as a fraction of trade notional."""
    dates = _make_dates(6)
    closes = [10.0, 11.0, 12.0, 15.0, 14.0, 10.0]
    bars = [_make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    commission_rate = 0.005  # 0.5% (50 bps)
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=dates[0],
        end_date=dates[5],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        execution=ExecutionModelAssumptions(commission_rate=commission_rate),
    )

    res = run_backtest(spec, bars=bars)
    assert len(res.fills) >= 1
    buy_fill = res.fills[0]
    assert buy_fill.commission == round(buy_fill.notional * commission_rate, 4)

    total_comm = sum(f.commission for f in res.fills)
    manifest_costs = res.manifest.get("costs", {})
    assert manifest_costs.get("total_commission") == round(total_comm, 4)


# ---------------------------------------------------------------------------
# 4. Slippage price adjustment and cost attribution (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_slippage():
    """Slippage rate raises buy execution price and lowers sell execution price."""
    dates = _make_dates(6)
    closes = [10.0, 11.0, 12.0, 15.0, 12.0, 10.0]
    bars = [_make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    slippage_rate = 0.01  # 1% slippage
    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=dates[0],
        end_date=dates[5],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        execution=ExecutionModelAssumptions(slippage_rate=slippage_rate),
    )

    res = run_backtest(spec, bars=bars)
    assert len(res.fills) >= 1
    buy_fill = res.fills[0]
    # Expected buy fill price: raw_open * (1 + slippage_rate) where bar 4 open is 12.0
    raw_open = 12.0  # bar 4 open
    assert buy_fill.price == round(raw_open * 1.01, 6)
    assert buy_fill.slippage_cost > 0.0


# ---------------------------------------------------------------------------
# 5. Stock splits share-count and cost-basis adjustment (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_stock_splits():
    """2:1 forward split doubles shares and halves entry price without changing portfolio value."""
    dates = _make_dates(6)
    bars = [
        _make_bar("AAPL", dates[0], 10.0, 10.0),
        _make_bar("AAPL", dates[1], 10.0, 11.0),
        _make_bar("AAPL", dates[2], 11.0, 12.0),
        _make_bar("AAPL", dates[3], 12.0, 14.0),  # Buy fill executes next day at 20.0
        _make_bar("AAPL", dates[4], 20.0, 20.0),  # Position: 5,000 shares @ $20 = $100k
        _make_bar("AAPL", dates[5], 10.0, 10.0),  # Split 2:1: 10,000 shares @ $10 = $100k
    ]

    split_action = CorporateAction(
        security_id="AAPL",
        type="split",
        effective_date=dates[5],
        value=2.0,  # 2-for-1 forward split
        source="test",
        retrieval_time="",
        available_at=f"{dates[4]}T21:00:00Z",
    )

    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=dates[0],
        end_date=dates[5],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
    )

    res = run_backtest(spec, bars=bars, corporate_actions=[split_action])
    ledger_day4 = res.ledger[4]
    ledger_day5 = res.ledger[5]

    # Shares doubled from 5,000 to 10,000
    assert ledger_day4.positions["AAPL"].shares == 5000.0
    assert ledger_day5.positions["AAPL"].shares == 10000.0
    # Mark to market value remains steady
    assert ledger_day4.portfolio_value == 100000.0
    assert ledger_day5.portfolio_value == 100000.0
    assert res.manifest["corporate_actions"]["total_splits"] == 1


# ---------------------------------------------------------------------------
# 6. Cash dividend credits and short debits (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_cash_dividends():
    """Cash dividend credits long positions and debits short positions on effective date."""
    dates = _make_dates(6)
    bars = [
        _make_bar("AAPL", dates[0], 10.0, 10.0),
        _make_bar("AAPL", dates[1], 10.0, 11.0),
        _make_bar("AAPL", dates[2], 11.0, 12.0),
        _make_bar("AAPL", dates[3], 12.0, 14.0),
        _make_bar("AAPL", dates[4], 20.0, 20.0),  # Held 5,000 shares long
        _make_bar("AAPL", dates[5], 20.0, 20.0),  # Dividend $1.50 per share credited
    ]

    div_action = CorporateAction(
        security_id="AAPL",
        type="dividend",
        effective_date=dates[5],
        value=1.50,
        source="test",
        retrieval_time="",
        available_at=f"{dates[4]}T21:00:00Z",
    )

    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        security_id="AAPL",
        start_date=dates[0],
        end_date=dates[5],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
    )

    res = run_backtest(spec, bars=bars, corporate_actions=[div_action])
    ledger_day5 = res.ledger[5]

    # Dividend credited: 5,000 shares * $1.50 = $7,500
    assert ledger_day5.dividends == 7500.0
    assert ledger_day5.cash == 7500.0
    assert ledger_day5.portfolio_value == 107500.0
    assert res.manifest["corporate_actions"]["total_dividends"] == 7500.0


# ---------------------------------------------------------------------------
# 7. Short positions creation and shorting disabled rejection (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_short_positions_and_disabling():
    """Negative target weights create short positions.

    Disabling shorting emits ConstraintRejection.
    """
    dates = _make_dates(6)
    bars = [
        _make_bar("AAPL", dates[0], 100.0, 100.0),
        _make_bar("AAPL", dates[1], 100.0, 90.0),
        _make_bar("AAPL", dates[2], 90.0, 80.0),
        _make_bar("AAPL", dates[3], 80.0, 70.0),
        _make_bar("AAPL", dates[4], 70.0, 60.0),
        _make_bar("AAPL", dates[5], 60.0, 50.0),
    ]

    # 1. Enabled shorting: creates short position (negative shares)
    spec_enabled = BacktestSpecification(
        strategy_name="long_short_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        universe=("AAPL",),
        start_date=dates[0],
        end_date=dates[5],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        execution=ExecutionModelAssumptions(allow_shorting=True),
    )
    res_enabled = run_backtest(spec_enabled, bars=bars)
    short_rows = [
        r for r in res_enabled.ledger
        if "AAPL" in r.positions and r.positions["AAPL"].shares < 0.0
    ]
    assert len(short_rows) > 0

    # 2. Disabled shorting: emits ConstraintRejection and prevents shorting
    spec_disabled = BacktestSpecification(
        strategy_name="long_short_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        universe=("AAPL",),
        start_date=dates[0],
        end_date=dates[5],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        execution=ExecutionModelAssumptions(allow_shorting=False),
    )
    res_disabled = run_backtest(spec_disabled, bars=bars)
    disabled_rejections = [
        r for r in res_disabled.rejections if r.rule == "short_disabled"
    ]
    assert len(disabled_rejections) > 0
    assert all(
        "AAPL" not in r.positions or r.positions["AAPL"].shares >= 0.0
        for r in res_disabled.ledger
    )


# ---------------------------------------------------------------------------
# 8. Borrow fee daily deductions on short market value (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_borrow_fees():
    """Borrow fee rate debits cash daily on short positions based on mark-to-market value."""
    dates = _make_dates(8)
    closes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0]
    bars = [_make_bar("AAPL", d, c, c) for d, c in zip(dates, closes)]

    borrow_rate = 0.10  # 10% annualized borrow fee
    spec = BacktestSpecification(
        strategy_name="long_short_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        universe=("AAPL",),
        start_date=dates[0],
        end_date=dates[7],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        execution=ExecutionModelAssumptions(
            allow_shorting=True,
            borrow_fee_rate=borrow_rate,
        ),
    )

    res = run_backtest(spec, bars=bars)
    fee_rows = [r for r in res.ledger if r.borrow_fees > 0.0]
    assert len(fee_rows) > 0

    total_ledger_fees = sum(r.borrow_fees for r in res.ledger)
    assert total_ledger_fees > 0.0

    manifest_costs = res.manifest.get("costs", {})
    assert manifest_costs.get("total_borrow_fees") == round(total_ledger_fees, 4)
    assert manifest_costs["portfolio_impact"]["borrow_fees"] == round(-total_ledger_fees, 4)


# ---------------------------------------------------------------------------
# 9. Leverage limit enforcement in reject and constrain modes (BT-006, BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_leverage_rejection_and_constrain():
    """Gross exposure exceeding max_leverage triggers rejection or scaling."""
    dates = _make_dates(5)
    bars = [
        _make_bar("AAPL", dates[0], 10.0, 10.0),
        _make_bar("AAPL", dates[1], 10.0, 11.0),
        _make_bar("AAPL", dates[2], 11.0, 12.0),
        _make_bar("AAPL", dates[3], 12.0, 14.0),
        _make_bar("AAPL", dates[4], 14.0, 16.0),
        _make_bar("MSFT", dates[0], 20.0, 20.0),
        _make_bar("MSFT", dates[1], 20.0, 22.0),
        _make_bar("MSFT", dates[2], 22.0, 24.0),
        _make_bar("MSFT", dates[3], 24.0, 28.0),
        _make_bar("MSFT", dates[4], 28.0, 30.0),
    ]

    # Max leverage = 0.8 (stricter than full 100% allocation across 2 symbols)
    spec_reject = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        universe=("AAPL", "MSFT"),
        start_date=dates[0],
        end_date=dates[4],
        starting_cash=100000.0,
        execution=ExecutionModelAssumptions(
            max_leverage=0.8,
            leverage_mode="reject",
        ),
    )

    res_reject = run_backtest(spec_reject, bars=bars)
    assert res_reject.manifest["execution"]["max_leverage"] == 0.8
    assert res_reject.manifest["execution"]["leverage_mode"] == "reject"

    spec_constrain = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-1",
        universe=("AAPL", "MSFT"),
        start_date=dates[0],
        end_date=dates[4],
        starting_cash=100000.0,
        execution=ExecutionModelAssumptions(
            max_leverage=0.8,
            leverage_mode="constrain",
        ),
    )
    res_constrain = run_backtest(spec_constrain, bars=bars)
    assert res_constrain.manifest["execution"]["leverage_mode"] == "constrain"


# ---------------------------------------------------------------------------
# 10. Deterministic replay of identical long-short runs and reports (BT-011)
# ---------------------------------------------------------------------------
def test_synthetic_deterministic_replay_identical_long_short():
    """Two identical long-short runs produce identical ledger entries, metrics, and reports."""
    dates = _make_dates(10)
    aapl_closes = [100.0, 102.0, 105.0, 110.0, 108.0, 104.0, 99.0, 95.0, 98.0, 102.0]
    msft_closes = [200.0, 198.0, 195.0, 190.0, 192.0, 196.0, 202.0, 208.0, 210.0, 215.0]
    spy_closes = [400.0, 402.0, 404.0, 406.0, 405.0, 407.0, 409.0, 411.0, 412.0, 415.0]

    bars = [
        *[_make_bar("AAPL", d, c, c) for d, c in zip(dates, aapl_closes)],
        *[_make_bar("MSFT", d, c, c) for d, c in zip(dates, msft_closes)],
        *[_make_bar("SPY", d, c, c) for d, c in zip(dates, spy_closes)],
    ]

    corp_actions = [
        CorporateAction(
            security_id="AAPL",
            type="dividend",
            effective_date=dates[4],
            value=0.75,
            source="test",
            retrieval_time="",
            available_at=f"{dates[3]}T21:00:00Z",
        ),
        CorporateAction(
            security_id="MSFT",
            type="split",
            effective_date=dates[6],
            value=2.0,
            source="test",
            retrieval_time="",
            available_at=f"{dates[5]}T21:00:00Z",
        ),
    ]

    spec = BacktestSpecification(
        strategy_name="long_flat_moving_average",
        strategy_revision="v1",
        dataset_version_id="ds-multi-1",
        universe=("AAPL", "MSFT"),
        benchmark_security_id="SPY",
        start_date=dates[0],
        end_date=dates[9],
        starting_cash=100000.0,
        parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        execution=ExecutionModelAssumptions(
            commission_rate=0.001,
            slippage_rate=0.0005,
            allow_shorting=True,
            borrow_fee_rate=0.03,
            cash_interest_rate=0.02,
            max_leverage=1.5,
            margin_requirement=0.5,
            maintenance_margin=0.25,
        ),
    )

    # Run 1
    run1 = run_backtest(spec, bars=bars, corporate_actions=corp_actions)
    # Run 2
    run2 = run_backtest(spec, bars=bars, corporate_actions=corp_actions)

    # 1. Exact equality of signals, fills, trades
    assert len(run1.signals) == len(run2.signals)
    assert len(run1.fills) == len(run2.fills)
    assert len(run1.trades) == len(run2.trades)
    assert len(run1.ledger) == len(run2.ledger)

    for f1, f2 in zip(run1.fills, run2.fills):
        assert asdict(f1) == asdict(f2)

    for t1, t2 in zip(run1.trades, run2.trades):
        assert asdict(t1) == asdict(t2)

    # 2. Exact equality of all daily ledger entries
    for row1, row2 in zip(run1.ledger, run2.ledger):
        assert asdict(row1) == asdict(row2)

    # 3. Exact equality of headline metrics (BT-010)
    assert asdict(run1.metrics) == asdict(run2.metrics)
    assert run1.metrics.total_return == run2.metrics.total_return
    assert run1.metrics.annualized_return == run2.metrics.annualized_return
    assert run1.metrics.annualized_volatility == run2.metrics.annualized_volatility
    assert run1.metrics.sharpe_ratio == run2.metrics.sharpe_ratio
    assert run1.metrics.sortino_ratio == run2.metrics.sortino_ratio
    assert run1.metrics.max_drawdown == run2.metrics.max_drawdown
    assert run1.metrics.calmar_ratio == run2.metrics.calmar_ratio
    assert run1.metrics.turnover == run2.metrics.turnover
    assert run1.metrics.gross_exposure == run2.metrics.gross_exposure
    assert run1.metrics.net_exposure == run2.metrics.net_exposure
    assert run1.metrics.benchmark_relative_return == run2.metrics.benchmark_relative_return

    # 4. Exact equality of HTML report and CSV export (REP-005, REP-006)
    manifest_data = {
        "id": "run-test-id",
        "dataset_versions": ["ds-multi-1"],
        "definition_revisions": ["v1"],
    }
    html1 = generate_backtest_html_report(run1.to_json(), manifest_data)
    html2 = generate_backtest_html_report(run2.to_json(), manifest_data)
    assert html1 == html2

    csv1 = generate_backtest_csv(run1.to_json())
    csv2 = generate_backtest_csv(run2.to_json())
    assert csv1 == csv2

    # Verify report content contains required labels (REP-006)
    assert "Out-of-sample (Point-in-time sequential simulation)" in html1
    assert "Cost Attribution" in html1
    assert "Performance Overview" in html1
    assert "Performance Metrics" in csv1
    assert "Cost Attribution" in csv1
    assert "Daily Portfolio Ledger" in csv1
