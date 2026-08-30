"""Unit tests for PortfolioLedger."""

from __future__ import annotations

import pytest

from market_research_lab.portfolio_ledger import (
    InsufficientCollateralError,
    PortfolioLedger,
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
    ledger.record_cash_flow(1500.50, description="Trade proceeds")
    assert ledger.cash == 101_500.50

    # Dividend
    ledger.record_dividend(250.0)
    assert ledger.cash == 101_750.50
    assert ledger.cumulative_dividends == 250.0

    # Borrow fee
    ledger.record_borrow_fee(45.0)
    assert ledger.cash == 101_705.50
    assert ledger.cumulative_borrow_fees == 45.0


def test_equity_and_option_equity_calculation() -> None:
    ledger = PortfolioLedger(50_000.0)

    # Equity position calculation
    equity = ledger.calculate_equity(total_position_value=25_000.0)
    assert equity == 75_000.0

    # Option liability calculation
    option_equity = ledger.calculate_option_equity(open_liability_value=4_000.0)
    assert option_equity == 46_000.0


def test_snapshot_recording() -> None:
    ledger = PortfolioLedger(100_000.0)
    snapshot = ledger.record_snapshot(
        timestamp="2026-01-02",
        portfolio_value=105_000.0,
        gross_exposure=0.5,
        net_exposure=0.5,
        cash_interest=10.0,
        dividends=50.0,
    )
    assert snapshot.timestamp == "2026-01-02"
    assert snapshot.portfolio_value == 105_000.0
    assert snapshot.cash == 100_000.0
    assert len(ledger.snapshots) == 1
