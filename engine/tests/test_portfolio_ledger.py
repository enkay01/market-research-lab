"""Unit tests for PortfolioLedger."""

from __future__ import annotations

import pytest

from market_research_lab.portfolio_ledger import (
    InsufficientCollateralError,
    PortfolioLedger,
    SnapshotMetrics,
)


def test_initialization() -> None:
    ledger = PortfolioLedger(100_000.0)
    assert ledger.initial_cash == 100_000.0
    assert ledger.cash == 100_000.0
    assert ledger.locked_collateral == 0.0
    assert ledger.available_cash == 100_000.0
    assert ledger.cumulative_interest == 0.0
    assert ledger.cumulative_borrow_fees == 0.0
    assert ledger.cumulative_dividends == 0.0
    assert len(ledger.snapshots) == 0


def test_initialization_invalid_cash() -> None:
    with pytest.raises(ValueError, match="Initial cash must be strictly positive"):
        PortfolioLedger(0.0)
    with pytest.raises(ValueError, match="Initial cash must be strictly positive"):
        PortfolioLedger(-500.0)


def test_apply_daily_interest() -> None:
    ledger = PortfolioLedger(100_000.0)
    # Rate: 5% annual, 252 trading days
    interest = ledger.apply_daily_interest(annual_rate=0.05, days=1.0, trading_days_per_year=252.0)
    expected_interest = 100_000.0 * (0.05 / 252.0)
    assert pytest.approx(interest) == expected_interest
    assert pytest.approx(ledger.cash) == 100_000.0 + expected_interest
    assert pytest.approx(ledger.cumulative_interest) == expected_interest

    # Negative cash (debit interest)
    ledger.cash = -50_000.0
    interest_debit = ledger.apply_daily_interest(
        annual_rate=0.08, days=1.0, trading_days_per_year=252.0
    )
    expected_debit = -50_000.0 * (0.08 / 252.0)
    assert pytest.approx(interest_debit) == expected_debit
    assert pytest.approx(ledger.cash) == -50_000.0 + expected_debit


def test_apply_time_elapsed_interest() -> None:
    ledger = PortfolioLedger(100_000.0)
    # 86400 seconds (1 day), 5% rate, 365 days
    interest = ledger.apply_time_elapsed_interest(
        annual_rate=0.05, elapsed_seconds=86400.0, days_per_year=365.0
    )
    expected_interest = 100_000.0 * 0.05 * 1.0 / 365.0
    assert pytest.approx(interest) == expected_interest
    assert pytest.approx(ledger.cash) == 100_000.0 + expected_interest


def test_collateral_locking_and_releasing() -> None:
    ledger = PortfolioLedger(10_000.0)
    ledger.lock_collateral(2_500.0)
    assert ledger.locked_collateral == 2_500.0
    assert ledger.available_cash == 7_500.0

    # Locking more than available cash in strict mode raises InsufficientCollateralError
    with pytest.raises(InsufficientCollateralError):
        ledger.lock_collateral(8_000.0, strict=True)

    # Locking with strict=False allows lock
    ledger.lock_collateral(8_000.0, strict=False)
    assert ledger.locked_collateral == 10_500.0
    assert ledger.available_cash == -500.0

    # Releasing collateral
    ledger.release_collateral(5_000.0)
    assert ledger.locked_collateral == 5_500.0

    # Releasing more collateral than locked clamps to 0
    ledger.release_collateral(10_000.0)
    assert ledger.locked_collateral == 0.0
    assert ledger.available_cash == 10_000.0


