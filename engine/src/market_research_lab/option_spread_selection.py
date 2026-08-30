"""Point-in-time Put Credit Spread candidate selection."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import NamedTuple, Sequence

from .market_data import DailyBar, OptionContract, OptionMarketData, UnderlyingMinuteBar
from .option_pricing import OptionPricingInputs, black_scholes_greeks, black_scholes_iv
from .option_time import NEW_YORK, option_minute, parse_option_timestamp


@dataclass(frozen=True)
class SelectionRules:
    dte_min: int
    dte_max: int
    delta_min: float
    delta_max: float
    target_delta: float
    iv_min: float
    iv_max: float
    previous_day_volume_min: float
    preferred_width: float
    fallback_width: float
    risk_free_rate: float
    dividend_yield: float
    automatic_selection: bool


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
class MinuteRange:
    low: float
    high: float
    last: float


class SpreadValues(NamedTuple):
    worst: float
    best: float


class _CandidateOrder(NamedTuple):
    width_rank: int
    delta_distance: float
    credit: float
    expiration: str


def minute_trade_ranges(
    data: OptionMarketData, *, as_of: datetime | None = None
) -> dict[tuple[str, datetime], MinuteRange]:
    """Build eligible low, high, and last trade values for each contract minute."""
    ranges: dict[tuple[str, datetime], MinuteRange] = {}
    for trade in data.option_trades:
        event_time = parse_option_timestamp(trade.timestamp)
        eligibility_cutoff = as_of or event_time + timedelta(minutes=1)
        if (
            trade.available_at is None
            or parse_option_timestamp(trade.available_at) > eligibility_cutoff
        ):
            continue
        key = (trade.contract_id, event_time.replace(second=0, microsecond=0))
        prior = ranges.get(key)
        if prior is None:
            ranges[key] = MinuteRange(trade.price, trade.price, trade.price)
        else:
            ranges[key] = MinuteRange(
                min(prior.low, trade.price), max(prior.high, trade.price), trade.price
            )
    return ranges


def underlying_bars_by_minute(
    data: OptionMarketData,
) -> dict[tuple[str, datetime], UnderlyingMinuteBar]:
    """Return underlying bars available no later than the end of their minute."""
    result: dict[tuple[str, datetime], UnderlyingMinuteBar] = {}
    for bar in data.underlying_bars:
        bar_minute = option_minute(bar.timestamp)
        eligibility_cutoff = bar_minute + timedelta(minutes=1)
        if (
            bar.available_at is None
            or parse_option_timestamp(bar.available_at) > eligibility_cutoff
        ):
            continue
        result[(bar.security_id, bar_minute)] = bar
    return result


def previous_day_volume(data: OptionMarketData, security_id: str, when: datetime) -> float:
    """Sum the latest prior session's option volume known at ``when``."""
    contract_ids = {item.contract_id for item in data.contracts if item.security_id == security_id}
    eligible_dates = sorted(
        {
            parse_option_timestamp(trade.timestamp).date()
            for trade in data.option_trades
            if trade.contract_id in contract_ids
            and parse_option_timestamp(trade.timestamp).date() < when.date()
            and trade.available_at is not None
            and parse_option_timestamp(trade.available_at) <= when
        }
    )
    if not eligible_dates:
        return 0.0
    previous = eligible_dates[-1]
    return sum(
        max(0.0, trade.size)
        for trade in data.option_trades
        if trade.contract_id in contract_ids
        and parse_option_timestamp(trade.timestamp).date() == previous
        and trade.available_at is not None
        and parse_option_timestamp(trade.available_at) <= when
    )


