"""Deterministic multi-Security Backtest engine supporting long/short positions and borrowing."""

from __future__ import annotations

import contextlib
import math
import re
import statistics
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal, Sequence

from .exchange_calendar import get_trading_days
from .json_types import JsonValue
from .market_data import CorporateAction, DailyBar
from .portfolio_ledger import PortfolioLedger, SnapshotMetrics
from .strategies import (
    CROSS_SECTIONAL_STRATEGIES,
    MarketView,
    RankingRecord,
    StrategyTarget,
    evaluate_strategy,
    get_strategy_spec,
)


class BacktestError(Exception):
    """Raised when a Backtest cannot run."""


class BacktestParameterError(ValueError):
    """Raised when a Backtest parameter fails validation."""


EPS = 1e-9
TRADING_DAYS_PER_YEAR = 252.0
_DATE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


@dataclass(frozen=True)
class ExecutionModelAssumptions:
    """Fill/cost assumptions. Fills always execute at the NEXT bar's open price."""

    schedule: Literal["daily"] = "daily"
    commission_rate: float = 0.0  # fraction of trade notional
    slippage_rate: float = 0.0  # fraction applied to fill price
    allow_shorting: bool = True
    borrow_fee_rate: float = 0.0  # annualized borrow fee rate on short market value
    cash_interest_rate: float = 0.0  # signed annualized rate on cash between eligible bars
    unavailable_borrow: tuple[str, ...] = ()
    hard_to_borrow_rates: dict[str, float] = field(default_factory=dict)
    # Maximum allowed gross portfolio exposure (e.g. 1.0 for 100%, 2.0 for 200%)
    max_leverage: float = 1.0
    # Initial margin requirement fraction (e.g. 1.0 for cash, 0.5 for 2:1 margin)
    margin_requirement: float = 1.0
    maintenance_margin: float = 0.25  # maintenance margin requirement fraction
    leverage_mode: Literal["reject", "constrain"] = "reject"


@dataclass(frozen=True)
class BacktestSpecification:
    """Fully specified inputs for one deterministic Backtest run."""

    strategy_name: str
    strategy_revision: str
    dataset_version_id: str
    security_id: str = ""
    start_date: str = ""  # "YYYY-MM-DD"
    end_date: str = ""  # "YYYY-MM-DD"
    starting_cash: float = 100000.0
    parameters: dict[str, JsonValue] = field(default_factory=dict)
    price_field: Literal["close", "open", "high", "low"] = "close"
    execution: ExecutionModelAssumptions = field(default_factory=ExecutionModelAssumptions)
    universe: tuple[str, ...] = ()
    benchmark_security_id: str | None = None
    calendar: Literal["US", "none"] = "none"


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
class PositionSnapshot:
    """Mark-to-market snapshot for one Security's position at bar close."""

    shares: float
    close_price: float
    position_value: float
    weight: float  # position_value / portfolio_value


@dataclass(frozen=True)
class ConstraintRejection:
    """Record of an execution or portfolio constraint rejection."""

    session_date: str
    security_id: str
    rule: str
    reason: str
    requested_weight: float | None = None


@dataclass(frozen=True)
class LedgerRow:
    """Immutable mark-to-market row for one bar close."""

    session_date: str
    signal_weight: float | None  # target weight for primary security (compat)
    signal_decision_time: str | None
    fill: Fill | None  # first fill on this date (compat)
    shares: float  # primary security shares (compat)
    close_price: float  # primary security close price (compat)
    cash: float
    position_value: float  # total position value across all securities
    portfolio_value: float  # cash + total position value
    positions: dict[str, PositionSnapshot] = field(default_factory=dict)
    signal_weights: dict[str, float] = field(default_factory=dict)
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    borrow_fees: float = 0.0
    cash_interest: float = 0.0  # signed interest credited to or charged against cash
    dividends: float = 0.0  # net cash dividends credited (positive) or debited (negative)
    # security_id -> split factor applied today
    splits: dict[str, float] = field(default_factory=dict)
    delistings: tuple[str, ...] = ()  # securities delisted today


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
    entry_cost: float  # entry notional + entry commission for long, entry proceeds for short
    exit_proceeds: float  # exit proceeds for long, exit cost for short
    pnl: float  # net realized profit and loss
    return_pct: float  # pnl / cost basis


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
    benchmark_equity_curve: tuple[EquityPoint, ...] = ()
    rejections: tuple[ConstraintRejection, ...] = ()
    ranking_records: tuple[RankingRecord, ...] = ()

    def to_json(self) -> dict[str, JsonValue]:
        from dataclasses import asdict

        payload = asdict(self)
        payload["rankings"] = payload.pop("ranking_records")
        return payload


@dataclass(frozen=True)
class PortfolioState:
    """Full-precision cash and multi-security share holdings at one point in time."""

    cash: float
    positions: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PendingTarget:
    """Target weight decided at the previous bar's close, awaiting a fill."""

    security_id: str
    weight: float
    decision_time: str
    rationale: str


@dataclass(frozen=True)
class OpenTrade:
    """Entry half of a round trip, held until the position is closed."""

    trade_id: str
    security_id: str
    entry_date: str
    entry_price: float
    quantity: float
    entry_cost: float
    side: Literal["long", "short"] = "long"


def _valid_date(value: str) -> bool:
    """Return True when value has the YYYY-MM-DD shape."""
    return _DATE_PATTERN.fullmatch(value) is not None


