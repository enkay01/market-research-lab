from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_research_lab.market_data import EarningsEvent
from market_research_lab.option_position_lifecycle import (
    ExitReason,
    LifecycleState,
    OpenPositionConditions,
    earnings_exit_day,
    evaluate_open_position,
    open_position_transition,
)

NEW_YORK = ZoneInfo("America/New_York")
MINUTE = datetime(2024, 1, 2, 15, 30, tzinfo=NEW_YORK)
BASE_CONDITIONS = OpenPositionConditions(
    minute=MINUTE,
    chosen_value=1.0,
    credit_per_unit=1.0,
    stop_level=2.0,
    remaining_fraction=1.0,
    underlying_price=101.0,
    underlying_low=101.0,
    short_strike=95.0,
    expiration=date(2024, 2, 20),
    width=5.0,
    earnings_exit_due=False,
)


def test_entry_transition_opens_the_position():
    transition = open_position_transition(MINUTE)

    assert transition.from_state is LifecycleState.ENTRY
    assert transition.to_state is LifecycleState.OPEN
    assert transition.reason is ExitReason.OPEN_POSITION


def test_trailing_stop_records_each_level_crossed_in_one_minute():
    decision = evaluate_open_position(replace(BASE_CONDITIONS, chosen_value=0.1))

    assert [item.stop_level for item in decision.stop_movements] == [1.0, 0.5, 0.25]
    assert [item.reason for item in decision.stop_movements] == [
        ExitReason.PROFIT_STOP_50,
        ExitReason.PROFIT_STOP_75,
        ExitReason.PROFIT_STOP_87_5,
    ]


def test_stop_loss_has_priority_over_other_exit_rules():
    conditions = replace(
        BASE_CONDITIONS,
        chosen_value=2.0,
        remaining_fraction=0.2,
        underlying_low=90.0,
    )

    decision = evaluate_open_position(conditions)

    assert decision.exit_transition is not None
    assert decision.exit_transition.reason is ExitReason.STOP_LEVEL
    assert decision.exit_transition.to_state is LifecycleState.EXIT_PENDING


@pytest.mark.parametrize(
    ("conditions", "reason"),
    [
        (
            replace(BASE_CONDITIONS, chosen_value=0.1, remaining_fraction=0.25),
            ExitReason.PROFIT_TARGET_90,
        ),
        (
            replace(BASE_CONDITIONS, chosen_value=0.25, remaining_fraction=0.5),
            ExitReason.PROFIT_TARGET_75,
        ),
        (replace(BASE_CONDITIONS, underlying_low=95.0), ExitReason.SHORT_STRIKE_BREACH),
        (replace(BASE_CONDITIONS, earnings_exit_due=True), ExitReason.PRE_EARNINGS_EXIT),
        (
            replace(
                BASE_CONDITIONS,
                minute=datetime(2024, 2, 13, 15, 30, tzinfo=NEW_YORK),
            ),
            ExitReason.SEVEN_DAY_EXPIRATION_CUTOFF,
        ),
    ],
)
def test_open_position_rules_create_pending_exit_transitions(conditions, reason):
    decision = evaluate_open_position(conditions)

    assert decision.exit_transition is not None
    assert decision.exit_transition.reason is reason
    assert decision.exit_transition.to_state is LifecycleState.EXIT_PENDING


@pytest.mark.parametrize(
    ("underlying_price", "reason", "exit_value"),
    [
        (96.0, ExitReason.EXPIRATION, 0.0),
        (95.0, ExitReason.EXPIRATION_ITM, 5.0),
    ],
)
def test_expiration_settlement_uses_the_full_supported_spread_width(
    underlying_price, reason, exit_value
):
    expiration_minute = datetime(2024, 2, 20, 15, 30, tzinfo=NEW_YORK)
    conditions = replace(
        BASE_CONDITIONS,
        minute=expiration_minute,
        expiration=expiration_minute.date(),
        underlying_price=underlying_price,
        underlying_low=96.0,
    )

    decision = evaluate_open_position(conditions)

    assert decision.exit_transition is not None
    assert decision.exit_transition.reason is reason
    assert decision.exit_transition.exit_value == exit_value
    assert decision.exit_transition.to_state is LifecycleState.CLOSED


def test_before_open_earnings_uses_previous_weekday_and_known_events_only():
    known = EarningsEvent("SPY", "2024-01-08", "before_open", available_at="2024-01-05T14:00:00Z")
    future = EarningsEvent("SPY", "2024-01-08", "before_open", available_at="2024-01-08T14:00:00Z")
    friday = datetime(2024, 1, 5, 15, 30, tzinfo=NEW_YORK)

    assert earnings_exit_day((known,), "SPY", friday)
    assert not earnings_exit_day((future,), "SPY", friday)