def test_cash_flows_and_accounting() -> None:
    ledger = PortfolioLedger(100_000.0)

    # Direct cash flow (trade proceeds)
    entry1 = ledger.record_cash_flow(
        1500.50,
        flow_type="fill_sell",
        description="Trade proceeds",
        timestamp="2026-01-02T10:00:00",
    )
    assert ledger.cash == 101_500.50
    assert entry1.amount == 1500.50
    assert entry1.flow_type == "fill_sell"
    assert entry1.description == "Trade proceeds"
    assert entry1.timestamp == "2026-01-02T10:00:00"
    assert entry1.balance_after == 101_500.50

    # Dividend
    entry2 = ledger.record_dividend(
        250.0, description="AAPL dividend", timestamp="2026-01-03T09:30:00"
    )
    assert ledger.cash == 101_750.50
    assert ledger.cumulative_dividends == 250.0
    assert entry2.flow_type == "dividend"
    assert entry2.description == "AAPL dividend"
    assert entry2.balance_after == 101_750.50

    # Borrow fee
    entry3 = ledger.record_borrow_fee(
        45.0, description="Short borrow fee", timestamp="2026-01-03T16:00:00"
    )
    assert ledger.cash == 101_705.50
    assert ledger.cumulative_borrow_fees == 45.0
    assert entry3.flow_type == "borrow_fee"
    assert entry3.amount == -45.0
    assert entry3.balance_after == 101_705.50

    # Daily interest cash flow
    ledger.apply_daily_interest(
        annual_rate=0.05,
        days=1.0,
        trading_days_per_year=252.0,
        timestamp="2026-01-04T16:00:00",
    )
    assert len(ledger.cash_flows) == 4
    assert ledger.cash_flows[3].flow_type == "cash_interest"
    assert ledger.cash_flows[3].timestamp == "2026-01-04T16:00:00"

    # Time-elapsed interest cash flow
    ledger.apply_time_elapsed_interest(
        annual_rate=0.05,
        elapsed_seconds=86400.0,
        days_per_year=365.0,
        timestamp="2026-01-05T16:00:00",
    )
    assert len(ledger.cash_flows) == 5
    assert ledger.cash_flows[4].flow_type == "cash_interest"


def test_equity_and_option_equity_calculation() -> None:
    ledger = PortfolioLedger(50_000.0)

    # Equity position calculation
    equity = ledger.calculate_equity(total_position_value=25_000.0)
    assert equity == 75_000.0

    # Option liability calculation
    option_equity = ledger.calculate_option_equity(open_liability_value=4_000.0)
    assert option_equity == 46_000.0


def test_snapshot_recording_and_curve_building() -> None:
    ledger = PortfolioLedger(100_000.0)
    s1 = ledger.record_snapshot(
        timestamp="2026-01-02",
        portfolio_value=100_000.0,
        metrics=SnapshotMetrics(gross_exposure=0.5, net_exposure=0.5),
    )
    s2 = ledger.record_snapshot(
        timestamp="2026-01-05",
        portfolio_value=110_000.0,
        metrics=SnapshotMetrics(gross_exposure=0.6, net_exposure=0.6),
    )
    s3 = ledger.record_snapshot(
        timestamp="2026-01-06",
        portfolio_value=99_000.0,
        metrics=SnapshotMetrics(gross_exposure=0.4, net_exposure=0.4),
    )

    assert len(ledger.snapshots) == 3
    assert s1.portfolio_value == 100_000.0
    assert s2.portfolio_value == 110_000.0
    assert s3.portfolio_value == 99_000.0

    # Build equity curve
    equity_curve = ledger.build_equity_curve()
    assert len(equity_curve) == 3
    assert equity_curve[0] == {"timestamp": "2026-01-02", "equity": 100_000.0}
    assert equity_curve[1] == {"timestamp": "2026-01-05", "equity": 110_000.0}
    assert equity_curve[2] == {"timestamp": "2026-01-06", "equity": 99_000.0}

    # Build drawdown curve
    dd_curve = ledger.build_drawdown_curve()
    assert len(dd_curve) == 3
    assert dd_curve[0]["drawdown"] == 0.0
    assert dd_curve[1]["drawdown"] == 0.0
    # Peak is 110,000, value is 99,000 -> (99,000 / 110,000) - 1 = -0.1
    assert pytest.approx(dd_curve[2]["drawdown"]) == -0.1

    # Max drawdown
    assert pytest.approx(ledger.max_drawdown()) == -0.1
