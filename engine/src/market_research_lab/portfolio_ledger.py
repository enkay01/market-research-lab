"""Unified portfolio ledger, cash flow accounting, and equity curve generation.

Consolidates cash balance tracking, signed cash interest compounding,
margin collateral locks, immutable cash flow audit trails, and mark-to-market
valuations across both equity and option backtesting engines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class InsufficientCollateralError(ValueError):
    """Raised when collateral cannot be locked due to insufficient available cash."""


@dataclass(frozen=True)
class CashFlowEntry:
    """Immutable audit record of a cash credit, debit, fee, dividend, or trade settlement."""

    timestamp: str
    amount: float
    flow_type: str
    description: str = ""
    balance_after: float = 0.0


@dataclass(frozen=True)
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
    """Tracks cash balances, transaction audit history, margin collateral, and equity curves."""

    def __init__(self, initial_cash: float) -> None:
        if initial_cash <= 0:
            raise ValueError("Initial cash must be strictly positive.")
        self._initial_cash: float = float(initial_cash)
        self._cash: float = float(initial_cash)
        self._locked_collateral: float = 0.0
        self._cumulative_interest: float = 0.0
        self._cumulative_borrow_fees: float = 0.0
        self._cumulative_dividends: float = 0.0
        self._cash_flows: list[CashFlowEntry] = []
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
    def cash_flows(self) -> tuple[CashFlowEntry, ...]:
        """Immutable audit history of all recorded cash flows."""
        return tuple(self._cash_flows)

    @property
    def snapshots(self) -> tuple[LedgerSnapshot, ...]:
        """Immutable history of all recorded mark-to-market snapshots."""
        return tuple(self._snapshots)

    def record_cash_flow(
        self,
        amount: float,
        flow_type: str = "transfer",
        description: str = "",
        timestamp: str = "",
    ) -> CashFlowEntry:
        """Record an immutable cash flow entry and adjust the cash balance."""
        amt = float(amount)
        self._cash += amt
        entry = CashFlowEntry(
            timestamp=timestamp,
            amount=amt,
            flow_type=flow_type,
            description=description,
            balance_after=self._cash,
        )
        self._cash_flows.append(entry)
        return entry

    def record_dividend(
        self,
        amount: float,
        description: str = "",
        timestamp: str = "",
    ) -> CashFlowEntry:
        """Record a dividend cash credit into the ledger audit trail."""
        amt = float(amount)
        self._cumulative_dividends += amt
        return self.record_cash_flow(
            amt,
            flow_type="dividend",
            description=description or "Dividend credit",
            timestamp=timestamp,
        )

    def record_borrow_fee(
        self,
        amount: float,
        description: str = "",
        timestamp: str = "",
    ) -> CashFlowEntry:
        """Record a short position borrow fee debit into the ledger audit trail."""
        fee = abs(float(amount))
        self._cumulative_borrow_fees += fee
        return self.record_cash_flow(
            -fee,
            flow_type="borrow_fee",
            description=description or "Short borrow fee debit",
            timestamp=timestamp,
        )

    def apply_daily_interest(
        self,
        annual_rate: float,
        days: float = 1.0,
        trading_days_per_year: float = 252.0,
        timestamp: str = "",
    ) -> float:
        """Apply signed cash balance interest compounding for discrete daily trading sessions.

        Interest is computed as cash * (annual_rate / trading_days_per_year) * days.
        If cash is negative, interest is debit/borrow interest.
        """
        if not annual_rate or days <= 0:
            return 0.0
        interest = self._cash * (annual_rate / trading_days_per_year) * days
        self._cumulative_interest += interest
        self.record_cash_flow(
            interest,
            flow_type="cash_interest",
            description=f"Daily cash interest ({annual_rate:.4f} annual rate)",
            timestamp=timestamp,
        )
        return interest

    def apply_time_elapsed_interest(
        self,
        annual_rate: float,
        elapsed_seconds: float,
        days_per_year: float = 365.0,
        timestamp: str = "",
    ) -> float:
        """Apply continuous time-elapsed cash interest compounding.

        Interest is computed as cash * annual_rate * (elapsed_seconds / 86400.0) / days_per_year.
        """
        if not annual_rate or elapsed_seconds <= 0:
            return 0.0
        elapsed_days = elapsed_seconds / 86400.0
        interest = self._cash * annual_rate * elapsed_days / days_per_year
        self._cumulative_interest += interest
        self.record_cash_flow(
            interest,
            flow_type="cash_interest",
            description=f"Time-elapsed cash interest ({annual_rate:.4f} annual rate)",
            timestamp=timestamp,
        )
        return interest

    def lock_collateral(self, amount: float, strict: bool = True) -> None:
        """Lock margin collateral for an open spread or short position."""
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

    def build_equity_curve(self) -> list[dict[str, Any]]:
        """Build equity curve dictionary entries from recorded snapshots."""
        return [
            {
                "timestamp": snapshot.timestamp,
                "equity": round(snapshot.portfolio_value, 4),
            }
            for snapshot in self._snapshots
        ]

    def build_drawdown_curve(self) -> list[dict[str, Any]]:
        """Build peak-to-trough drawdown curve entries from recorded snapshots."""
        curve: list[dict[str, Any]] = []
        running_peak = -math.inf
        for snapshot in self._snapshots:
            running_peak = max(running_peak, snapshot.portfolio_value)
            drawdown = (
                (snapshot.portfolio_value / running_peak - 1.0)
                if running_peak > 0
                else 0.0
            )
            curve.append(
                {
                    "timestamp": snapshot.timestamp,
                    "equity": round(snapshot.portfolio_value, 4),
                    "drawdown": round(drawdown, 6),
                }
            )
        return curve

    def max_drawdown(self) -> float:
        """Compute maximum peak-to-trough drawdown fraction across recorded snapshots."""
        peak = 0.0
        worst = 0.0
        for snapshot in self._snapshots:
            peak = max(peak, snapshot.portfolio_value)
            if peak > 0:
                worst = min(worst, snapshot.portfolio_value / peak - 1.0)
        return worst