def _parse_available_at(value: str) -> datetime:
    """Parse one DailyBar eligibility timestamp as an aware UTC datetime."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BacktestError(f"DailyBar available_at is not an ISO timestamp: {value!r}.") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _resolve_universe(specification: BacktestSpecification) -> tuple[str, ...]:
    """Resolve the effective universe tuple from universe or security_id."""
    if specification.universe:
        return specification.universe
    if specification.security_id:
        return (specification.security_id,)
    return ()


def _validate_specification(specification: BacktestSpecification) -> tuple[str, ...]:
    """Validate the Specification's parameters, returning the normalized universe."""
    universe = _resolve_universe(specification)
    if not universe:
        raise BacktestParameterError("universe or security_id must specify at least one security.")

    if not math.isfinite(specification.starting_cash) or specification.starting_cash <= 0.0:
        raise BacktestParameterError(
            f"starting_cash must be finite and > 0, got {specification.starting_cash}."
        )
    commission = specification.execution.commission_rate
    if not math.isfinite(commission) or commission < 0.0:
        raise BacktestParameterError(f"commission_rate must be finite and >= 0, got {commission}.")
    slippage = specification.execution.slippage_rate
    if not math.isfinite(slippage) or not 0.0 <= slippage < 1.0:
        raise BacktestParameterError(f"slippage_rate must be finite and in [0, 1), got {slippage}.")
    borrow_fee = specification.execution.borrow_fee_rate
    if not math.isfinite(borrow_fee) or borrow_fee < 0.0:
        raise BacktestParameterError(
            f"borrow_fee_rate must be finite and >= 0, got {borrow_fee}."
        )
    cash_interest = specification.execution.cash_interest_rate
    if not math.isfinite(cash_interest):
        raise BacktestParameterError(
            f"cash_interest_rate must be finite, got {cash_interest}."
        )
    max_leverage = specification.execution.max_leverage
    if not math.isfinite(max_leverage) or max_leverage <= 0.0:
        raise BacktestParameterError(
            f"max_leverage must be finite and > 0, got {max_leverage}."
        )
    margin_req = specification.execution.margin_requirement
    if not math.isfinite(margin_req) or margin_req <= 0.0:
        raise BacktestParameterError(
            f"margin_requirement must be finite and > 0, got {margin_req}."
        )
    maint_margin = specification.execution.maintenance_margin
    if not math.isfinite(maint_margin) or maint_margin < 0.0:
        raise BacktestParameterError(
            f"maintenance_margin must be finite and >= 0, got {maint_margin}."
        )
    if specification.execution.leverage_mode not in {"reject", "constrain"}:
        raise BacktestParameterError(
            "leverage_mode must be 'reject' or 'constrain', got "
            f"{specification.execution.leverage_mode!r}."
        )
    if specification.price_field not in {"close", "open", "high", "low"}:
        raise BacktestParameterError(
            f"price_field must be one of 'close', 'open', 'high', 'low', "
            f"got {specification.price_field!r}."
        )
    if specification.calendar not in {"US", "none"}:
        raise BacktestParameterError(
            f"calendar must be 'US' or 'none', got {specification.calendar!r}."
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
    return universe


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
        if bar.security_id == security_id
        and bar.available_at is not None
        and bar.available_at <= decision_time
    ]
    if not eligible:
        raise BacktestError(
            f"no bars are point-in-time eligible for '{security_id}' at "
            f"decision time '{decision_time}'."
        )
    eligible.sort(key=lambda bar: bar.session_date)
    return MarketView(
        security_id=security_id,
        session_dates=tuple(bar.session_date for bar in eligible),
        prices=tuple(_price_value(bar, price_field) for bar in eligible),
    )


def _build_trade(open_trade: OpenTrade, fill: Fill) -> Trade:
    """Close an open trade with the shared trade id and the closing fill."""
    if open_trade.side == "short":
        exit_cost = fill.notional + fill.commission
        pnl = open_trade.entry_cost - exit_cost
        cost_basis = open_trade.quantity * open_trade.entry_price
        return Trade(
            trade_id=open_trade.trade_id,
            security_id=fill.security_id,
            entry_date=open_trade.entry_date,
            exit_date=fill.session_date,
            entry_price=open_trade.entry_price,
            exit_price=fill.price,
            quantity=open_trade.quantity,
            entry_cost=round(open_trade.entry_cost, 4),
            exit_proceeds=round(exit_cost, 4),
            pnl=round(pnl, 4),
            return_pct=round(pnl / cost_basis if cost_basis > 0 else 0.0, 6),
        )
    exit_proceeds = -fill.notional - fill.commission
    pnl = exit_proceeds - open_trade.entry_cost
    cost_basis = open_trade.entry_cost
    return Trade(
        trade_id=open_trade.trade_id,
        security_id=fill.security_id,
        entry_date=open_trade.entry_date,
        exit_date=fill.session_date,
        entry_price=open_trade.entry_price,
        exit_price=fill.price,
        quantity=open_trade.quantity,
        entry_cost=round(open_trade.entry_cost, 4),
        exit_proceeds=round(exit_proceeds, 4),
        pnl=round(pnl, 4),
        return_pct=round(pnl / cost_basis if cost_basis > 0 else 0.0, 6),
    )


@dataclass(frozen=True)
class BenchmarkCalculationResult:
    """Benchmark equity curve and buy-and-hold total return."""

    curve: tuple[EquityPoint, ...]
    total_return: float | None


@dataclass(frozen=True)
class MetricsCalculationInput:
    """Input payload for risk/return metric derivation."""

    ledger: Sequence[LedgerRow]
    starting_cash: float
    fills: Sequence[Fill]
    trades: Sequence[Trade]
    benchmark_relative_return: float | None = None


def _compute_metrics(calc_input: MetricsCalculationInput) -> BacktestMetrics:
    """Derive headline risk/return metrics from the mark-to-market ledger."""
    ledger = calc_input.ledger
    starting_cash = calc_input.starting_cash
    fills = calc_input.fills
    trades = calc_input.trades
    benchmark_relative_return = calc_input.benchmark_relative_return

    equities = [row.portfolio_value for row in ledger]
    total_return = (equities[-1] / starting_cash - 1.0) if (equities and starting_cash > 0) else 0.0

    returns = [
        equities[i] / equities[i - 1] - 1.0
        for i in range(1, len(equities))
        if equities[i - 1] > 0.0
    ]
    mean_return = statistics.mean(returns) if returns else 0.0
    volatility = statistics.stdev(returns) if len(returns) >= 2 else 0.0

    if returns:
        base = 1.0 + total_return
        annualized_return = base ** (252.0 / len(returns)) - 1.0 if base > 0.0 else 0.0
    else:
        annualized_return = total_return

    annualized_volatility = volatility * math.sqrt(252.0)
    sharpe_ratio = (mean_return / volatility) * math.sqrt(252.0) if volatility > 0.0 else 0.0
    downside = math.sqrt(statistics.mean(min(x, 0.0) ** 2 for x in returns)) if returns else 0.0
    sortino_ratio = (mean_return / downside) * math.sqrt(252.0) if downside > 0.0 else 0.0

    running_peak = -math.inf
    drawdowns: list[float] = []
    for equity in equities:
        running_peak = max(running_peak, equity)
        drawdowns.append(equity / running_peak - 1.0 if running_peak > 0 else 0.0)
    max_drawdown = min(drawdowns) if drawdowns else 0.0

    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0.0 else 0.0
    hit_rate = sum(1.0 for trade in trades if trade.pnl > 0.0) / len(trades) if trades else None

    mean_equity = statistics.mean(equities) if equities else 0.0
    turnover = sum(abs(fill.notional) for fill in fills) / mean_equity if mean_equity > 0.0 else 0.0

    gross_exp = (
        sum(row.gross_exposure for row in ledger) / len(ledger) if ledger else 0.0
    )
    net_exp = (
        sum(row.net_exposure for row in ledger) / len(ledger) if ledger else 0.0
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
        gross_exposure=round(gross_exp, 6),
        net_exposure=round(net_exp, 6),
        benchmark_relative_return=round(benchmark_relative_return, 6)
        if benchmark_relative_return is not None
        else None,
        num_trades=len(trades),
        num_fills=len(fills),
    )


