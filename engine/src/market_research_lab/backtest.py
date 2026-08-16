"""Deterministic single-Security Backtest engine with a dated portfolio ledger."""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field, replace
from typing import Literal, Sequence

from .json_types import JsonValue
from .market_data import DailyBar
from .strategies import MarketView, StrategyTarget, evaluate_strategy, get_strategy_spec


class BacktestError(Exception):
    """Raised when a Backtest cannot run."""


class BacktestParameterError(ValueError):
    """Raised when a Backtest parameter fails validation."""


EPS = 1e-9
_DATE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


@dataclass(frozen=True)
class ExecutionModelAssumptions:
    """Fill/cost assumptions. Fills always execute at the NEXT bar's open price."""

    schedule: Literal["daily"] = "daily"
    commission_rate: float = 0.0  # fraction of trade notional
    slippage_rate: float = 0.0  # fraction applied to fill price


@dataclass(frozen=True)
class BacktestSpecification:
    """Fully specified inputs for one deterministic Backtest run."""

    strategy_name: str
    strategy_revision: str
    dataset_version_id: str
    security_id: str
    start_date: str  # "YYYY-MM-DD"
    end_date: str  # "YYYY-MM-DD"
    starting_cash: float
    parameters: dict[str, JsonValue] = field(default_factory=dict)
    price_field: Literal["close", "open", "high", "low"] = "close"
    execution: ExecutionModelAssumptions = field(default_factory=ExecutionModelAssumptions)


@dataclass(frozen=True)
class Fill:
    """One executed fill against the effective next-open price."""

    trade_id: str
    security_id: str
    session_date: str  # bar whose open produced the fill
    decision_time: str  # available_at of the bar whose signal triggered the fill
    side: Literal["buy", "sell"]
    quantity: float
    price: float  # effective price AFTER slippage
    notional: float  # quantity * price (positive buy, negative sell)
    commission: float
    slippage_cost: float
    rationale: str


@dataclass(frozen=True)
class LedgerRow:
    """Immutable mark-to-market row for one bar close."""

    session_date: str
    signal_weight: float | None  # target weight decided at this bar's close
    signal_decision_time: str | None
    fill: Fill | None  # fill executed at this bar's open (from prior signal)
    shares: float
    close_price: float
    cash: float
    position_value: float  # shares * close_price
    portfolio_value: float  # cash + position_value


@dataclass(frozen=True)
class Trade:
    """One closed round trip from entry fill to exit fill."""

    trade_id: str
    security_id: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_cost: float  # entry notional + entry commission
    exit_proceeds: float  # exit notional - exit commission
    pnl: float  # exit_proceeds - entry_cost
    return_pct: float  # pnl / entry_cost


@dataclass(frozen=True)
class EquityPoint:
    """One equity or drawdown observation on a bar close."""

    session_date: str
    equity: float
    drawdown: float  # <= 0.0; equity / running_peak - 1


@dataclass(frozen=True)
class BacktestMetrics:
    """Headline risk/return statistics derived from the equity curve."""

    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float  # <= 0.0 (most negative drawdown)
    calmar_ratio: float
    hit_rate: float | None  # None when there are no closed trades
    turnover: float
    gross_exposure: float
    net_exposure: float
    benchmark_relative_return: float | None
    num_trades: int
    num_fills: int


@dataclass(frozen=True)
class BacktestResult:
    """Complete immutable output of one Backtest run."""

    specification: BacktestSpecification
    signals: tuple[StrategyTarget, ...]
    fills: tuple[Fill, ...]
    trades: tuple[Trade, ...]
    ledger: tuple[LedgerRow, ...]
    equity_curve: tuple[EquityPoint, ...]
    drawdown_curve: tuple[EquityPoint, ...]
    metrics: BacktestMetrics
    warnings: tuple[str, ...]
    manifest: dict[str, JsonValue]

    def to_json(self) -> dict[str, JsonValue]:
        from dataclasses import asdict

        return asdict(self)


@dataclass(frozen=True)
class PortfolioState:
    """Full-precision cash and share holdings at one point in time."""

    cash: float
    shares: float


@dataclass(frozen=True)
class PendingTarget:
    """Target weight decided at the previous bar's close, awaiting a fill."""

    weight: float
    decision_time: str
    rationale: str


@dataclass(frozen=True)
class FillOutcome:
    """Result of reconciling one Pending Target against a Portfolio State."""

    fill: Fill | None
    state: PortfolioState
    opened_position: bool  # went flat -> long
    closed_position: bool  # went long -> flat


