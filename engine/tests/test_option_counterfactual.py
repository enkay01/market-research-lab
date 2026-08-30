from market_research_lab.option_counterfactual import (
    CounterfactualInputs,
    analyze_post_exit,
)
from market_research_lab.option_position_lifecycle import ExitReason


def _stop_inputs(values_after: tuple[float, ...]) -> CounterfactualInputs:
    return CounterfactualInputs(
        close_rule=ExitReason.STOP_LEVEL,
        exit_value=3.0,
        values_after=values_after,
        entry_credit=100.0,
        quantity=1,
        multiplier=100.0,
    )


def test_recovery_at_entry_credit_boundary_is_whipsaw():
    outcome = analyze_post_exit(_stop_inputs((1.0,)))

    assert outcome is not None
    assert outcome.outcome == "WHIPSAWED"
    assert outcome.avoided_loss_or_missed_gain == 200.0


def test_whipsaw_takes_priority_when_later_values_also_exceed_the_exit():
    outcome = analyze_post_exit(_stop_inputs((4.0, 0.5)))

    assert outcome is not None
    assert outcome.outcome == "WHIPSAWED"


def test_more_expensive_spread_records_stop_saved_outcome():
    outcome = analyze_post_exit(_stop_inputs((3.00000002,)))

    assert outcome is not None
    assert outcome.outcome == "STOP_SAVED"
    assert outcome.avoided_loss_or_missed_gain == 0.0


def test_profit_exit_has_target_achieved_outcome_without_later_values():
    inputs = CounterfactualInputs(
        close_rule=ExitReason.PROFIT_TARGET_75,
        exit_value=0.25,
        values_after=(),
        entry_credit=100.0,
        quantity=1,
        multiplier=100.0,
    )

    outcome = analyze_post_exit(inputs)

    assert outcome is not None
    assert outcome.outcome == "TARGET_ACHIEVED"


def test_open_position_has_no_counterfactual_outcome():
    inputs = CounterfactualInputs(
        close_rule=ExitReason.OPEN_POSITION,
        exit_value=1.0,
        values_after=(2.0,),
        entry_credit=100.0,
        quantity=1,
        multiplier=100.0,
    )

    assert analyze_post_exit(inputs) is None