def _compute_benchmark_curve(
    benchmark_symbol: str,
    bars_by_symbol: dict[str, dict[str, DailyBar]],
    session_dates: Sequence[str],
    starting_cash: float,
) -> BenchmarkCalculationResult:
    """Compute the point-in-time benchmark buy-and-hold equity curve and return."""
    bench_bars = bars_by_symbol.get(benchmark_symbol)
    if not bench_bars:
        return BenchmarkCalculationResult(curve=(), total_return=None)

    available_dates = [d for d in session_dates if d in bench_bars]
    if not available_dates:
        return BenchmarkCalculationResult(curve=(), total_return=None)

    first_close = bench_bars[available_dates[0]].close
    if first_close <= 0:
        return BenchmarkCalculationResult(curve=(), total_return=None)

    curve: list[EquityPoint] = []
    running_peak = -math.inf
    last_known_close = first_close

    for date_str in session_dates:
        if date_str in bench_bars:
            last_known_close = bench_bars[date_str].close
        equity = starting_cash * (last_known_close / first_close)
        running_peak = max(running_peak, equity)
        drawdown = equity / running_peak - 1.0 if running_peak > 0 else 0.0
        curve.append(
            EquityPoint(
                session_date=date_str,
                equity=round(equity, 4),
                drawdown=round(drawdown, 6),
            )
        )

    bench_total_return = (curve[-1].equity / starting_cash) - 1.0 if curve else None
    return BenchmarkCalculationResult(curve=tuple(curve), total_return=bench_total_return)