def _valid_date(value: str) -> bool:
    """Return True when value has the YYYY-MM-DD shape."""
    return _DATE_PATTERN.fullmatch(value) is not None


def _validate_specification(specification: BacktestSpecification) -> None:
    """Validate the Specification's parameters, raising on bad input."""
    if not math.isfinite(specification.starting_cash) or specification.starting_cash <= 0.0:
        raise BacktestParameterError(
            f"starting_cash must be finite and > 0, got {specification.starting_cash}."
        )
    commission = specification.execution.commission_rate
    if not math.isfinite(commission) or commission < 0.0:
        raise BacktestParameterError(
            f"commission_rate must be finite and >= 0, got {commission}."
        )
    slippage = specification.execution.slippage_rate
    if not math.isfinite(slippage) or not 0.0 <= slippage < 1.0:
        raise BacktestParameterError(
            f"slippage_rate must be finite and in [0, 1), got {slippage}."
        )
    if specification.price_field not in {"close", "open", "high", "low"}:
        raise BacktestParameterError(
            f"price_field must be one of 'close', 'open', 'high', 'low', "
            f"got {specification.price_field!r}."
        )
    if not _valid_date(specification.start_date):
        raise BacktestParameterError(
            f"start_date must be YYYY-MM-DD, got {specification.start_date!r}."
        )
    if not _valid_date(specification.end_date):
        raise BacktestParameterError(
            f"end_date must be YYYY-MM-DD, got {specification.end_date!r}."
        )
    if specification.start_date > specification.end_date:
        raise BacktestParameterError(
            f"start_date must be <= end_date, got "
            f"{specification.start_date} > {specification.end_date}."
        )


def _price_value(bar: DailyBar, price_field: str) -> float:
    """Return one OHLC price field from a DailyBar without dynamic lookup."""
    if price_field == "open":
        return bar.open
    if price_field == "high":
        return bar.high
    if price_field == "low":
        return bar.low
    return bar.close


def _market_view(
    security_id: str, sorted_bars: Sequence[DailyBar], decision_time: str, price_field: str
) -> MarketView:
    """Build the point-in-time Market View eligible at one decision time."""
    eligible = [
        bar
        for bar in sorted_bars
        if bar.available_at is not None and bar.available_at <= decision_time
    ]
    if not eligible:
        raise BacktestError(
            f"no bars are point-in-time eligible at decision time '{decision_time}'."
        )
    eligible.sort(key=lambda bar: bar.session_date)
    return MarketView(
        security_id=security_id,
        session_dates=tuple(bar.session_date for bar in eligible),
        prices=tuple(_price_value(bar, price_field) for bar in eligible),
    )


def _execute_fill(
    state: PortfolioState,
    target: PendingTarget,
    bar: DailyBar,
    assumptions: ExecutionModelAssumptions,
) -> FillOutcome:
    """Reconcile one pending target against the current long/flat position.

    Long/flat slice: a target weight <= 0 demands a flat position; a positive
    weight either opens a fully invested long (cash / effective buy price) when
    flat or holds the current shares when already long. A fill only occurs when
    the resulting share delta exceeds EPS. Cash and shares stay at full float
    precision; only the recorded Fill fields are rounded.
    """
    open_price = bar.open
    if target.weight <= 0.0:
        target_shares = 0.0
    elif state.shares <= EPS:
        denominator = open_price * (1.0 + assumptions.slippage_rate)
        denominator *= 1.0 + assumptions.commission_rate
        target_shares = state.cash / denominator if denominator > 0.0 else 0.0
    else:
        target_shares = state.shares

    delta = target_shares - state.shares
    if abs(delta) < EPS:
        return FillOutcome(fill=None, state=state, opened_position=False, closed_position=False)

    was_flat = state.shares <= EPS
    side: Literal["buy", "sell"] = "buy" if delta > 0.0 else "sell"
    slippage = assumptions.slippage_rate
    effective_price = (
        open_price * (1.0 + slippage) if delta > 0.0 else open_price * (1.0 - slippage)
    )
    notional = delta * effective_price
    commission = abs(notional) * assumptions.commission_rate
    slippage_cost = abs(delta) * open_price * slippage
    new_state = PortfolioState(
        cash=state.cash - notional - commission,
        shares=target_shares,
    )
    fill = Fill(
        trade_id="",
        security_id=bar.security_id,
        session_date=bar.session_date,
        decision_time=target.decision_time,
        side=side,
        quantity=round(abs(delta), 6),
        price=round(effective_price, 4),
        notional=round(notional, 4),
        commission=round(commission, 4),
        slippage_cost=round(slippage_cost, 4),
        rationale=target.rationale,
    )
    return FillOutcome(
        fill=fill,
        state=new_state,
        opened_position=was_flat and target_shares > EPS,
        closed_position=not was_flat and target_shares <= EPS,
    )


