"""Pure Put Credit Spread position transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from .market_data import EarningsEvent

NEW_YORK = ZoneInfo("America/New_York")
EPS = 1e-9


class LifecycleState(Enum):
    ENTRY = "entry"
    OPEN = "open"
    EXIT_PENDING = "exit_pending"
    CLOSED = "closed"


class ExitReason(str, Enum):
    OPEN_POSITION = "Open Position"
    STOP_LEVEL = "Stop Level"
    PROFIT_STOP_50 = "50% profit stop move"
    PROFIT_STOP_75 = "75% profit stop move"
    PROFIT_STOP_87_5 = "87.5% profit stop move"
    PROFIT_TARGET_90 = "Profit Target 90%"
    PROFIT_TARGET_75 = "Profit Target 75%"
    SHORT_STRIKE_BREACH = "Short Strike Breach"
    PRE_EARNINGS_EXIT = "Pre-earnings exit"
    SEVEN_DAY_EXPIRATION_CUTOFF = "7-day expiration cutoff"
    EXPIRATION = "Expiration"
    EXPIRATION_ITM = "Expiration ITM"


@dataclass(frozen=True)
class PositionTransition:
    from_state: LifecycleState
    to_state: LifecycleState
    reason: ExitReason
    timestamp: datetime
    stop_level: float | None = None
    exit_value: float | None = None


@dataclass(frozen=True)
class OpenPositionConditions:
    minute: datetime
    chosen_value: float
    credit_per_unit: float
    stop_level: float
    remaining_fraction: float
    underlying_price: float
    underlying_low: float
    short_strike: float
    expiration: date
    width: float
    earnings_exit_due: bool


@dataclass(frozen=True)
class LifecycleDecision:
    stop_level: float
    stop_movements: tuple[PositionTransition, ...] = ()
    exit_transition: PositionTransition | None = None


def open_position_transition(minute: datetime) -> PositionTransition:
    return PositionTransition(
        LifecycleState.ENTRY,
        LifecycleState.OPEN,
        ExitReason.OPEN_POSITION,
        minute,
    )


def _stop_movement(minute: datetime, reason: ExitReason, stop_level: float) -> PositionTransition:
    return PositionTransition(
        LifecycleState.OPEN,
        LifecycleState.OPEN,
        reason,
        minute,
        stop_level=stop_level,
    )


def _pending_exit(minute: datetime, reason: ExitReason) -> PositionTransition:
    return PositionTransition(
        LifecycleState.OPEN,
        LifecycleState.EXIT_PENDING,
        reason,
        minute,
    )


def evaluate_open_position(conditions: OpenPositionConditions) -> LifecycleDecision:
    """Apply one minute of lifecycle rules in replay priority order."""
    if conditions.chosen_value >= conditions.stop_level - EPS:
        return LifecycleDecision(
            conditions.stop_level,
            exit_transition=_pending_exit(conditions.minute, ExitReason.STOP_LEVEL),
        )

    stop_level = conditions.stop_level
    movements: list[PositionTransition] = []
    if (
        conditions.chosen_value <= 0.5 * conditions.credit_per_unit
        and stop_level > conditions.credit_per_unit
    ):
        stop_level = conditions.credit_per_unit
        movements.append(_stop_movement(conditions.minute, ExitReason.PROFIT_STOP_50, stop_level))
    if (
        conditions.chosen_value <= 0.25 * conditions.credit_per_unit
        and stop_level > 0.5 * conditions.credit_per_unit
    ):
        stop_level = 0.5 * conditions.credit_per_unit
        movements.append(_stop_movement(conditions.minute, ExitReason.PROFIT_STOP_75, stop_level))
    if (
        conditions.chosen_value <= 0.125 * conditions.credit_per_unit
        and stop_level > 0.25 * conditions.credit_per_unit
    ):
        stop_level = 0.25 * conditions.credit_per_unit
        movements.append(_stop_movement(conditions.minute, ExitReason.PROFIT_STOP_87_5, stop_level))

    reason: ExitReason | None = None
    if (
        conditions.chosen_value <= 0.10 * conditions.credit_per_unit
        and conditions.remaining_fraction <= 0.25
    ):
        reason = ExitReason.PROFIT_TARGET_90
    elif (
        conditions.chosen_value <= 0.25 * conditions.credit_per_unit
        and conditions.remaining_fraction <= 0.5
    ):
        reason = ExitReason.PROFIT_TARGET_75
    elif conditions.underlying_low <= conditions.short_strike:
        reason = ExitReason.SHORT_STRIKE_BREACH
    elif conditions.earnings_exit_due:
        reason = ExitReason.PRE_EARNINGS_EXIT
    elif conditions.minute.date() == conditions.expiration - timedelta(
        days=7
    ) and conditions.minute.timetz().replace(tzinfo=None) >= time(15, 30):
        reason = ExitReason.SEVEN_DAY_EXPIRATION_CUTOFF

    transition = _pending_exit(conditions.minute, reason) if reason else None
    if (
        transition is None
        and conditions.minute.date() == conditions.expiration
        and conditions.minute.timetz().replace(tzinfo=None) >= time(15, 30)
    ):
        exit_value = (
            0.0 if conditions.underlying_price > conditions.short_strike else conditions.width
        )
        expiration_reason = (
            ExitReason.EXPIRATION if exit_value == 0.0 else ExitReason.EXPIRATION_ITM
        )
        transition = PositionTransition(
            LifecycleState.OPEN,
            LifecycleState.CLOSED,
            expiration_reason,
            conditions.minute,
            exit_value=exit_value,
        )
    return LifecycleDecision(stop_level, tuple(movements), transition)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=NEW_YORK)
    return parsed.astimezone(NEW_YORK)


def earnings_exit_day(
    events: tuple[EarningsEvent, ...], security_id: str, minute: datetime
) -> bool:
    """Return whether known earnings facts require an exit on this date."""
    for event in events:
        if event.security_id != security_id:
            continue
        if event.available_at is None or _timestamp(event.available_at) > minute + timedelta(
            minutes=1
        ):
            continue
        event_date = date.fromisoformat(event.event_date)
        if event.timing == "after_close" and minute.date() == event_date:
            return True
        if event.timing == "before_open":
            exit_day = event_date - timedelta(days=1)
            while exit_day.weekday() >= 5:
                exit_day -= timedelta(days=1)
            if minute.date() == exit_day:
                return True
    return False


def earnings_exit_due(
    events: tuple[EarningsEvent, ...], security_id: str, minute: datetime
) -> bool:
    return earnings_exit_day(events, security_id, minute) and minute.timetz().replace(
        tzinfo=None
    ) >= time(15, 30)