def run_backtest(
    specification: BacktestSpecification,
    *,
    bars: Sequence[DailyBar],
    corporate_actions: Sequence[CorporateAction] = (),
) -> BacktestResult:
    """Run a deterministic next-open Backtest over a multi-Security universe."""
    universe = _validate_specification(specification)
    get_strategy_spec(specification.strategy_name)

    # Validate corporate actions
    for action in corporate_actions:
        if action.type not in {"split", "stock_split", "dividend", "delisting", "delist"}:
            raise BacktestError(f"Unsupported corporate action type: {action.type!r}.")
        if not math.isfinite(action.value):
            raise BacktestError(f"Corporate action value must be finite, got {action.value!r}.")
        if action.type in {"split", "stock_split"} and action.value <= 0.0:
            raise BacktestError(f"Split factor must be > 0, got {action.value!r}.")
        if not _valid_date(action.effective_date):
            raise BacktestError(
                "Corporate action effective_date must be YYYY-MM-DD, got "
                f"{action.effective_date!r}."
            )

    available_at_by_date: dict[str, datetime] = {}
    for bar in bars:
        if not bar.available_at or not bar.available_at.strip():
            raise BacktestError(
                "Backtest requires point-in-time availability ('available_at') on every DailyBar."
            )
        available_at = _parse_available_at(bar.available_at)
        if bar.security_id not in universe:
            continue
        prior_available_at = available_at_by_date.get(bar.session_date)
        if prior_available_at is None or available_at > prior_available_at:
            available_at_by_date[bar.session_date] = available_at

    # Index bars by symbol and session_date
    bars_by_symbol: dict[str, dict[str, DailyBar]] = {}
    for bar in bars:
        bars_by_symbol.setdefault(bar.security_id, {})[bar.session_date] = bar

    # Index corporate actions by effective_date
    corp_actions_by_date: dict[str, list[CorporateAction]] = {}
    for action in corporate_actions:
        if action.security_id in universe:
            corp_actions_by_date.setdefault(action.effective_date, []).append(action)

    # Determine unique sorted simulation dates in the window [start_date, end_date]
    if specification.calendar == "US":
        trading_days = get_trading_days(
            specification.start_date, specification.end_date, exchange="US"
        )
        if not trading_days:
            raise BacktestError("no bars within [start_date, end_date]")
        sorted_window_dates = trading_days
    else:
        window_dates_set: set[str] = set()
        for sym in universe:
            if sym in bars_by_symbol:
                for session_date in bars_by_symbol[sym]:
                    if specification.start_date <= session_date <= specification.end_date:
                        window_dates_set.add(session_date)

        if not window_dates_set:
            raise BacktestError("no bars within [start_date, end_date]")
        sorted_window_dates = sorted(window_dates_set)

    sorted_all_bars = sorted(bars, key=lambda b: (b.available_at, b.session_date))

    ledger_account = PortfolioLedger(specification.starting_cash)
    cash = ledger_account.cash
    positions: dict[str, float] = {sym: 0.0 for sym in universe}
    holding_target_weights: dict[str, float] = {sym: 0.0 for sym in universe}
    pending_targets: dict[str, PendingTarget] = {}
    open_trades: dict[str, OpenTrade] = {}
    last_known_close_prices: dict[str, float] = {sym: 0.0 for sym in universe}
    delisted_securities: set[str] = set()
    trade_counter = 0

    signals: list[StrategyTarget] = []
    ranking_records: list[RankingRecord] = []
    fills: list[Fill] = []
    trades: list[Trade] = []
    ledger: list[LedgerRow] = []
    warnings: list[str] = []
    rejections: list[ConstraintRejection] = []
    previous_eligible_at: datetime | None = None
    cash_interest_periods = 0
    total_splits_count = 0
    total_dividends_credited = 0.0
    delistings_applied: list[str] = []

    primary_symbol = universe[0]

    for date_str in sorted_window_dates:
        fills_today: list[Fill] = []
        splits_today: dict[str, float] = {}
        dividends_today = 0.0
        delistings_today: list[str] = []
        cash_interest_today = 0.0

        current_eligible_at = available_at_by_date.get(date_str)

        # -------------------------------------------------------------
        # STEP 0: Apply corporate actions effective on date_str
        # -------------------------------------------------------------
        day_actions = corp_actions_by_date.get(date_str, [])
        for action in day_actions:
            # Point-in-time check: corporate action must be available at or before today's
            # decision time
            if action.available_at and current_eligible_at:
                action_available_at: datetime | None = None
                with contextlib.suppress(BacktestError):
                    action_available_at = _parse_available_at(action.available_at)

                if action_available_at is not None and action_available_at > current_eligible_at:
                    # Skip future corporate action (DATA-008 leakage prevention)
                    continue

            sym = action.security_id
            if sym in delisted_securities:
                continue

            if action.type in {"split", "stock_split"}:
                factor = action.value
                curr_s = positions.get(sym, 0.0)
                positions[sym] = curr_s * factor
                if sym in open_trades:
                    open_tr = open_trades[sym]
                    new_qty = open_tr.quantity * factor
                    new_entry_p = (
                        open_tr.entry_price / factor if factor > 0 else open_tr.entry_price
                    )
                    open_trades[sym] = replace(open_tr, quantity=new_qty, entry_price=new_entry_p)
                splits_today[sym] = factor
                total_splits_count += 1

            elif action.type == "dividend":
                div_val = action.value
                curr_s = positions.get(sym, 0.0)
                div_cash = curr_s * div_val
                ledger_account.record_dividend(
                    div_cash, description=f"Dividend for {sym}", timestamp=date_str
                )
                cash = ledger_account.cash
                dividends_today += div_cash
                total_dividends_credited += div_cash

            elif action.type in {"delisting", "delist"}:
                liq_price = max(0.0, action.value)
                curr_s = positions.get(sym, 0.0)
                if abs(curr_s) > EPS:
                    open_tr = open_trades.get(sym)
                    if curr_s > EPS:
                        proceeds = curr_s * liq_price
                        ledger_account.record_cash_flow(
                            proceeds,
                            flow_type="delisting_liquidation",
                            description=f"Delisting liquidation proceeds for {sym}",
                            timestamp=date_str,
                        )
                        cash = ledger_account.cash
                        if open_tr is not None:
                            trade_pnl = proceeds - open_tr.entry_cost
                            trade_cost_basis = open_tr.entry_cost
                            trades.append(
                                Trade(
                                    trade_id=open_tr.trade_id,
                                    security_id=sym,
                                    entry_date=open_tr.entry_date,
                                    exit_date=date_str,
                                    entry_price=open_tr.entry_price,
                                    exit_price=liq_price,
                                    quantity=open_tr.quantity,
                                    entry_cost=round(open_tr.entry_cost, 4),
                                    exit_proceeds=round(proceeds, 4),
                                    pnl=round(trade_pnl, 4),
                                    return_pct=round(
                                        trade_pnl / trade_cost_basis
                                        if trade_cost_basis > 0
                                        else 0.0,
                                        6,
                                    ),
                                )
                            )
                            del open_trades[sym]
                    else:
                        cover_cost = abs(curr_s) * liq_price
                        ledger_account.record_cash_flow(
                            -cover_cost,
                            flow_type="delisting_cover",
                            description=f"Delisting short cover cost for {sym}",
                            timestamp=date_str,
                        )
                        cash = ledger_account.cash
                        if open_tr is not None:
                            trade_pnl = open_tr.entry_cost - cover_cost
                            trade_cost_basis = open_tr.quantity * open_tr.entry_price
                            trades.append(
                                Trade(
                                    trade_id=open_tr.trade_id,
                                    security_id=sym,
                                    entry_date=open_tr.entry_date,
                                    exit_date=date_str,
                                    entry_price=open_tr.entry_price,
                                    exit_price=liq_price,
                                    quantity=open_tr.quantity,
                                    entry_cost=round(open_tr.entry_cost, 4),
                                    exit_proceeds=round(cover_cost, 4),
                                    pnl=round(trade_pnl, 4),
                                    return_pct=round(
                                        trade_pnl / trade_cost_basis
                                        if trade_cost_basis > 0
                                        else 0.0,
                                        6,
                                    ),
                                )
                            )
                            del open_trades[sym]
                    positions[sym] = 0.0
                    holding_target_weights[sym] = 0.0

                delisted_securities.add(sym)
                delistings_today.append(sym)
                delistings_applied.append(sym)
                if sym in pending_targets:
                    del pending_targets[sym]
                    rejections.append(
                        ConstraintRejection(
                            session_date=date_str,
                            security_id=sym,
                            rule="delisted_security",
                            reason=f"Security '{sym}' was delisted on {action.effective_date}.",
                        )
                    )

        # -------------------------------------------------------------
        # STEP 1: Cash Interest
        # -------------------------------------------------------------
        if (
            previous_eligible_at is not None
            and current_eligible_at is not None
            and current_eligible_at > previous_eligible_at
        ):
            cash_interest_periods += 1
            cash_interest_today = ledger_account.apply_daily_interest(
                specification.execution.cash_interest_rate,
                days=1.0,
                trading_days_per_year=TRADING_DAYS_PER_YEAR,
                timestamp=date_str,
            )
            cash = ledger_account.cash
        if current_eligible_at is not None:
            previous_eligible_at = max(
                previous_eligible_at or current_eligible_at,
                current_eligible_at,
            )

        # -------------------------------------------------------------
        # STEP 2: Reconcile pending targets at today's open price
        # -------------------------------------------------------------
        if pending_targets:
            # Calculate open portfolio value using today's open prices
            open_prices: dict[str, float] = {}
            for sym in universe:
                if sym in delisted_securities:
                    open_prices[sym] = 0.0
                    continue
                bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
                if bar_sym is not None:
                    open_prices[sym] = bar_sym.open
                    last_known_close_prices[sym] = bar_sym.close
                else:
                    open_prices[sym] = 0.0

            curr_positions_val_at_open = sum(
                positions.get(sym, 0.0)
                * (
                    open_prices.get(sym, 0.0)
                    if open_prices.get(sym, 0.0) > 0.0
                    else last_known_close_prices.get(sym, 0.0)
                )
                for sym in universe
            )
            portfolio_val_at_open = cash + curr_positions_val_at_open

            # Compute desired share deltas for symbols with active open prices
            desired_deltas: dict[str, float] = {}
            symbols_to_process: list[str] = []

            for sym, target in list(pending_targets.items()):
                if sym in delisted_securities:
                    del pending_targets[sym]
                    continue

                open_p = open_prices.get(sym, 0.0)
                if open_p <= 0.0:
                    # Missing bar on this session: target remains pending for the next session
                    continue

                symbols_to_process.append(sym)
                target_w = target.weight
                curr_shares = positions.get(sym, 0.0)

                if abs(target_w) <= EPS:
                    target_shares = 0.0
                    holding_target_weights[sym] = 0.0
                elif target_w > 0.0:
                    # Long target
                    if (
                        curr_shares <= EPS
                        or abs(target_w - holding_target_weights.get(sym, 0.0)) > EPS
                    ):
                        denom = open_p * (1.0 + specification.execution.slippage_rate)
                        denom *= 1.0 + specification.execution.commission_rate
                        target_val = max(0.0, portfolio_val_at_open) * target_w
                        target_shares = target_val / denom if denom > 0.0 else 0.0
                        holding_target_weights[sym] = target_w
                    else:
                        target_shares = curr_shares
                else:
                    # Short target (target_w < 0.0)
                    if (
                        curr_shares >= -EPS
                        or abs(target_w - holding_target_weights.get(sym, 0.0)) > EPS
                    ):
                        eff_p = open_p * (1.0 - specification.execution.slippage_rate)
                        target_val_short = abs(target_w) * max(0.0, portfolio_val_at_open)
                        target_shares = -(target_val_short / eff_p) if eff_p > 0.0 else 0.0
                        holding_target_weights[sym] = target_w
                    else:
                        target_shares = curr_shares

                desired_deltas[sym] = target_shares - curr_shares

            # Execution ordering: SELLS execute before BUYS
            sell_symbols = [s for s in symbols_to_process if desired_deltas.get(s, 0.0) < -EPS]
            buy_symbols = [s for s in symbols_to_process if desired_deltas.get(s, 0.0) > EPS]

            # 2a. Process SELLS (long exits / short openings)
            for sym in sell_symbols:
                bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
                if bar_sym is None:
                    continue
                open_p = bar_sym.open
                delta = desired_deltas[sym]
                curr_shares = positions.get(sym, 0.0)
                sell_qty = abs(delta)

                if sell_qty <= EPS:
                    continue

                target = pending_targets.get(sym)
                decision_time = target.decision_time if target else bar_sym.available_at
                rationale = target.rationale if target else "Rebalance sell"

                slippage = specification.execution.slippage_rate
                effective_price = open_p * (1.0 - slippage)
                notional = -sell_qty * effective_price
                commission = abs(notional) * specification.execution.commission_rate
                slippage_cost = sell_qty * open_p * slippage

                ledger_account.record_cash_flow(
                    abs(notional),
                    flow_type="fill_sell",
                    description=f"Sell fill notional for {sym}",
                    timestamp=date_str,
                )
                ledger_account.record_cash_flow(
                    -commission,
                    flow_type="commission",
                    description=f"Sell commission for {sym}",
                    timestamp=date_str,
                )
                cash = ledger_account.cash
                new_shares = curr_shares - sell_qty
                positions[sym] = new_shares

                trade_id = ""
                open_tr = open_trades.get(sym)
                if open_tr is not None:
                    trade_id = open_tr.trade_id
                elif new_shares < -EPS:
                    trade_counter += 1
                    trade_id = f"trade-{trade_counter}"

                fill = Fill(
                    trade_id=trade_id,
                    security_id=sym,
                    session_date=date_str,
                    decision_time=decision_time,
                    side="sell",
                    quantity=round(sell_qty, 6),
                    price=round(effective_price, 4),
                    notional=round(notional, 4),
                    commission=round(commission, 4),
                    slippage_cost=round(slippage_cost, 4),
                    rationale=rationale,
                )
                fills.append(fill)
                fills_today.append(fill)

                # Trade lifecycle updates
                if curr_shares > EPS:
                    # Closing or reducing long
                    if open_tr is not None:
                        long_exit_qty = min(sell_qty, open_tr.quantity)
                        if long_exit_qty >= open_tr.quantity - EPS:
                            trades.append(_build_trade(open_tr, fill))
                            del open_trades[sym]
                        else:
                            closed_cost = open_tr.entry_cost * (long_exit_qty / open_tr.quantity)
                            partial_tr = replace(
                                open_tr, quantity=long_exit_qty, entry_cost=closed_cost
                            )
                            trades.append(_build_trade(partial_tr, fill))
                            rem_qty = open_tr.quantity - long_exit_qty
                            rem_cost = open_tr.entry_cost - closed_cost
                            open_trades[sym] = replace(
                                open_tr, quantity=rem_qty, entry_cost=rem_cost
                            )

                        if new_shares < -EPS:
                            # Flipped to short
                            trade_counter += 1
                            short_trade_id = f"trade-{trade_counter}"
                            short_qty = abs(new_shares)
                            open_trades[sym] = OpenTrade(
                                trade_id=short_trade_id,
                                security_id=sym,
                                entry_date=date_str,
                                entry_price=fill.price,
                                quantity=short_qty,
                                entry_cost=(
                                    short_qty * fill.price - (short_qty / sell_qty) * commission
                                ),
                                side="short",
                            )
                elif curr_shares >= -EPS and new_shares < -EPS:
                    # Opening short from flat
                    open_trades[sym] = OpenTrade(
                        trade_id=trade_id,
                        security_id=sym,
                        entry_date=date_str,
                        entry_price=fill.price,
                        quantity=sell_qty,
                        entry_cost=abs(notional) - commission,
                        side="short",
                    )

            # 2b. Process BUYS (short covers / long openings)
            for sym in buy_symbols:
                bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
                if bar_sym is None:
                    continue
                open_p = bar_sym.open
                delta = desired_deltas[sym]
                curr_shares = positions.get(sym, 0.0)

                slippage = specification.execution.slippage_rate
                effective_price = open_p * (1.0 + slippage)
                cost_per_share = effective_price * (1.0 + specification.execution.commission_rate)

                target = pending_targets.get(sym)
                decision_time = target.decision_time if target else bar_sym.available_at
                rationale = target.rationale if target else "Rebalance buy"

                cover_shares = min(delta, abs(curr_shares)) if curr_shares < -EPS else 0.0
                new_long_delta = max(0.0, delta - cover_shares)
                new_long_cost = new_long_delta * cost_per_share

                margin_req = specification.execution.margin_requirement
                allowed_long_shares = new_long_delta

                if new_long_delta > EPS:
                    if margin_req < 1.0:
                        avail_capacity = max(0.0, portfolio_val_at_open) / margin_req
                        if avail_capacity <= EPS:
                            rejections.append(
                                ConstraintRejection(
                                    session_date=date_str,
                                    security_id=sym,
                                    rule="margin_limit",
                                    reason=(
                                        f"Insufficient margin equity ({portfolio_val_at_open:.2f}) "
                                        f"to execute long buy for {sym}."
                                    ),
                                    requested_weight=target.weight if target else None,
                                )
                            )
                            warnings.append(f"Insufficient margin to buy {sym} on {date_str}.")
                            allowed_long_shares = 0.0
                        elif new_long_cost > avail_capacity:
                            allowed_long_shares = avail_capacity / cost_per_share
                            rejections.append(
                                ConstraintRejection(
                                    session_date=date_str,
                                    security_id=sym,
                                    rule="partial_fill_margin_limit",
                                    reason=(
                                        f"Partial fill for {sym} "
                                        f"({cover_shares + allowed_long_shares:.4f} of "
                                        f"{delta:.4f} shares) due to margin limit."
                                    ),
                                    requested_weight=target.weight if target else None,
                                )
                            )
                    else:
                        if cash <= EPS:
                            rejections.append(
                                ConstraintRejection(
                                    session_date=date_str,
                                    security_id=sym,
                                    rule="cash_limit",
                                    reason=(
                                        f"Insufficient cash ({cash:.2f}) to execute buy for {sym}."
                                    ),
                                    requested_weight=target.weight if target else None,
                                )
                            )
                            warnings.append(f"Insufficient cash to buy {sym} on {date_str}.")
                            allowed_long_shares = 0.0
                        elif new_long_cost > cash:
                            allowed_long_shares = cash / cost_per_share
                            rejections.append(
                                ConstraintRejection(
                                    session_date=date_str,
                                    security_id=sym,
                                    rule="partial_fill_cash_limit",
                                    reason=(
                                        f"Partial fill for {sym} "
                                        f"({cover_shares + allowed_long_shares:.4f} of "
                                        f"{delta:.4f} shares) due to cash limit."
                                    ),
                                    requested_weight=target.weight if target else None,
                                )
                            )

                buy_qty = cover_shares + allowed_long_shares

                if buy_qty <= EPS:
                    continue

                notional = buy_qty * effective_price
                commission = notional * specification.execution.commission_rate
                slippage_cost = buy_qty * open_p * slippage

                ledger_account.record_cash_flow(
                    -notional,
                    flow_type="fill_buy",
                    description=f"Buy fill notional for {sym}",
                    timestamp=date_str,
                )
                ledger_account.record_cash_flow(
                    -commission,
                    flow_type="commission",
                    description=f"Buy commission for {sym}",
                    timestamp=date_str,
                )
                if margin_req >= 1.0 and ledger_account.cash < 0.0:
                    ledger_account.cash = 0.0
                cash = ledger_account.cash
                new_shares = curr_shares + buy_qty
                positions[sym] = new_shares

                trade_id = ""
                open_tr = open_trades.get(sym)
                if open_tr is not None:
                    trade_id = open_tr.trade_id
                elif new_shares > EPS:
                    trade_counter += 1
                    trade_id = f"trade-{trade_counter}"

                fill = Fill(
                    trade_id=trade_id,
                    security_id=sym,
                    session_date=date_str,
                    decision_time=decision_time,
                    side="buy",
                    quantity=round(buy_qty, 6),
                    price=round(effective_price, 4),
                    notional=round(notional, 4),
                    commission=round(commission, 4),
                    slippage_cost=round(slippage_cost, 4),
                    rationale=rationale,
                )
                fills.append(fill)
                fills_today.append(fill)

                # Trade lifecycle updates
                if curr_shares < -EPS:
                    # Covering or reducing short
                    if open_tr is not None:
                        short_cover_qty = min(buy_qty, open_tr.quantity)
                        if short_cover_qty >= open_tr.quantity - EPS:
                            trades.append(_build_trade(open_tr, fill))
                            del open_trades[sym]
                        else:
                            closed_cost = open_tr.entry_cost * (short_cover_qty / open_tr.quantity)
                            partial_tr = replace(
                                open_tr, quantity=short_cover_qty, entry_cost=closed_cost
                            )
                            trades.append(_build_trade(partial_tr, fill))
                            rem_qty = open_tr.quantity - short_cover_qty
                            rem_cost = open_tr.entry_cost - closed_cost
                            open_trades[sym] = replace(
                                open_tr, quantity=rem_qty, entry_cost=rem_cost
                            )

                        if new_shares > EPS:
                            # Flipped to long
                            trade_counter += 1
                            long_trade_id = f"trade-{trade_counter}"
                            long_qty = new_shares
                            open_trades[sym] = OpenTrade(
                                trade_id=long_trade_id,
                                security_id=sym,
                                entry_date=date_str,
                                entry_price=fill.price,
                                quantity=long_qty,
                                entry_cost=(
                                    long_qty * fill.price + (long_qty / buy_qty) * commission
                                ),
                                side="long",
                            )
                elif curr_shares <= EPS and new_shares > EPS:
                    # Opening long from flat
                    open_trades[sym] = OpenTrade(
                        trade_id=trade_id,
                        security_id=sym,
                        entry_date=date_str,
                        entry_price=fill.price,
                        quantity=buy_qty,
                        entry_cost=notional + commission,
                        side="long",
                    )

            # Clear processed pending targets
            for sym in symbols_to_process:
                pending_targets.pop(sym, None)

        # -------------------------------------------------------------
        # STEP 3: Evaluate Strategy on today's close for each security
        # -------------------------------------------------------------
        candidate_targets: list[tuple[str, StrategyTarget, float, DailyBar]] = []
        active_universe = [s for s in universe if s not in delisted_securities]
        universe_size = len(active_universe)

        cross_sectional_evaluation = None
        if specification.strategy_name == "top_n_momentum":
            current_bars = {
                sym: bars_by_symbol[sym][date_str]
                for sym in active_universe
                if date_str in bars_by_symbol.get(sym, {})
            }
            decision_time = min((bar.available_at for bar in current_bars.values()), default=None)
            cross_views = {
                sym: _market_view(
                    sym,
                    sorted_all_bars,
                    decision_time,
                    specification.price_field,
                )
                for sym in current_bars
            }
            if cross_views and decision_time is not None:
                cross_sectional_evaluation = CROSS_SECTIONAL_STRATEGIES["top_n_momentum"](
                    cross_views,
                    specification.parameters,
                    decision_time=decision_time,
                    session_date=date_str,
                )
                ranking_records.extend(cross_sectional_evaluation.ranking_records)

        for sym in active_universe:
            bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
            if bar_sym is None:
                continue

            last_known_close_prices[sym] = _price_value(bar_sym, specification.price_field)

            if cross_sectional_evaluation is not None:
                evaluation = cross_sectional_evaluation
            else:
                view = _market_view(
                    sym, sorted_all_bars, bar_sym.available_at, specification.price_field
                )
                evaluation = evaluate_strategy(
                    specification.strategy_name,
                    view,
                    specification.parameters,
                    decision_time=bar_sym.available_at,
                )

            # In multi-security universe, normalize allocation by universe size
            targets = (
                (target for target in evaluation.targets if target.security_id == sym)
                if cross_sectional_evaluation is not None
                else evaluation.targets
            )
            for raw_t in targets:
                norm_weight = (
                    raw_t.weight
                    if specification.strategy_name == "top_n_momentum"
                    else raw_t.weight / universe_size if universe_size > 0 else 0.0
                )

                # Shorting & Borrow availability checks
                if norm_weight < 0.0:
                    if not specification.execution.allow_shorting:
                        rejections.append(
                            ConstraintRejection(
                                session_date=date_str,
                                security_id=sym,
                                rule="short_disabled",
                                reason=(
                                    f"Negative target weight ({norm_weight}) rejected: "
                                    "short positions are disabled in execution assumptions."
                                ),
                                requested_weight=round(norm_weight, 6),
                            )
                        )
                        warnings.append(
                            f"Short target for {sym} on {date_str} rejected (shorting disabled)."
                        )
                        norm_weight = 0.0
                    elif sym in specification.execution.unavailable_borrow:
                        rejections.append(
                            ConstraintRejection(
                                session_date=date_str,
                                security_id=sym,
                                rule="borrow_unavailable",
                                reason=(
                                    f"Borrow unavailable for '{sym}' "
                                    "(hard-to-borrow constraint)."
                                ),
                                requested_weight=round(norm_weight, 6),
                            )
                        )
                        warnings.append(
                            f"Borrow unavailable for {sym} on {date_str}; short target rejected."
                        )
                        norm_weight = 0.0

                candidate_targets.append((sym, raw_t, norm_weight, bar_sym))

        # Leverage limit evaluation across portfolio target gross exposure
        total_target_gross = sum(abs(norm_w) for _, _, norm_w, _ in candidate_targets)
        max_lev = specification.execution.max_leverage
        is_leverage_breached = total_target_gross > max_lev + EPS

        today_signal_weights: dict[str, float] = {}
        primary_target: StrategyTarget | None = None

        if is_leverage_breached:
            if specification.execution.leverage_mode == "reject":
                for sym, raw_t, norm_w, bar_sym in candidate_targets:
                    prior_w = holding_target_weights.get(sym, 0.0)
                    if abs(norm_w) > EPS:
                        rejections.append(
                            ConstraintRejection(
                                session_date=date_str,
                                security_id=sym,
                                rule="leverage_limit",
                                reason=(
                                    f"Target gross exposure ({total_target_gross:.2f}) exceeds "
                                    f"maximum leverage limit of {max_lev:.2f}."
                                ),
                                requested_weight=round(norm_w, 6),
                            )
                        )
                        warnings.append(
                            f"Target for {sym} on {date_str} (weight {norm_w:.4f}) rejected: "
                            f"portfolio gross exposure ({total_target_gross:.2f}) "
                            f"exceeds max leverage {max_lev:.2f}."
                        )
                    target = replace(raw_t, weight=prior_w)
                    signals.append(target)
                    today_signal_weights[sym] = prior_w
                    pending_targets[sym] = PendingTarget(
                        security_id=sym,
                        weight=prior_w,
                        decision_time=bar_sym.available_at,
                        rationale=target.rationale,
                    )
                    if sym == primary_symbol:
                        primary_target = target
            else:
                scale_factor = max_lev / total_target_gross if total_target_gross > 0 else 1.0
                for sym, raw_t, norm_w, bar_sym in candidate_targets:
                    if abs(norm_w) > EPS:
                        scaled_w = round(norm_w * scale_factor, 6)
                        rejections.append(
                            ConstraintRejection(
                                session_date=date_str,
                                security_id=sym,
                                rule="leverage_constrained",
                                reason=(
                                    f"Target weight {norm_w:.4f} scaled to {scaled_w:.4f} "
                                    f"(scale factor {scale_factor:.4f}) to satisfy maximum "
                                    f"leverage limit of {max_lev:.2f}."
                                ),
                                requested_weight=round(norm_w, 6),
                            )
                        )
                    else:
                        scaled_w = 0.0
                    target = replace(raw_t, weight=scaled_w)
                    signals.append(target)
                    today_signal_weights[sym] = scaled_w
                    pending_targets[sym] = PendingTarget(
                        security_id=sym,
                        weight=scaled_w,
                        decision_time=bar_sym.available_at,
                        rationale=target.rationale,
                    )
                    if sym == primary_symbol:
                        primary_target = target
        else:
            for sym, raw_t, norm_w, bar_sym in candidate_targets:
                target = replace(raw_t, weight=round(norm_w, 6))
                signals.append(target)
                today_signal_weights[sym] = target.weight
                pending_targets[sym] = PendingTarget(
                    security_id=sym,
                    weight=target.weight,
                    decision_time=bar_sym.available_at,
                    rationale=target.rationale,
                )
                if sym == primary_symbol:
                    primary_target = target

        # -------------------------------------------------------------
        # STEP 4: Mark-to-market and borrow cost accounting at close
        # -------------------------------------------------------------
        borrow_fee_today = 0.0
        for sym in universe:
            shares_sym = positions.get(sym, 0.0)
            if shares_sym < -EPS:
                bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
                close_p = (
                    _price_value(bar_sym, specification.price_field)
                    if bar_sym
                    else last_known_close_prices.get(sym, 0.0)
                )
                short_val = abs(shares_sym) * close_p
                borrow_rate = specification.execution.hard_to_borrow_rates.get(
                    sym, specification.execution.borrow_fee_rate
                )
                if borrow_rate > 0.0:
                    daily_fee = short_val * (borrow_rate / 252.0)
                    borrow_fee_today += daily_fee

        if borrow_fee_today > 0.0:
            ledger_account.record_borrow_fee(
                borrow_fee_today,
                description=f"Short borrow fee for session {date_str}",
                timestamp=date_str,
            )
            if ledger_account.cash < 0.0:
                ledger_account.cash = 0.0
            cash = ledger_account.cash

        position_snapshots: dict[str, PositionSnapshot] = {}
        total_pos_val = 0.0
        gross_pos_val = 0.0
        primary_close = 0.0
        primary_shares = positions.get(primary_symbol, 0.0)

        for sym in universe:
            if sym in delisted_securities:
                close_p = 0.0
            else:
                bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
                if bar_sym is not None:
                    close_p = _price_value(bar_sym, specification.price_field)
                    last_known_close_prices[sym] = close_p
                else:
                    close_p = last_known_close_prices.get(sym, 0.0)

            if sym == primary_symbol:
                primary_close = close_p

            shares_sym = positions.get(sym, 0.0)
            val_sym = shares_sym * close_p
            total_pos_val += val_sym
            gross_pos_val += abs(val_sym)

        portfolio_val = ledger_account.calculate_equity(total_pos_val)

        for sym in universe:
            if sym in delisted_securities:
                close_p = 0.0
            else:
                bar_sym = bars_by_symbol.get(sym, {}).get(date_str)
                close_p = (
                    _price_value(bar_sym, specification.price_field)
                    if bar_sym
                    else last_known_close_prices.get(sym, 0.0)
                )

            shares_sym = positions.get(sym, 0.0)
            val_sym = shares_sym * close_p
            w_sym = (val_sym / portfolio_val) if portfolio_val > 0.0 else 0.0

            position_snapshots[sym] = PositionSnapshot(
                shares=round(shares_sym, 6),
                close_price=round(close_p, 4),
                position_value=round(val_sym, 4),
                weight=round(w_sym, 6),
            )

        gross_exp = (gross_pos_val / portfolio_val) if portfolio_val > 0.0 else 0.0
        net_exp = (total_pos_val / portfolio_val) if portfolio_val > 0.0 else 0.0

        # Maintenance margin threshold check at session close
        if gross_pos_val > EPS and portfolio_val > 0:
            maint_req = gross_pos_val * specification.execution.maintenance_margin
            if portfolio_val < maint_req:
                maint_warning = (
                    f"Margin call on {date_str}: Portfolio value (${portfolio_val:,.2f}) fell "
                    f"below maintenance margin requirement (${maint_req:,.2f}, "
                    f"{specification.execution.maintenance_margin * 100:.1f}% "
                    f"of gross position value ${gross_pos_val:,.2f})."
                )
                warnings.append(maint_warning)
                for sym in universe:
                    if abs(positions.get(sym, 0.0)) > EPS:
                        rejections.append(
                            ConstraintRejection(
                                session_date=date_str,
                                security_id=sym,
                                rule="maintenance_margin_call",
                                reason=maint_warning,
                                requested_weight=position_snapshots.get(
                                    sym, PositionSnapshot(0.0, 0.0, 0.0, 0.0)
                               ).weight,
                            )
                        )

        ledger_account.record_snapshot(
            date_str,
            portfolio_val,
            SnapshotMetrics(
                gross_exposure=gross_exp,
                net_exposure=net_exp,
                cash_interest=cash_interest_today,
                borrow_fees=borrow_fee_today,
                dividends=dividends_today,
            ),
        )

        ledger.append(
            LedgerRow(
                session_date=date_str,
                signal_weight=primary_target.weight if primary_target else None,
                signal_decision_time=primary_target.decision_time if primary_target else None,
                fill=fills_today[0] if fills_today else None,
                shares=round(primary_shares, 6),
                close_price=primary_close,
                cash=round(cash, 4),
                position_value=round(total_pos_val, 4),
                portfolio_value=round(portfolio_val, 4),
                positions=position_snapshots,
                signal_weights=today_signal_weights,
                gross_exposure=round(gross_exp, 6),
                net_exposure=round(net_exp, 6),
                borrow_fees=round(borrow_fee_today, 4),
                cash_interest=round(cash_interest_today, 4),
                dividends=round(dividends_today, 4),
                splits=splits_today,
                delistings=tuple(delistings_today),
            )
        )

    if not fills:
        warnings.append("No fills occurred during the backtest window.")

    if pending_targets:
        for sym, pending in pending_targets.items():
            curr_w = position_snapshots.get(sym, PositionSnapshot(0, 0, 0, 0)).weight
            if abs(pending.weight - curr_w) > EPS:
                warnings.append(
                    f"Final signal for {sym} on {sorted_window_dates[-1]} "
                    f"(weight {pending.weight}) has no subsequent bar to fill."
                )

    drawdown_curve = [
        EquityPoint(
            session_date=pt["timestamp"],
            equity=pt["equity"],
            drawdown=pt["drawdown"],
        )
        for pt in ledger_account.build_drawdown_curve()
    ]
    curve = list(drawdown_curve)

    # -------------------------------------------------------------
    # Benchmark calculations
    # -------------------------------------------------------------
    benchmark_equity_curve: tuple[EquityPoint, ...] = ()
    bench_relative_return: float | None = None
    if specification.benchmark_security_id:
        bench_result = _compute_benchmark_curve(
            specification.benchmark_security_id,
            bars_by_symbol,
            sorted_window_dates,
            specification.starting_cash,
        )
        benchmark_equity_curve = bench_result.curve
        if bench_result.total_return is not None and curve:
            port_total_return = (curve[-1].equity / specification.starting_cash) - 1.0
            bench_relative_return = port_total_return - bench_result.total_return

    metrics = _compute_metrics(
        MetricsCalculationInput(
            ledger=ledger,
            starting_cash=specification.starting_cash,
            fills=fills,
            trades=trades,
            benchmark_relative_return=bench_relative_return,
        )
    )

    total_commission = round(sum(fill.commission for fill in fills), 4)
    total_slippage = round(sum(fill.slippage_cost for fill in fills), 4)
    total_borrow_fees = round(sum(row.borrow_fees for row in ledger), 4)
    total_cash_interest = round(sum(row.cash_interest for row in ledger), 4)
    total_dividends = round(sum(row.dividends for row in ledger), 4)
    total_costs = round(
        total_commission + total_slippage + total_borrow_fees - total_cash_interest,
        4,
    )

    manifest: dict[str, JsonValue] = {
        "kind": "backtest",
        "strategy_name": specification.strategy_name,
        "strategy_revision": specification.strategy_revision,
        "dataset_version_id": specification.dataset_version_id,
        "security_id": specification.security_id or primary_symbol,
        "universe": list(universe),
        "benchmark_security_id": specification.benchmark_security_id,
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
            "allow_shorting": specification.execution.allow_shorting,
            "borrow_fee_rate": specification.execution.borrow_fee_rate,
            "cash_interest_rate": specification.execution.cash_interest_rate,
            "unavailable_borrow": list(specification.execution.unavailable_borrow),
            "max_leverage": specification.execution.max_leverage,
            "margin_requirement": specification.execution.margin_requirement,
            "maintenance_margin": specification.execution.maintenance_margin,
            "leverage_mode": specification.execution.leverage_mode,
        },
        "signal_count": len(signals),
        "fill_count": len(fills),
        "trade_count": len(trades),
        "rejection_count": len(rejections),
        "cash_interest_periods": cash_interest_periods,
        "corporate_actions": {
            "total_dividends": total_dividends,
            "total_splits": total_splits_count,
            "delistings": delistings_applied,
        },
        "costs": {
            "total_commission": total_commission,
            "total_slippage": total_slippage,
            "total_borrow_fees": total_borrow_fees,
            "total_cash_interest": total_cash_interest,
            "total_dividends": total_dividends,
            "total_costs": total_costs,
            "portfolio_impact": {
                "commission": round(-total_commission, 4),
                "slippage": round(-total_slippage, 4),
                "borrow_fees": round(-total_borrow_fees, 4),
                "cash_interest": total_cash_interest,
                "dividends": total_dividends,
                "net": round(
                    -total_commission
                    - total_slippage
                    - total_borrow_fees
                    + total_cash_interest
                    + total_dividends,
                    4,
                ),
            },
        },
    }

    return BacktestResult(
        specification=specification,
        signals=tuple(signals),
        fills=tuple(fills),
        trades=tuple(trades),
        ledger=tuple(ledger),
        equity_curve=tuple(curve),
        drawdown_curve=tuple(drawdown_curve),
        metrics=metrics,
        warnings=tuple(warnings),
        manifest=manifest,
        benchmark_equity_curve=benchmark_equity_curve,
        rejections=tuple(rejections),
        ranking_records=tuple(ranking_records),
    )
