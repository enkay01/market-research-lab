"""Deterministic historical Put Credit Spread backtesting.

This module is deliberately specific to the first options slice.  It consumes a
named, point-in-time eligible ``OptionMarketData`` value and does not place
orders or depend on a provider client.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Literal, Mapping, NamedTuple, Sequence
from zoneinfo import ZoneInfo

from .json_types import JsonValue
from .market_data import (
    DailyBar,
    EarningsEvent,
    OptionContract,
    OptionMarketData,
    OptionTrade,
    UnderlyingMinuteBar,
)

NEW_YORK = ZoneInfo("America/New_York")
FEE_PER_LEG = 0.65
EPS = 1e-9


class OptionBacktestError(ValueError):
    """Raised when options data or a Put Credit Spread specification is invalid."""


class OptionBacktestParameterError(OptionBacktestError):
    """Raised when an options Backtest parameter is invalid."""


@dataclass(frozen=True)
class OptionGreeks:
    delta: float
    theta: float
    gamma: float
    vega: float
    implied_volatility: float


@dataclass(frozen=True)
class SpreadCandidate:
    short_contract: OptionContract
    long_contract: OptionContract
    short_delta: float
    implied_volatility: float
    short_trade_price: float
    long_trade_price: float
    selection_reason: str

    @property
    def width(self) -> float:
        return self.short_contract.strike - self.long_contract.strike


@dataclass(frozen=True)
class StopMovement:
    timestamp: str
    underlying_price: float
    new_stop: float
    trigger_rule: str


@dataclass(frozen=True)
class CounterfactualOutcome:
    outcome: Literal["STOP_SAVED", "TARGET_ACHIEVED", "WHIPSAWED", "NOT_APPLICABLE"]
    avoided_loss_or_missed_gain: float
    explanation: str


@dataclass(frozen=True)
class TrajectoryPoint:
    minute: str
    stock_price: float
    spread_worst: float
    spread_best: float
    stop_level: float


@dataclass(frozen=True)
class PriceCandle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class SpreadPosition:
    id: str
    security_id: str
    spread_type: Literal["Put Credit"] = "Put Credit"
    short_strike: float = 0.0
    long_strike: float = 0.0
    width: float = 0.0
    expiration: str = ""
    entry_credit: float = 0.0
    margin_required: float = 0.0
    full_possible_loss: float = 0.0
    return_on_margin_pct: float = 0.0
    annualized_rom_pct: float = 0.0
    worst_net_pnl: float = 0.0
    best_net_pnl: float = 0.0
    days_held: int = 0
    open_timestamp: str = ""
    open_rule: str = ""
    close_timestamp: str | None = None
    close_rule: str = "Open Position"
    status: str = "Open Position"
    short_delta: float = 0.0
    implied_volatility: float = 0.0
    bid_ask_spread_drag: float = 0.0
    slippage_cost: float = 0.0
    execution_mode: str = "worst"
    reliability_pct: float = 100.0
    missing_minutes_count: int = 0
    stop_movements: tuple[StopMovement, ...] = ()
    greeks: dict[str, OptionGreeks | None] = field(default_factory=dict)
    counterfactual: CounterfactualOutcome | None = None
    candles: tuple[PriceCandle, ...] = ()
    trajectory_points: tuple[TrajectoryPoint, ...] = ()
    quantity: int = 1
    entry_fee: float = 0.0
    exit_fee: float = 0.0


@dataclass(frozen=True)
class BlockedCandidate:
    timestamp: str
    security_id: str
    reason: str
    rule: str


@dataclass(frozen=True)
class OptionBacktestSummary:
    worst_net_pnl: float
    best_net_pnl: float
    portfolio_rom_pct: float
    win_rate_pct: float
    winning_trades: int
    losing_trades: int
    total_trades: int
    max_drawdown_pct: float
    total_slippage_drag: float
    overall_reliability_pct: float
    rejection_counts: dict[str, int]


@dataclass(frozen=True)
class OptionsBacktestSpecification:
    """All rules that affect a Put Credit Spread replay."""

    strategy_name: str = "put_credit_spread"
    strategy_revision: str = "v1"
    dataset_version_id: str = ""
    start_date: str = ""
    end_date: str = ""
    starting_cash: float = 100000.0
    symbols: tuple[str, ...] = ()
    watchlist: tuple[str, ...] = ()
    path: Literal["worst", "best"] = "worst"
    automatic_selection: bool = True
    fixed_short_contract_id: str | None = None
    fixed_long_contract_id: str | None = None
    dte_min: int = 30
    dte_max: int = 45
    delta_min: float = 0.15
    delta_max: float = 0.20
    target_delta: float = 0.175
    iv_min: float = 0.30
    iv_max: float = 0.55
    previous_day_volume_min: float = 100000.0
    preferred_width: float = 2.50
    fallback_width: float = 5.00
    risk_per_position: float = 0.02
    max_open_risk: float = 0.10
    max_open_securities: int = 3
    similarity_limit: float = 0.70
    fee_per_leg: float = FEE_PER_LEG
    risk_free_rate: float = 0.0
    dividend_yield: float = 0.0
    cash_interest_rate: float = 0.0
    benchmark_security_id: str | None = "SPY"

    @property
    def selected_symbols(self) -> tuple[str, ...]:
        return self.watchlist or self.symbols


@dataclass(frozen=True)
class OptionsBacktestResult:
    specification: OptionsBacktestSpecification
    summary: OptionBacktestSummary
    positions: tuple[SpreadPosition, ...]
    blocked_candidates: tuple[BlockedCandidate, ...]
    warnings: tuple[str, ...]
    manifest: dict[str, JsonValue]
    best_positions: tuple[SpreadPosition, ...] = ()
    equity_curve: tuple[dict[str, JsonValue], ...] = ()
    benchmark_equity_curve: tuple[dict[str, JsonValue], ...] = ()

    @property
    def worst_net_pnl(self) -> float:
        return self.summary.worst_net_pnl

    @property
    def best_net_pnl(self) -> float:
        return self.summary.best_net_pnl

    def to_json(self) -> dict[str, JsonValue]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class _MinuteRange:
    low: float
    high: float
    last: float


class _SpreadValues(NamedTuple):
    worst: float
    best: float


@dataclass(frozen=True)
class _PathPositionData:
    data: OptionMarketData
    candidate: SpreadCandidate
    all_values: Sequence[tuple[datetime, float, float, float]]
    expiration: str
    fee_per_leg: float


@dataclass(frozen=True)
class _SimulationResult:
    positions: tuple[SpreadPosition, ...]
    blocked: list[BlockedCandidate]
    rejection_counts: dict[str, int]
    equity_curve: list[dict[str, JsonValue]]
    warnings: list[str]
    entry_plan: dict[tuple[str, str], tuple[str, str, int]]


@dataclass(frozen=True)
class _SimulationOptions:
    symbols: Sequence[str]
    path: str
    entry_plan: Mapping[tuple[str, str], tuple[str, str, int]] | None = None


@dataclass
class _OpenPosition:
    position_id: str
    candidate: SpreadCandidate
    quantity: int
    entry_timestamp: str
    entry_credit: float
    entry_fee: float
    collateral: float
    stop_level: float
    matched_minutes: int = 0
    missing_minutes: int = 0
    stop_movements: list[StopMovement] = field(default_factory=list)
    trajectory: list[TrajectoryPoint] = field(default_factory=list)
    pending_exit_reason: str | None = None
    pending_exit_after: datetime | None = None
    exit_timestamp: str | None = None
    exit_value: float | None = None
    exit_fee: float = 0.0
    pnl: float = 0.0
    close_rule: str = "Open Position"
    last_greeks: OptionGreeks | None = None
    entry_greeks: OptionGreeks | None = None
    mid_greeks: OptionGreeks | None = None


def _json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OptionBacktestError(f"Invalid timestamp: {value!r}.") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=NEW_YORK)
    return parsed.astimezone(NEW_YORK)


def _minute(value: str) -> datetime:
    parsed = _timestamp(value)
    return parsed.replace(second=0, microsecond=0)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise OptionBacktestParameterError(f"Invalid date: {value!r}.") from error


def _minute_text(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


@dataclass(frozen=True)
class OptionPricingInputs:
    spot: float
    strike: float
    years: float
    rate: float = 0.0
    dividend: float = 0.0
    right: Literal["put", "call"] = "put"


def _option_price(inputs: OptionPricingInputs, volatility: float) -> float:
    if inputs.years <= 0.0:
        return max(
            0.0,
            (inputs.spot - inputs.strike)
            if inputs.right == "call"
            else (inputs.strike - inputs.spot),
        )
    root = volatility * math.sqrt(inputs.years)
    d1 = (
        math.log(inputs.spot / inputs.strike)
        + (inputs.rate - inputs.dividend + 0.5 * volatility * volatility) * inputs.years
    ) / root
    d2 = d1 - root
    discount = math.exp(-inputs.rate * inputs.years)
    carry = math.exp(-inputs.dividend * inputs.years)
    if inputs.right == "call":
        return inputs.spot * carry * _normal_cdf(d1) - inputs.strike * discount * _normal_cdf(d2)
    return inputs.strike * discount * _normal_cdf(-d2) - inputs.spot * carry * _normal_cdf(-d1)


def black_scholes_iv(option_price: float, inputs: OptionPricingInputs) -> float:
    """Solve European Black-Scholes implied volatility by bisection."""
    if option_price <= 0.0 or inputs.spot <= 0.0 or inputs.strike <= 0.0 or inputs.years <= 0.0:
        return 0.0
    low, high = 1e-6, 5.0
    low_price = _option_price(inputs, low)
    high_price = _option_price(inputs, high)
    if option_price < low_price - 1e-8 or option_price > high_price + 1e-8:
        return 0.0
    for _ in range(80):
        middle = (low + high) / 2.0
        if _option_price(inputs, middle) < option_price:
            low = middle
        else:
            high = middle
    return round((low + high) / 2.0, 10)


def black_scholes_greeks(inputs: OptionPricingInputs, volatility: float) -> OptionGreeks:
    """Return local European Black-Scholes IV and first-order Greeks."""
    if min(inputs.spot, inputs.strike, inputs.years, volatility) <= 0.0:
        return OptionGreeks(0.0, 0.0, 0.0, 0.0, max(volatility, 0.0))
    root = volatility * math.sqrt(inputs.years)
    d1 = (
        math.log(inputs.spot / inputs.strike)
        + (inputs.rate - inputs.dividend + 0.5 * volatility**2) * inputs.years
    ) / root
    d2 = d1 - root
    discount = math.exp(-inputs.rate * inputs.years)
    carry = math.exp(-inputs.dividend * inputs.years)
    gamma = carry * _normal_pdf(d1) / (inputs.spot * root)
    vega = inputs.spot * carry * _normal_pdf(d1) * math.sqrt(inputs.years) / 100.0
    if inputs.right == "call":
        delta = carry * _normal_cdf(d1)
        theta = (
            -inputs.spot * carry * _normal_pdf(d1) * volatility / (2.0 * math.sqrt(inputs.years))
            - inputs.rate * inputs.strike * discount * _normal_cdf(d2)
            + inputs.dividend * inputs.spot * carry * _normal_cdf(d1)
        ) / 365.0
    else:
        delta = carry * (_normal_cdf(d1) - 1.0)
        theta = (
            -inputs.spot * carry * _normal_pdf(d1) * volatility / (2.0 * math.sqrt(inputs.years))
            + inputs.rate * inputs.strike * discount * _normal_cdf(-d2)
            - inputs.dividend * inputs.spot * carry * _normal_cdf(-d1)
        ) / 365.0
    return OptionGreeks(
        delta=round(delta, 8),
        theta=round(theta, 8),
        gamma=round(gamma, 8),
        vega=round(vega, 8),
        implied_volatility=round(volatility, 8),
    )


# Names that read well at call sites and keep the calculation easy to discover.
black_scholes_implied_volatility = black_scholes_iv
calculate_option_greeks = black_scholes_greeks


def eligible_option_contracts(
    contracts: Sequence[OptionContract], as_of: str | datetime
) -> tuple[OptionContract, ...]:
    cutoff = _timestamp(as_of) if isinstance(as_of, str) else as_of.astimezone(NEW_YORK)
    return tuple(
        contract
        for contract in contracts
        if contract.available_at is not None
        and _timestamp(contract.available_at) <= cutoff
        and (contract.inactivated_at is None or _timestamp(contract.inactivated_at) > cutoff)
    )


def eligible_option_trades(
    trades: Sequence[OptionTrade], as_of: str | datetime
) -> tuple[OptionTrade, ...]:
    cutoff = _timestamp(as_of) if isinstance(as_of, str) else as_of.astimezone(NEW_YORK)
    return tuple(
        trade
        for trade in trades
        if trade.available_at is not None and _timestamp(trade.available_at) <= cutoff
    )


def eligible_option_market_data(
    market_data: OptionMarketData, as_of: str | datetime
) -> OptionMarketData:
    """Return only option and stock observations known at ``as_of``."""
    cutoff = _timestamp(as_of) if isinstance(as_of, str) else as_of.astimezone(NEW_YORK)
    eligible_stocks = tuple(
        bar
        for bar in market_data.underlying_bars
        if bar.available_at is not None and _timestamp(bar.available_at) <= cutoff
    )
    eligible_daily = tuple(
        bar
        for bar in market_data.daily_bars
        if bar.available_at is not None and _timestamp(bar.available_at) <= cutoff
    )
    return OptionMarketData(
        contracts=eligible_option_contracts(market_data.contracts, cutoff),
        option_trades=eligible_option_trades(market_data.option_trades, cutoff),
        underlying_bars=eligible_stocks,
        daily_bars=eligible_daily,
        earnings=tuple(
            event
            for event in market_data.earnings
            if event.available_at is not None and _timestamp(event.available_at) <= cutoff
        ),
        dataset_version_id=market_data.dataset_version_id,
        provider=market_data.provider,
    )


def _trade_ranges(
    data: OptionMarketData, *, as_of: datetime | None = None
) -> dict[tuple[str, datetime], _MinuteRange]:
    ranges: dict[tuple[str, datetime], _MinuteRange] = {}
    for trade in data.option_trades:
        event_time = _timestamp(trade.timestamp)
        eligibility_cutoff = as_of or event_time + timedelta(minutes=1)
        if trade.available_at is None or _timestamp(trade.available_at) > eligibility_cutoff:
            continue
        key = (trade.contract_id, event_time.replace(second=0, microsecond=0))
        prior = ranges.get(key)
        if prior is None:
            ranges[key] = _MinuteRange(trade.price, trade.price, trade.price)
        else:
            ranges[key] = _MinuteRange(
                min(prior.low, trade.price), max(prior.high, trade.price), trade.price
            )
    return ranges


def _stock_by_minute(data: OptionMarketData) -> dict[tuple[str, datetime], UnderlyingMinuteBar]:
    result: dict[tuple[str, datetime], UnderlyingMinuteBar] = {}
    for bar in data.underlying_bars:
        bar_minute = _minute(bar.timestamp)
        if bar.available_at is None or _timestamp(bar.available_at) > bar_minute + timedelta(
            minutes=1
        ):
            continue
        result[(bar.security_id, bar_minute)] = bar
    return result


def _contract_is_eligible(contract: OptionContract, when: datetime) -> bool:
    if contract.available_at is not None and _timestamp(contract.available_at) > when:
        return False
    if contract.inactivated_at is not None and _timestamp(contract.inactivated_at) <= when:
        return False
    return True


def _previous_volume(data: OptionMarketData, security_id: str, when: datetime) -> float:
    contract_ids = {item.contract_id for item in data.contracts if item.security_id == security_id}
    eligible_dates = sorted(
        {
            _timestamp(trade.timestamp).date()
            for trade in data.option_trades
            if trade.contract_id in contract_ids
            and _timestamp(trade.timestamp).date() < when.date()
            and trade.available_at is not None
            and _timestamp(trade.available_at) <= when
        }
    )
    if not eligible_dates:
        return 0.0
    previous = eligible_dates[-1]
    return sum(
        max(0.0, trade.size)
        for trade in data.option_trades
        if trade.contract_id in contract_ids
        and _timestamp(trade.timestamp).date() == previous
        and trade.available_at is not None
        and _timestamp(trade.available_at) <= when
    )


def _daily_trend_passes(daily_bars: Sequence[DailyBar], security_id: str, when: datetime) -> bool:
    closes = [
        bar.close
        for bar in daily_bars
        if bar.security_id == security_id
        and bar.session_date < when.date().isoformat()
        and bar.available_at is not None
        and _timestamp(bar.available_at) <= when
    ]
    if len(closes) < 200:
        return False
    ma20 = statistics.mean(closes[-20:])
    ma50 = statistics.mean(closes[-50:])
    ma200 = statistics.mean(closes[-200:])
    return ma20 > ma50 and ma50 > ma200 and closes[-1] > ma200


def _underlying_price(data: OptionMarketData, security_id: str, minute: datetime) -> float | None:
    bar = _stock_by_minute(data).get((security_id, minute))
    return bar.close if bar else None


def _pullback_passes(data: OptionMarketData, security_id: str, when: datetime) -> bool:
    bars = [
        bar
        for (symbol, minute), bar in sorted(_stock_by_minute(data).items())
        if symbol == security_id and minute <= when
    ]
    closes = [bar.close for bar in bars]
    daily = [
        bar.close
        for bar in data.daily_bars
        if bar.security_id == security_id
        and bar.session_date < when.date().isoformat()
        and bar.available_at is not None
        and _timestamp(bar.available_at) <= when
    ]
    if not closes or len(daily) < 200:
        return False
    ma200 = statistics.mean(daily[-200:])
    for start in range(max(0, len(closes) - 10), len(closes)):
        if abs(closes[start] - ma200) > ma200 * 0.02:
            continue
        recorded_high = max(closes[start : start + 5])
        after = closes[start + 5 :]
        if len(after) >= 2 and after[-1] > recorded_high and after[-2] > recorded_high:
            return True
    return False


def select_put_credit_spread(
    specification: OptionsBacktestSpecification,
    *,
    market_data: OptionMarketData,
    security_id: str,
    at: str | datetime,
) -> SpreadCandidate | None:
    """Select the closest eligible short delta and an allowed lower strike."""
    when = _timestamp(at) if isinstance(at, str) else at.astimezone(NEW_YORK)
    if specification.automatic_selection and not _daily_trend_passes(
        market_data.daily_bars, security_id, when
    ):
        return None
    if specification.automatic_selection and not _pullback_passes(market_data, security_id, when):
        return None
    if (
        specification.automatic_selection
        and _previous_volume(market_data, security_id, when)
        <= specification.previous_day_volume_min
    ):
        return None

    ranges = _trade_ranges(market_data, as_of=when + timedelta(minutes=1))
    underlying = _underlying_price(market_data, security_id, when.replace(second=0, microsecond=0))
    if underlying is None or underlying <= 0.0:
        return None
    candidates: list[SpreadCandidate] = []
    for short in market_data.contracts:
        if (
            short.security_id != security_id
            or short.right != "put"
            or not _contract_is_eligible(short, when)
        ):
            continue
        expiration = _date(short.expiration)
        dte = (expiration - when.date()).days
        if not specification.dte_min <= dte <= specification.dte_max:
            continue
        short_range = ranges.get((short.contract_id, when.replace(second=0, microsecond=0)))
        if short_range is None:
            continue
        short_price = (short_range.low + short_range.high) / 2.0
        years = max(dte / 365.0, 1 / 365.0)
        pricing = OptionPricingInputs(
            underlying,
            short.strike,
            years,
            specification.risk_free_rate,
            specification.dividend_yield,
        )
        iv = black_scholes_iv(short_price, pricing)
        greeks = black_scholes_greeks(pricing, iv)
        if not specification.delta_min <= abs(greeks.delta) <= specification.delta_max:
            continue
        if not specification.iv_min <= iv <= specification.iv_max:
            continue
        for width in (specification.preferred_width, specification.fallback_width):
            long = next(
                (
                    item
                    for item in market_data.contracts
                    if item.security_id == security_id
                    and item.right == "put"
                    and item.expiration == short.expiration
                    and math.isclose(item.strike, short.strike - width, abs_tol=1e-8)
                    and _contract_is_eligible(item, when)
                ),
                None,
            )
            if long is None:
                continue
            long_range = ranges.get((long.contract_id, when.replace(second=0, microsecond=0)))
            if long_range is None:
                continue
            candidates.append(
                SpreadCandidate(
                    short_contract=short,
                    long_contract=long,
                    short_delta=greeks.delta,
                    implied_volatility=iv,
                    short_trade_price=short_price,
                    long_trade_price=(long_range.low + long_range.high) / 2.0,
                    selection_reason=f"{dte} DTE, delta {abs(greeks.delta):.4f}, width {width:g}",
                )
            )
            break
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            abs(abs(item.short_delta) - specification.target_delta),
            item.short_trade_price - item.long_trade_price,
            item.short_contract.expiration,
        ),
    )


def _fixed_candidate(
    specification: OptionsBacktestSpecification, data: OptionMarketData, when: datetime
) -> SpreadCandidate | None:
    if not specification.fixed_short_contract_id or not specification.fixed_long_contract_id:
        return None
    short = next(
        (
            item
            for item in data.contracts
            if item.contract_id == specification.fixed_short_contract_id
        ),
        None,
    )
    long = next(
        (
            item
            for item in data.contracts
            if item.contract_id == specification.fixed_long_contract_id
        ),
        None,
    )
    if short is None or long is None:
        raise OptionBacktestError("The fixed Put Credit Spread contract IDs were not found.")
    if (
        short.right != "put"
        or long.right != "put"
        or short.security_id != long.security_id
        or short.expiration != long.expiration
        or short.strike <= long.strike
    ):
        raise OptionBacktestError(
            "Fixed contracts must be two puts for the same Security and expiration, "
            "with the short strike above the long strike."
        )
    ranges = _trade_ranges(data, as_of=when + timedelta(minutes=1))
    minute = when.replace(second=0, microsecond=0)
    short_range, long_range = (
        ranges.get((short.contract_id, minute)),
        ranges.get((long.contract_id, minute)),
    )
    if short_range is None or long_range is None:
        return None
    stock = _underlying_price(data, short.security_id, minute) or short.strike
    dte = max((_date(short.expiration) - when.date()).days, 1)
    short_price = (short_range.low + short_range.high) / 2.0
    pricing = OptionPricingInputs(
        stock,
        short.strike,
        dte / 365.0,
        specification.risk_free_rate,
        specification.dividend_yield,
    )
    iv = black_scholes_iv(short_price, pricing)
    greeks = black_scholes_greeks(pricing, iv)
    return SpreadCandidate(
        short,
        long,
        greeks.delta,
        iv,
        short_price,
        (long_range.low + long_range.high) / 2.0,
        "fixed contract selection",
    )


def _entry_credit(
    candidate: SpreadCandidate,
    ranges: dict[tuple[str, datetime], _MinuteRange],
    minute: datetime,
    path: str,
) -> float:
    short_range = ranges[(candidate.short_contract.contract_id, minute)]
    long_range = ranges[(candidate.long_contract.contract_id, minute)]
    if path == "best":
        credit = short_range.high - long_range.low
    else:
        credit = short_range.low - long_range.high
    return max(0.0, min(candidate.width, credit))


def _spread_values(
    candidate: SpreadCandidate, ranges: dict[tuple[str, datetime], _MinuteRange], minute: datetime
) -> _SpreadValues:
    short_range = ranges.get((candidate.short_contract.contract_id, minute))
    long_range = ranges.get((candidate.long_contract.contract_id, minute))
    if short_range is None or long_range is None:
        raise KeyError(minute)
    best = max(0.0, min(candidate.width, short_range.low - long_range.high))
    worst = max(0.0, min(candidate.width, short_range.high - long_range.low))
    return _SpreadValues(worst, best)


def _similarity(data: OptionMarketData, first: str, second: str, when: datetime) -> float:
    def closes(symbol: str) -> dict[str, float]:
        return {
            bar.session_date: bar.close
            for bar in data.daily_bars
            if bar.security_id == symbol
            and bar.session_date < when.date().isoformat()
            and bar.available_at is not None
            and _timestamp(bar.available_at) <= when
        }

    left, right = closes(first), closes(second)
    dates = sorted(set(left) & set(right))[-60:]
    if len(dates) < 2:
        return 0.0
    left_returns = [left[b] / left[a] - 1.0 for a, b in zip(dates, dates[1:]) if left[a] != 0]
    right_returns = [right[b] / right[a] - 1.0 for a, b in zip(dates, dates[1:]) if right[a] != 0]
    if (
        len(left_returns) < 2
        or statistics.pstdev(left_returns) == 0
        or statistics.pstdev(right_returns) == 0
    ):
        return 0.0
    mean_left, mean_right = statistics.mean(left_returns), statistics.mean(right_returns)
    covariance = statistics.mean(
        (a - mean_left) * (b - mean_right) for a, b in zip(left_returns, right_returns)
    )
    return covariance / (statistics.pstdev(left_returns) * statistics.pstdev(right_returns))


def _matching_minutes(
    data: OptionMarketData, candidate: SpreadCandidate, security_id: str
) -> dict[datetime, tuple[float, float, float]]:
    ranges = _trade_ranges(data)
    stock = _stock_by_minute(data)
    result: dict[datetime, tuple[float, float, float]] = {}
    keys = {minute for symbol, minute in stock if symbol == security_id}
    for minute in keys:
        if (candidate.short_contract.contract_id, minute) not in ranges or (
            candidate.long_contract.contract_id,
            minute,
        ) not in ranges:
            continue
        worst, best = _spread_values(candidate, ranges, minute)
        result[minute] = (stock[(security_id, minute)].close, worst, best)
    return result


def _position_values(
    data: OptionMarketData, position: _OpenPosition
) -> list[tuple[datetime, float, float, float]]:
    values = [
        (_minute(item.minute), item.stock_price, item.spread_worst, item.spread_best)
        for item in position.trajectory
    ]
    if position.exit_timestamp is None:
        return values
    exit_minute = _minute(position.exit_timestamp)
    observed = {minute for minute, _, _, _ in values}
    for minute, (stock_price, worst, best) in _matching_minutes(
        data, position.candidate, position.candidate.short_contract.security_id
    ).items():
        if minute > exit_minute and minute not in observed:
            values.append((minute, stock_price, worst, best))
    return sorted(values, key=lambda item: item[0])


def _validate_specification(
    specification: OptionsBacktestSpecification, data: OptionMarketData
) -> tuple[str, ...]:
    if not specification.start_date or not specification.end_date:
        raise OptionBacktestParameterError("start_date and end_date are required.")
    if _date(specification.start_date) > _date(specification.end_date):
        raise OptionBacktestParameterError("start_date must be before or equal to end_date.")
    if not math.isfinite(specification.starting_cash) or specification.starting_cash <= 0:
        raise OptionBacktestParameterError("starting_cash must be finite and greater than zero.")
    if specification.path not in {"worst", "best"}:
        raise OptionBacktestParameterError("path must be 'worst' or 'best'.")
    if specification.dte_min > specification.dte_max:
        raise OptionBacktestParameterError("dte_min must not exceed dte_max.")
    if specification.delta_min > specification.delta_max:
        raise OptionBacktestParameterError("delta_min must not exceed delta_max.")
    if specification.iv_min > specification.iv_max:
        raise OptionBacktestParameterError("iv_min must not exceed iv_max.")
    if any(
        value < 0.0
        for value in (
            specification.delta_min,
            specification.delta_max,
            specification.iv_min,
            specification.iv_max,
            specification.fee_per_leg,
        )
    ):
        raise OptionBacktestParameterError("Selection bounds and fees must not be negative.")
    if specification.selected_symbols:
        symbols = specification.selected_symbols
    else:
        symbols = tuple(sorted({contract.security_id for contract in data.contracts}))
    if not symbols:
        raise OptionBacktestParameterError(
            "symbols or watchlist must contain at least one Security."
        )
    if (
        specification.dataset_version_id
        and data.dataset_version_id
        and specification.dataset_version_id != data.dataset_version_id
    ):
        raise OptionBacktestError("OptionMarketData does not match the named Dataset Version.")
    for contract in data.contracts:
        if contract.right not in {"put", "call"} or contract.multiplier <= 0:
            raise OptionBacktestError(f"Invalid Option Contract '{contract.contract_id}'.")
        if contract.available_at is None:
            raise OptionBacktestError(
                "Historical option contracts require available_at eligibility timestamps."
            )
    for trade in data.option_trades:
        if trade.available_at is None:
            raise OptionBacktestError(
                "Historical option trades require available_at eligibility timestamps."
            )
    for bar in data.underlying_bars:
        if bar.available_at is None:
            raise OptionBacktestError(
                "Historical stock minute bars require available_at eligibility timestamps."
            )
    return tuple(symbols)


def _path_position(
    position: _OpenPosition, path: str, details: _PathPositionData
) -> SpreadPosition:
    data = details.data
    candidate = details.candidate
    all_values = details.all_values
    expiration = details.expiration
    total_credit = position.entry_credit
    if position.exit_value is not None:
        exit_value = position.exit_value
    elif position.trajectory:
        last_point = position.trajectory[-1]
        exit_value = last_point.spread_worst if path == "worst" else last_point.spread_best
    else:
        exit_value = 0.0
    full_loss = max(0.0, position.collateral - total_credit)
    pnl = (
        total_credit
        - exit_value * position.quantity * candidate.short_contract.multiplier
        - position.entry_fee
        - position.exit_fee
    )
    reliability_denominator = position.matched_minutes + position.missing_minutes
    reliability = (
        100.0 * position.matched_minutes / reliability_denominator
        if reliability_denominator
        else 100.0
    )
    first_day = _timestamp(position.entry_timestamp).date()
    last_day = _timestamp(position.exit_timestamp).date() if position.exit_timestamp else first_day
    days_held = max(0, (last_day - first_day).days)
    rom = pnl / full_loss if full_loss > EPS else 0.0
    annualized = (1.0 + rom) ** (365.0 / max(days_held, 1)) - 1.0 if rom > -1.0 else -1.0
    points = [
        TrajectoryPoint(_minute_text(minute), stock, worst, best, position.stop_level)
        for minute, stock, worst, best in all_values
    ]
    values_after = [
        worst if path == "worst" else best
        for minute, stock, worst, best in all_values
        if position.exit_timestamp
        and _timestamp(_minute_text(minute)) > _timestamp(position.exit_timestamp)
    ]
    counterfactual: CounterfactualOutcome | None = None
    if position.close_rule.startswith("Stop") and values_after:
        later_peak = max(values_after)
        later_low = min(values_after)
        if later_peak > exit_value + EPS:
            counterfactual = CounterfactualOutcome(
                "STOP_SAVED",
                round(
                    (later_peak - exit_value)
                    * position.quantity
                    * candidate.short_contract.multiplier,
                    4,
                ),
                "The spread became more expensive after the stop exit.",
            )
        elif later_low < position.entry_credit / position.quantity - EPS:
            counterfactual = CounterfactualOutcome(
                "WHIPSAWED",
                round(
                    (exit_value - later_low)
                    * position.quantity
                    * candidate.short_contract.multiplier,
                    4,
                ),
                "The spread recovered after the stop exit.",
            )
    if counterfactual is None and position.close_rule.startswith("Profit"):
        counterfactual = CounterfactualOutcome(
            "TARGET_ACHIEVED", 0.0, "The configured profit exit was reached."
        )
    return SpreadPosition(
        id=position.position_id,
        security_id=candidate.short_contract.security_id,
        short_strike=candidate.short_contract.strike,
        long_strike=candidate.long_contract.strike,
        width=candidate.width,
        expiration=expiration,
        entry_credit=round(total_credit, 4),
        margin_required=round(position.collateral, 4),
        full_possible_loss=round(full_loss, 4),
        return_on_margin_pct=round(rom * 100.0, 6),
        annualized_rom_pct=round(annualized * 100.0, 6),
        worst_net_pnl=round(pnl if path == "worst" else 0.0, 4),
        best_net_pnl=round(pnl if path == "best" else 0.0, 4),
        days_held=days_held,
        open_timestamp=position.entry_timestamp,
        open_rule=candidate.selection_reason,
        close_timestamp=position.exit_timestamp,
        close_rule=position.close_rule,
        status=(
            "Closed Stop Level"
            if position.close_rule.startswith("Stop")
            else "Closed Profit Target"
            if position.close_rule.startswith("Profit")
            else "Expired Worthless"
            if position.close_rule == "Expiration"
            else position.close_rule
        ),
        short_delta=round(candidate.short_delta, 8),
        implied_volatility=round(candidate.implied_volatility, 8),
        bid_ask_spread_drag=round(
            abs(candidate.short_trade_price - candidate.long_trade_price)
            * candidate.short_contract.multiplier,
            4,
        ),
        slippage_cost=0.0,
        execution_mode=path,
        reliability_pct=round(reliability, 4),
        missing_minutes_count=position.missing_minutes,
        stop_movements=tuple(position.stop_movements),
        greeks={
            "entry": position.entry_greeks,
            "mid": position.mid_greeks or position.last_greeks,
            "exit": position.last_greeks,
        },
        counterfactual=counterfactual,
        candles=tuple(
            PriceCandle(
                date=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in data.underlying_bars
            if bar.security_id == candidate.short_contract.security_id
            and _timestamp(bar.timestamp).date() >= first_day
            and (position.exit_timestamp is None or _timestamp(bar.timestamp).date() <= last_day)
        ),
        trajectory_points=tuple(points),
        quantity=position.quantity,
        entry_fee=round(position.entry_fee, 4),
        exit_fee=round(position.exit_fee, 4),
    )


def _earnings_exit_day(events: Sequence[object], security_id: str, minute: datetime) -> bool:
    """Return whether the day is the configured pre-earnings exit day."""
    for event in events:
        if not isinstance(event, EarningsEvent) or event.security_id != security_id:
            continue
        if event.available_at is None or _timestamp(event.available_at) > minute + timedelta(
            minutes=1
        ):
            continue
        event_date = _date(event.event_date)
        if event.timing == "after_close" and minute.date() == event_date:
            return True
        if event.timing == "before_open":
            exit_day = event_date - timedelta(days=1)
            while exit_day.weekday() >= 5:
                exit_day -= timedelta(days=1)
            if minute.date() == exit_day:
                return True
    return False


def _earnings_exit_due(events: Sequence[object], security_id: str, minute: datetime) -> bool:
    return _earnings_exit_day(events, security_id, minute) and minute.timetz().replace(
        tzinfo=None
    ) >= time(15, 30)


def _simulate_path(
    specification: OptionsBacktestSpecification,
    data: OptionMarketData,
    options: _SimulationOptions,
) -> _SimulationResult:
    symbols = options.symbols
    path = options.path
    ranges = _trade_ranges(data)
    stock = _stock_by_minute(data)
    first = _timestamp(specification.start_date + "T00:00:00-05:00")
    last = _timestamp(specification.end_date + "T23:59:59-05:00")
    minutes = sorted(
        minute
        for (symbol, minute) in stock
        if symbol in symbols
        and first <= minute <= last
        and time(9, 30) <= minute.timetz().replace(tzinfo=None) <= time(16, 0)
    )
    positions: list[SpreadPosition] = []
    blocked: list[BlockedCandidate] = []
    rejection_counts: dict[str, int] = {}
    open_positions: dict[str, _OpenPosition] = {}
    stopped_dates: set[tuple[str, str]] = set()
    equity_rows: list[dict[str, JsonValue]] = []
    warnings: list[str] = []

    def block_candidate(timestamp: str, security_id: str, rule: str, reason: str) -> None:
        if len(blocked) < 500:
            blocked.append(BlockedCandidate(timestamp, security_id, reason, rule))

    planned_entries = dict(options.entry_plan or {})
    actual_entries: dict[tuple[str, str], tuple[str, str, int]] = {}
    cash = specification.starting_cash
    locked_collateral = 0.0
    position_counter = 0
    previous_minute: datetime | None = None

    for minute in minutes:
        if previous_minute is not None:
            elapsed_days = max(0.0, (minute - previous_minute).total_seconds() / 86400.0)
            if specification.cash_interest_rate:
                cash += cash * specification.cash_interest_rate * elapsed_days / 365.0
        previous_minute = minute
        date_text = minute.date().isoformat()

        # Exit requests are intentionally filled at the next matching minute.
        for security_id, position in list(open_positions.items()):
            matching = (position.candidate.short_contract.contract_id, minute) in ranges and (
                position.candidate.long_contract.contract_id,
                minute,
            ) in ranges
            if not matching:
                if time(9, 30) <= minute.timetz().replace(tzinfo=None) <= time(16, 0):
                    position.missing_minutes += 1
                continue
            position.matched_minutes += 1
            worst, best = _spread_values(position.candidate, ranges, minute)
            stock_price = stock[(security_id, minute)].close
            chosen_value = worst if path == "worst" else best
            dte_years = max(
                (_date(position.candidate.short_contract.expiration) - minute.date()).days / 365.0,
                1 / 365.0,
            )
            short_range = ranges[(position.candidate.short_contract.contract_id, minute)]
            short_price = (short_range.low + short_range.high) / 2.0
            pricing = OptionPricingInputs(
                stock_price,
                position.candidate.short_contract.strike,
                dte_years,
                specification.risk_free_rate,
                specification.dividend_yield,
            )
            position.last_greeks = black_scholes_greeks(
                pricing, black_scholes_iv(short_price, pricing)
            )
            if position.mid_greeks is None and minute > _minute(position.entry_timestamp):
                position.mid_greeks = position.last_greeks
            position.trajectory.append(
                TrajectoryPoint(_minute_text(minute), stock_price, worst, best, position.stop_level)
            )
            if (
                position.pending_exit_reason
                and position.pending_exit_after is not None
                and minute > position.pending_exit_after
            ):
                position.exit_timestamp = _minute_text(minute)
                position.exit_value = chosen_value
                position.exit_fee = specification.fee_per_leg * 2.0 * position.quantity
                position.close_rule = position.pending_exit_reason
                cash -= (
                    chosen_value * position.quantity * position.candidate.short_contract.multiplier
                    + position.exit_fee
                )
                locked_collateral -= position.collateral
                positions.append(
                    _path_position(
                        position,
                        path,
                        _PathPositionData(
                            data,
                            position.candidate,
                            _position_values(data, position),
                            position.candidate.short_contract.expiration,
                            specification.fee_per_leg,
                        ),
                    )
                )
                del open_positions[security_id]
                continue
            if chosen_value >= position.stop_level - EPS:
                position.pending_exit_reason = "Stop Level"
                position.pending_exit_after = minute
                stopped_dates.add((security_id, date_text))
                continue
            credit_per_unit = (
                position.entry_credit
                / position.quantity
                / position.candidate.short_contract.multiplier
            )
            elapsed = (minute.date() - _timestamp(position.entry_timestamp).date()).days
            total_days = max(
                1,
                (
                    _date(position.candidate.short_contract.expiration)
                    - _timestamp(position.entry_timestamp).date()
                ).days,
            )
            remaining_fraction = max(0.0, 1.0 - elapsed / total_days)
            if chosen_value <= 0.5 * credit_per_unit and position.stop_level > credit_per_unit:
                position.stop_level = credit_per_unit
                position.stop_movements.append(
                    StopMovement(
                        _minute_text(minute), stock_price, credit_per_unit, "50% profit stop move"
                    )
                )
            if (
                chosen_value <= 0.25 * credit_per_unit
                and position.stop_level > 0.5 * credit_per_unit
            ):
                position.stop_level = 0.5 * credit_per_unit
                position.stop_movements.append(
                    StopMovement(
                        _minute_text(minute),
                        stock_price,
                        0.5 * credit_per_unit,
                        "75% profit stop move",
                    )
                )
            if (
                chosen_value <= 0.125 * credit_per_unit
                and position.stop_level > 0.25 * credit_per_unit
            ):
                position.stop_level = 0.25 * credit_per_unit
                position.stop_movements.append(
                    StopMovement(
                        _minute_text(minute),
                        stock_price,
                        0.25 * credit_per_unit,
                        "87.5% profit stop move",
                    )
                )
            if chosen_value <= 0.10 * credit_per_unit and remaining_fraction <= 0.25:
                position.pending_exit_reason = "Profit Target 90%"
                position.pending_exit_after = minute
            elif chosen_value <= 0.25 * credit_per_unit and remaining_fraction <= 0.5:
                position.pending_exit_reason = "Profit Target 75%"
                position.pending_exit_after = minute
            elif stock[(security_id, minute)].low <= position.candidate.short_contract.strike:
                position.pending_exit_reason = "Short Strike Breach"
                position.pending_exit_after = minute
            elif _earnings_exit_due(data.earnings, security_id, minute):
                position.pending_exit_reason = "Pre-earnings exit"
                position.pending_exit_after = minute
            elif minute.date() == (
                _date(position.candidate.short_contract.expiration) - timedelta(days=7)
            ) and minute.timetz().replace(tzinfo=None) >= time(15, 30):
                position.pending_exit_reason = "7-day expiration cutoff"
                position.pending_exit_after = minute
            elif minute.date() == _date(
                position.candidate.short_contract.expiration
            ) and minute.timetz().replace(tzinfo=None) >= time(15, 30):
                position.exit_timestamp = _minute_text(minute)
                position.exit_value = (
                    0.0
                    if stock_price > position.candidate.short_contract.strike
                    else position.candidate.width
                )
                position.close_rule = (
                    "Expiration" if position.exit_value == 0.0 else "Expiration ITM"
                )
                position.exit_fee = (
                    0.0
                    if position.exit_value == 0.0
                    else specification.fee_per_leg * 2.0 * position.quantity
                )
                cash -= (
                    position.exit_value
                    * position.quantity
                    * position.candidate.short_contract.multiplier
                    + position.exit_fee
                )
                locked_collateral -= position.collateral
                positions.append(
                    _path_position(
                        position,
                        path,
                        _PathPositionData(
                            data,
                            position.candidate,
                            _position_values(data, position),
                            position.candidate.short_contract.expiration,
                            specification.fee_per_leg,
                        ),
                    )
                )
                del open_positions[security_id]

        # Scan entries after managing existing positions.
        if time(10, 0) <= minute.timetz().replace(tzinfo=None) <= time(15, 30):
            for security_id in symbols:
                if security_id in open_positions:
                    continue
                if (security_id, date_text) in stopped_dates:
                    rejection_counts["same_day_stop_cooldown"] = (
                        rejection_counts.get("same_day_stop_cooldown", 0) + 1
                    )
                    block_candidate(
                        _minute_text(minute),
                        security_id,
                        "same_day_stop_cooldown",
                        "A Security cannot re-enter on the day of a Stop Level exit.",
                    )
                    continue
                if _earnings_exit_day(data.earnings, security_id, minute):
                    rejection_counts["pre_earnings_exit_day"] = (
                        rejection_counts.get("pre_earnings_exit_day", 0) + 1
                    )
                    block_candidate(
                        _minute_text(minute),
                        security_id,
                        "pre_earnings_exit_day",
                        "Entry is blocked on the required pre-earnings exit day.",
                    )
                    continue
                planned = planned_entries.get((security_id, date_text))
                if planned:
                    candidate = _fixed_candidate(
                        replace(
                            specification,
                            automatic_selection=False,
                            fixed_short_contract_id=planned[0],
                            fixed_long_contract_id=planned[1],
                        ),
                        data,
                        minute,
                    )
                else:
                    candidate = (
                        _fixed_candidate(specification, data, minute)
                        if not specification.automatic_selection
                        else select_put_credit_spread(
                            specification, market_data=data, security_id=security_id, at=minute
                        )
                    )
                if candidate is None:
                    key = "no_eligible_spread"
                    rejection_counts[key] = rejection_counts.get(key, 0) + 1
                    if len(blocked) < 500:
                        blocked.append(
                            BlockedCandidate(
                                _minute_text(minute),
                                security_id,
                                (
                                    "No spread met the DTE, delta, IV, volume, trend, or "
                                    "matching-minute rules."
                                ),
                                key,
                            )
                        )
                    continue
                if len(open_positions) >= specification.max_open_securities:
                    rejection_counts["max_open_securities"] = (
                        rejection_counts.get("max_open_securities", 0) + 1
                    )
                    block_candidate(
                        _minute_text(minute),
                        security_id,
                        "max_open_securities",
                        "The Portfolio already has the maximum number of open Securities.",
                    )
                    continue
                if any(
                    _similarity(data, security_id, other, minute) > specification.similarity_limit
                    for other in open_positions
                ):
                    rejection_counts["similarity_limit"] = (
                        rejection_counts.get("similarity_limit", 0) + 1
                    )
                    block_candidate(
                        _minute_text(minute),
                        security_id,
                        "similarity_limit",
                        "The Security is too similar to an existing open position.",
                    )
                    continue
                credit_unit = _entry_credit(candidate, ranges, minute, path)
                if credit_unit <= EPS:
                    rejection_counts["nonpositive_entry_credit"] = (
                        rejection_counts.get("nonpositive_entry_credit", 0) + 1
                    )
                    block_candidate(
                        _minute_text(minute),
                        security_id,
                        "nonpositive_entry_credit",
                        "The worst supported Entry Credit is not positive.",
                    )
                    continue
                multiplier = candidate.short_contract.multiplier
                risk_per_spread = max(0.0, candidate.width - credit_unit) * multiplier
                if risk_per_spread <= EPS:
                    continue
                open_value = sum(
                    (entry.spread_worst if path == "worst" else entry.spread_best)
                    * open_position.quantity
                    * open_position.candidate.short_contract.multiplier
                    for open_position in open_positions.values()
                    for entry in [open_position.trajectory[-1]]
                )
                portfolio_value = cash - open_value
                open_risk = sum(
                    max(
                        0.0,
                        open_position.candidate.width
                        - open_position.entry_credit
                        / open_position.quantity
                        / open_position.candidate.short_contract.multiplier,
                    )
                    * open_position.quantity
                    * open_position.candidate.short_contract.multiplier
                    for open_position in open_positions.values()
                )
                qty_by_position = math.floor(
                    max(0.0, portfolio_value * specification.risk_per_position) / risk_per_spread
                )
                qty_by_portfolio = math.floor(
                    max(0.0, portfolio_value * specification.max_open_risk - open_risk)
                    / risk_per_spread
                )
                quantity = min(qty_by_position, qty_by_portfolio)
                if planned:
                    quantity = planned[2]
                collateral = candidate.width * multiplier * quantity
                if quantity < 1 or cash - locked_collateral < collateral:
                    rejection_counts["collateral_limit"] = (
                        rejection_counts.get("collateral_limit", 0) + 1
                    )
                    block_candidate(
                        _minute_text(minute),
                        security_id,
                        "collateral_limit",
                        "The Portfolio cannot fund the required spread collateral or "
                        "Full Possible Loss.",
                    )
                    continue
                position_counter += 1
                entry_credit_total = credit_unit * multiplier * quantity
                entry_fee = specification.fee_per_leg * 2.0 * quantity
                cash += entry_credit_total - entry_fee
                locked_collateral += collateral
                years = max(
                    (_date(candidate.short_contract.expiration) - minute.date()).days / 365.0,
                    1 / 365.0,
                )
                stock_price = stock[(security_id, minute)].close
                entry_iv = candidate.implied_volatility
                position = _OpenPosition(
                    position_id=f"spread-{position_counter}",
                    candidate=candidate,
                    quantity=quantity,
                    entry_timestamp=_minute_text(minute),
                    entry_credit=entry_credit_total,
                    entry_fee=entry_fee,
                    collateral=collateral,
                    stop_level=2.0 * credit_unit,
                    entry_greeks=black_scholes_greeks(
                        OptionPricingInputs(
                            stock_price,
                            candidate.short_contract.strike,
                            years,
                            specification.risk_free_rate,
                            specification.dividend_yield,
                        ),
                        entry_iv,
                    ),
                )
                position.matched_minutes += 1
                worst, best = _spread_values(candidate, ranges, minute)
                position.trajectory.append(
                    TrajectoryPoint(
                        _minute_text(minute), stock_price, worst, best, position.stop_level
                    )
                )
                open_positions[security_id] = position
                actual_entries[(security_id, date_text)] = (
                    candidate.short_contract.contract_id,
                    candidate.long_contract.contract_id,
                    quantity,
                )

        open_value = sum(
            (entry.spread_worst if path == "worst" else entry.spread_best)
            * pos.quantity
            * pos.candidate.short_contract.multiplier
            for pos in open_positions.values()
            for entry in [pos.trajectory[-1]]
        )
        equity_rows.append(
            {"timestamp": _minute_text(minute), "equity": round(cash - open_value, 4)}
        )

    for security_id, position in open_positions.items():
        warnings.append(f"{position.position_id} remained open at the end of the requested period.")
        positions.append(
            _path_position(
                position,
                path,
                _PathPositionData(
                    data,
                    position.candidate,
                    _position_values(data, position),
                    position.candidate.short_contract.expiration,
                    specification.fee_per_leg,
                ),
            )
        )
    if any(item.missing_minutes_count > 5 for item in positions):
        warnings.append(
            "One or more positions have more than five missing matching minutes and are unreliable."
        )
    return _SimulationResult(
        tuple(positions), blocked, rejection_counts, equity_rows, warnings, actual_entries
    )


def _max_drawdown(rows: Sequence[dict[str, JsonValue]]) -> float:
    peak = 0.0
    worst = 0.0
    for row in rows:
        value = float(row.get("equity", 0.0))
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def run_option_backtest(
    specification: OptionsBacktestSpecification, *, market_data: OptionMarketData
) -> OptionsBacktestResult:
    """Replay one Put Credit Spread strategy on best and worst supported paths."""
    symbols = _validate_specification(specification, market_data)
    worst_result = _simulate_path(specification, market_data, _SimulationOptions(symbols, "worst"))
    best_result = _simulate_path(
        specification,
        market_data,
        _SimulationOptions(symbols, "best", worst_result.entry_plan),
    )
    worst_positions = worst_result.positions
    blocked = worst_result.blocked
    rejections = worst_result.rejection_counts
    worst_curve = worst_result.equity_curve
    warnings = worst_result.warnings
    best_positions = best_result.positions
    best_rejections = best_result.rejection_counts
    best_curve = best_result.equity_curve
    best_warnings = best_result.warnings
    by_id_best = {position.id: position for position in best_positions}
    merged: list[SpreadPosition] = []
    for worst in worst_positions:
        best = by_id_best.get(worst.id)
        merged.append(
            replace(
                worst,
                best_net_pnl=best.best_net_pnl if best else worst.worst_net_pnl,
            )
        )
    worst_pnl = sum(position.worst_net_pnl for position in merged)
    best_pnl = sum(position.best_net_pnl for position in merged)
    closed = [position for position in merged if position.close_timestamp]
    winning = sum(position.worst_net_pnl > 0 for position in closed)
    full_risk = sum(position.full_possible_loss for position in merged)
    reliability_values = [position.reliability_pct for position in merged]
    summary = OptionBacktestSummary(
        worst_net_pnl=round(worst_pnl, 4),
        best_net_pnl=round(best_pnl, 4),
        portfolio_rom_pct=round((worst_pnl / full_risk * 100.0) if full_risk else 0.0, 6),
        win_rate_pct=round((winning / len(closed) * 100.0) if closed else 0.0, 6),
        winning_trades=winning,
        losing_trades=sum(position.worst_net_pnl <= 0 for position in closed),
        total_trades=len(closed),
        max_drawdown_pct=round(_max_drawdown(worst_curve) * 100.0, 6),
        total_slippage_drag=round(
            sum(abs(position.best_net_pnl - position.worst_net_pnl) for position in merged), 4
        ),
        overall_reliability_pct=round(
            statistics.mean(reliability_values) if reliability_values else 100.0, 6
        ),
        rejection_counts={
            key: rejections.get(key, 0) + best_rejections.get(key, 0)
            for key in set(rejections) | set(best_rejections)
        },
    )
    all_warnings = tuple(
        dict.fromkeys(
            warnings
            + best_warnings
            + (
                [
                    (
                        "The options result is inconclusive because more than 15% of "
                        "closed positions are unreliable."
                    )
                ]
                if closed
                and sum(position.missing_minutes_count > 5 for position in merged) / len(closed)
                > 0.15
                else []
            )
        )
    )
    manifest: dict[str, JsonValue] = {
        "kind": "options_backtest",
        "provider": market_data.provider,
        "input_dataset_versions": {
            "options_market_data": market_data.dataset_version_id
            or specification.dataset_version_id
        },
        "strategy_revision": specification.strategy_revision,
        "execution": {
            "main_path": "worst",
            "comparison_path": "best",
            "fee_per_leg": specification.fee_per_leg,
            "minute_trade_range": True,
        },
        "rules": {
            "dte": [specification.dte_min, specification.dte_max],
            "delta": [specification.delta_min, specification.delta_max],
            "iv": [specification.iv_min, specification.iv_max],
            "widths": [specification.preferred_width, specification.fallback_width],
        },
        "rejection_counts": summary.rejection_counts,
        "reliability": {
            "overall_percent": summary.overall_reliability_pct,
            "unreliable_gap_minutes": 5,
        },
    }
    return OptionsBacktestResult(
        specification,
        summary,
        tuple(merged),
        tuple(blocked),
        all_warnings,
        manifest,
        tuple(best_positions),
        tuple(worst_curve),
        tuple(best_curve),
    )