def sma_trend_passes(daily_bars: Sequence[DailyBar], security_id: str, when: datetime) -> bool:
    """Apply the completed-bar 20, 50, and 200-day trend rule."""
    closes = [
        bar.close
        for bar in daily_bars
        if bar.security_id == security_id
        and bar.session_date < when.date().isoformat()
        and bar.available_at is not None
        and parse_option_timestamp(bar.available_at) <= when
    ]
    if len(closes) < 200:
        return False
    ma20 = statistics.mean(closes[-20:])
    ma50 = statistics.mean(closes[-50:])
    ma200 = statistics.mean(closes[-200:])
    return ma20 > ma50 and ma50 > ma200 and closes[-1] > ma200


def _underlying_price(data: OptionMarketData, security_id: str, minute: datetime) -> float | None:
    bar = underlying_bars_by_minute(data).get((security_id, minute))
    return bar.close if bar else None


def pullback_passes(data: OptionMarketData, security_id: str, when: datetime) -> bool:
    """Apply the 200-SMA touch and two-minute confirmation rule."""
    bars = [
        bar
        for (symbol, minute), bar in sorted(underlying_bars_by_minute(data).items())
        if symbol == security_id and minute <= when
    ]
    closes = [bar.close for bar in bars]
    daily = [
        bar.close
        for bar in data.daily_bars
        if bar.security_id == security_id
        and bar.session_date < when.date().isoformat()
        and bar.available_at is not None
        and parse_option_timestamp(bar.available_at) <= when
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


def _contract_is_eligible(contract: OptionContract, when: datetime) -> bool:
    if contract.available_at is not None and parse_option_timestamp(contract.available_at) > when:
        return False
    return contract.inactivated_at is None or parse_option_timestamp(contract.inactivated_at) > when


def _candidate_order(candidate: SpreadCandidate, rules: SelectionRules) -> _CandidateOrder:
    return _CandidateOrder(
        width_rank=(0 if math.isclose(candidate.width, rules.preferred_width, abs_tol=1e-8) else 1),
        delta_distance=abs(abs(candidate.short_delta) - rules.target_delta),
        credit=candidate.short_trade_price - candidate.long_trade_price,
        expiration=candidate.short_contract.expiration,
    )


def select_put_credit_spread(
    rules: SelectionRules,
    *,
    market_data: OptionMarketData,
    security_id: str,
    at: str | datetime,
) -> SpreadCandidate | None:
    """Select the closest eligible short Delta and an allowed lower strike."""
    when = parse_option_timestamp(at) if isinstance(at, str) else at.astimezone(NEW_YORK)
    if rules.automatic_selection and not sma_trend_passes(
        market_data.daily_bars, security_id, when
    ):
        return None
    if rules.automatic_selection and not pullback_passes(market_data, security_id, when):
        return None
    if (
        rules.automatic_selection
        and previous_day_volume(market_data, security_id, when) <= rules.previous_day_volume_min
    ):
        return None

    ranges = minute_trade_ranges(market_data, as_of=when + timedelta(minutes=1))
    minute = when.replace(second=0, microsecond=0)
    underlying = _underlying_price(market_data, security_id, minute)
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
        expiration = date.fromisoformat(short.expiration)
        dte = (expiration - when.date()).days
        if not rules.dte_min <= dte <= rules.dte_max:
            continue
        short_range = ranges.get((short.contract_id, minute))
        if short_range is None:
            continue
        short_price = (short_range.low + short_range.high) / 2.0
        pricing = OptionPricingInputs(
            underlying,
            short.strike,
            max(dte / 365.0, 1 / 365.0),
            rules.risk_free_rate,
            rules.dividend_yield,
        )
        iv = black_scholes_iv(short_price, pricing)
        greeks = black_scholes_greeks(pricing, iv)
        if not rules.delta_min <= abs(greeks.delta) <= rules.delta_max:
            continue
        if not rules.iv_min <= iv <= rules.iv_max:
            continue
        for width in (rules.preferred_width, rules.fallback_width):
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
            long_range = ranges.get((long.contract_id, minute))
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
                    selection_reason=(f"{dte} DTE, delta {abs(greeks.delta):.4f}, width {width:g}"),
                )
            )
            break
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: _candidate_order(candidate, rules))
