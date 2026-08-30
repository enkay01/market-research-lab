"""Unified portfolio ledger and cash interest accounting.

Consolidates cash balance tracking, signed cash interest compounding,
margin collateral locks, and mark-to-market valuations across both
equity and option backtesting engines.
"""

from __future__ import annotations

from dataclasses import dataclass


class InsufficientCollateralError(ValueError):
    """Raised when collateral cannot be locked due to insufficient available cash."""


@dataclass
class LedgerSnapshot:
    """Mark-to-market snapshot of portfolio ledger state at a point in time."""

    timestamp: str
    cash: float
    locked_collateral: float
    available_cash: float
    portfolio_value: float
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    cash_interest: float = 0.0
    borrow_fees: float = 0.0
    dividends: float = 0.0


class PortfolioLedger:
    """Tracks cash balances, interest compounding, margin collateral, and valuations."""

    def __init__(self, initial_cash: float) -> None:
        if initial_cash <= 0:
            raise ValueError("Initial cash must be strictly positive.")
        self._initial_cash: float = float(initial_cash)
        self._cash: float = float(initial_cash)
        self._locked_collateral: float = 0.0
        self._cumulative_interest: float = 0.0
        self._cumulative_borrow_fees: float = 0.0
        self._cumulative_dividends: float = 0.0
        self._snapshots: list[LedgerSnapshot] = []

    @property
    def initial_cash(self) -> float:
        return self._initial_cash

    @property
    def cash(self) -> float:
        return self._cash

    @cash.setter
    def cash(self, value: float) -> None:
        self._cash = float(value)

    @property
    def locked_collateral(self) -> float:
        return self._locked_collateral

    @property
    def available_cash(self) -> float:
        """Unencumbered cash available for trading or collateral locking."""
        return self._cash - self._locked_collateral

    @property
    def cumulative_interest(self) -> float:
        return self._cumulative_interest

    @property
    def cumulative_borrow_fees(self) -> float:
        return self._cumulative_borrow_fees

    @property
    def cumulative_dividends(self) -> float:
        return self._cumulative_dividends

    @property
    def snapshots(self) -> list[LedgerSnapshot]:
        return self._snapshots

    def apply_daily_interest(
        self,
        annual_rate: float,
        days: float = 1.0,
        trading_days_per_year: float = 252.0,
    ) -> float:
        """Apply signed cash balance interest compounding for discrete daily trading sessions.

        Interest is computed as cash * (annual_rate / trading_days_per_year) * days.
        If cash is negative, interest is debit/borrow interest.
        """
        if not annual_rate or days <= 0:
            return 0.0
        interest = self._cash * (annual_rate / trading_days_per_year) * days
        self._cash += interest
        self._cumulative_interest += interest
        return interest

    def apply_time_elapsed_interest(
        self,
        annual_rate: float,
        elapsed_seconds: float,
        days_per_year: float = 365.0,
    ) -> float:
        """Apply continuous time-elapsed cash interest compounding.

        Interest is computed as cash * annual_rate * (elapsed_seconds / 86400.0) / days_per_year.
        """
        if not annual_rate or elapsed_seconds <= 0:
            return 0.0
        elapsed_days = elapsed_seconds / 86400.0
        interest = self._cash * annual_rate * elapsed_days / days_per_year
        self._cash += interest
        self._cumulative_interest += interest
        return interest

    def record_cash_flow(self, amount: float, description: str = "") -> None:
        """Record a raw cash credit or debit (e.g. fills, fees, trade exits)."""
        self._cash += float(amount)

    def record_dividend(self, amount: float) -> None:
        """Record dividend cash flow."""
        self._cash += float(amount)
        self._cumulative_dividends += float(amount)

    def record_borrow_fee(self, amount: float) -> None:
        """Record short borrow fee debit."""
        self._cash -= float(amount)
        self._cumulative_borrow_fees += float(amount)

    def lock_collateral(self, amount: float, strict: bool = True) -> None:
        """Lock margin collateral for open spread or short position."""
        if amount < 0:
            raise ValueError("Collateral amount to lock must be non-negative.")
        if strict and self.available_cash < amount:
            raise InsufficientCollateralError(
                f"Available cash ({self.available_cash:.2f}) is insufficient "
                f"for required collateral ({amount:.2f})."
            )
        self._locked_collateral += float(amount)

    def release_collateral(self, amount: float) -> None:
        """Release previously locked margin collateral."""
        if amount < 0:
            raise ValueError("Collateral amount to release must be non-negative.")
        self._locked_collateral = max(0.0, self._locked_collateral - float(amount))

    def calculate_equity(self, total_position_value: float) -> float:
        """Calculate mark-to-market equity for equity positions.

        Computed as cash + long position values - short position values.
        """
        return self._cash + total_position_value

    def calculate_option_equity(self, open_liability_value: float) -> float:
        """Calculate mark-to-market equity for option spread positions (cash - spread liability)."""
        return self._cash - open_liability_value

    def record_snapshot(
        self,
        timestamp: str,
        portfolio_value: float,
        *,
        gross_exposure: float = 0.0,
        net_exposure: float = 0.0,
        cash_interest: float = 0.0,
        borrow_fees: float = 0.0,
        dividends: float = 0.0,
    ) -> LedgerSnapshot:
        """Record a point-in-time ledger snapshot."""
        snapshot = LedgerSnapshot(
            timestamp=timestamp,
            cash=self._cash,
            locked_collateral=self._locked_collateral,
            available_cash=self.available_cash,
            portfolio_value=portfolio_value,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            cash_interest=cash_interest,
            borrow_fees=borrow_fees,
            dividends=dividends,
        )
        self._snapshots.append(snapshot)
        return snapshot