def _build_trade(open_trade: dict[str, str | float], fill: Fill) -> Trade:
    """Close an open trade with the shared trade id and the closing fill."""
    entry_cost = float(open_trade["entry_cost"])
    exit_proceeds = -fill.notional - fill.commission
    pnl = exit_proceeds - entry_cost
    return Trade(
        trade_id=str(open_trade["trade_id"]),
        security_id=fill.security_id,
        entry_date=str(open_trade["entry_date"]),
        exit_date=fill.session_date,
        entry_price=float(open_trade["entry_price"]),
        exit_price=fill.price,
        quantity=float(open_trade["quantity"]),
        entry_cost=entry_cost,
        exit_proceeds=exit_proceeds,
        pnl=pnl,
        return_pct=pnl / entry_cost,
    )


def _compute_metrics(
    ledger: Sequence[LedgerRow],
    starting_cash: float,
    fills: Sequence[Fill],
    trades: Sequence[Trade],
) -> BacktestMetrics:
    """Derive headline risk/return metrics from the mark-to-market ledger."""
    equities = [row.portfolio_value for row in ledger]
    total_return = equities[-1] / starting_cash - 1.0

    returns = [
        equities[i] / equities[i - 1] - 1.0
        for i in range(1, len(equities))
        if equities[i - 1] > 0.0
    ]
    mean_return = statistics.mean(returns) if returns else 0.0
    volatility = statistics.stdev(returns) if len(returns) >= 2 else 0.0

    if len(equities) >= 2:
        base = 1.0 + total_return
        annualized_return = base ** (252.0 / len(equities)) - 1.0 if base > 0.0 else 0.0
    else:
        annualized_return = total_return

    annualized_volatility = volatility * math.sqrt(252.0)
    sharpe_ratio = (mean_return / volatility) * math.sqrt(252.0) if volatility > 0.0 else 0.0
    downside = (
        math.sqrt(statistics.mean(min(x, 0.0) ** 2 for x in returns)) if returns else 0.0
    )
    sortino_ratio = (mean_return / downside) * math.sqrt(252.0) if downside > 0.0 else 0.0

    running_peak = -math.inf
    drawdowns: list[float] = []
    for equity in equities:
        running_peak = max(running_peak, equity)
        drawdowns.append(equity / running_peak - 1.0)
    max_drawdown = min(drawdowns) if drawdowns else 0.0

    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0.0 else 0.0
    hit_rate = sum(1.0 for trade in trades if trade.pnl > 0.0) / len(trades) if trades else None

    mean_equity = statistics.mean(equities) if equities else 0.0
    turnover = (
        sum(abs(fill.notional) for fill in fills) / mean_equity if mean_equity > 0.0 else 0.0
    )

    last_row = ledger[-1]
    exposure = (
        last_row.position_value / last_row.portfolio_value
        if last_row.portfolio_value != 0.0
        else 0.0
    )

    return BacktestMetrics(
        total_return=round(total_return, 6),
        annualized_return=round(annualized_return, 6),
        annualized_volatility=round(annualized_volatility, 6),
        sharpe_ratio=round(sharpe_ratio, 6),
        sortino_ratio=round(sortino_ratio, 6),
        max_drawdown=round(max_drawdown, 6),
        calmar_ratio=round(calmar_ratio, 6),
        hit_rate=round(hit_rate, 6) if hit_rate is not None else None,
        turnover=round(turnover, 6),
        gross_exposure=round(exposure, 6),
        net_exposure=round(exposure, 6),
        benchmark_relative_return=None,
        num_trades=len(trades),
        num_fills=len(fills),
    )


def run_backtest(
    specification: BacktestSpecification, *, bars: Sequence[DailyBar]
) -> BacktestResult:
    """Run a deterministic next-open Backtest over one Security's daily bars."""
    _validate_specification(specification)
    get_strategy_spec(specification.strategy_name)
    for bar in bars:
        if not bar.available_at or not bar.available_at.strip():
            raise BacktestError(
                "Backtest requires point-in-time availability ('available_at') "
                "on every DailyBar."
            )

    bars_sorted = sorted(bars, key=lambda bar: (bar.available_at, bar.session_date))
    window = [
        bar
        for bar in bars_sorted
        if specification.start_date <= bar.session_date <= specification.end_date
    ]
    if not window:
        raise BacktestError("no bars within [start_date, end_date]")

    cash = specification.starting_cash
    shares = 0.0
    pending: PendingTarget | None = None
    open_trade: dict[str, str | float] | None = None
    trade_counter = 0
    signals: list[StrategyTarget] = []
    fills: list[Fill] = []
    trades: list[Trade] = []
    ledger: list[LedgerRow] = []
    warnings: list[str] = []

    for bar in window:
        fill = None
        if pending is not None:
            outcome = _execute_fill(
                PortfolioState(cash, shares), pending, bar, specification.execution
            )
            cash, shares = outcome.state.cash, outcome.state.shares
            if outcome.fill is not None:
                fill = outcome.fill
                if outcome.opened_position:
                    trade_counter += 1
                    trade_id = f"trade-{trade_counter}"
                    fill = replace(fill, trade_id=trade_id)
                    open_trade = {
                        "trade_id": trade_id,
                        "entry_date": bar.session_date,
                        "entry_price": fill.price,
                        "quantity": fill.quantity,
                        "entry_cost": fill.notional + fill.commission,
                    }
                elif outcome.closed_position and open_trade is not None:
                    fill = replace(fill, trade_id=str(open_trade["trade_id"]))
                fills.append(fill)
                if outcome.closed_position and open_trade is not None:
                    trades.append(_build_trade(open_trade, fill))
                    open_trade = None
        pending = None

        view = _market_view(
            specification.security_id,
            bars_sorted,
            bar.available_at,
            specification.price_field,
        )
        evaluation = evaluate_strategy(
            specification.strategy_name,
            view,
            specification.parameters,
            decision_time=bar.available_at,
        )
        if len(evaluation.targets) != 1:
            raise BacktestError("single-Security backtest requires exactly one target")
        target = evaluation.targets[0]
        signals.append(target)
        pending = PendingTarget(target.weight, bar.available_at, target.rationale)

        close_price = _price_value(bar, specification.price_field)
        position_value = shares * close_price
        portfolio_value = cash + position_value
        ledger.append(
            LedgerRow(
                session_date=bar.session_date,
                signal_weight=target.weight,
                signal_decision_time=bar.available_at,
                fill=fill,
                shares=round(shares, 6),
                close_price=close_price,
                cash=round(cash, 4),
                position_value=round(position_value, 4),
                portfolio_value=round(portfolio_value, 4),
            )
        )

    if not fills:
        warnings.append("No fills occurred during the backtest window.")

    if pending is not None:
        position_weight = 1.0 if shares > EPS else 0.0
        if abs(pending.weight - position_weight) > EPS:
            warnings.append(
                f"Final signal on {window[-1].session_date} "
                f"(weight {pending.weight}) has no subsequent bar to fill."
            )

    running_peak = -math.inf
    curve: list[EquityPoint] = []
    for row in ledger:
        running_peak = max(running_peak, row.portfolio_value)
        drawdown = row.portfolio_value / running_peak - 1.0
        curve.append(
            EquityPoint(
                session_date=row.session_date,
                equity=round(row.portfolio_value, 4),
                drawdown=round(drawdown, 6),
            )
        )

    metrics = _compute_metrics(ledger, specification.starting_cash, fills, trades)

    manifest: dict[str, JsonValue] = {
        "kind": "backtest",
        "strategy_name": specification.strategy_name,
        "strategy_revision": specification.strategy_revision,
        "dataset_version_id": specification.dataset_version_id,
        "security_id": specification.security_id,
        "start_date": specification.start_date,
        "end_date": specification.end_date,
        "starting_cash": specification.starting_cash,
        "parameters": dict(specification.parameters),
        "price_field": specification.price_field,
        "execution": {
            "schedule": specification.execution.schedule,
            "fill_price": "next_open",
            "commission_rate": specification.execution.commission_rate,
            "slippage_rate": specification.execution.slippage_rate,
        },
        "signal_count": len(signals),
        "fill_count": len(fills),
        "trade_count": len(trades),
    }

    return BacktestResult(
        specification=specification,
        signals=tuple(signals),
        fills=tuple(fills),
        trades=tuple(trades),
        ledger=tuple(ledger),
        equity_curve=tuple(curve),
        drawdown_curve=tuple(curve),
        metrics=metrics,
        warnings=tuple(warnings),
        manifest=manifest,
    )
