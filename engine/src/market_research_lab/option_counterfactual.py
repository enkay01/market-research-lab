"""Post-exit outcome analysis for Put Credit Spreads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .option_position_lifecycle import ExitReason

EPS = 1e-9


@dataclass(frozen=True)
class CounterfactualOutcome:
    outcome: Literal["STOP_SAVED", "TARGET_ACHIEVED", "WHIPSAWED", "NOT_APPLICABLE"]
    avoided_loss_or_missed_gain: float
    explanation: str


@dataclass(frozen=True)
class CounterfactualInputs:
    close_rule: ExitReason
    exit_value: float
    values_after: tuple[float, ...]
    entry_credit: float
    quantity: int
    multiplier: float


def analyze_post_exit(inputs: CounterfactualInputs) -> CounterfactualOutcome | None:
    """Classify the supported Spread Values observed after an exit."""
    if inputs.close_rule in {
        ExitReason.PROFIT_TARGET_90,
        ExitReason.PROFIT_TARGET_75,
    }:
        return CounterfactualOutcome(
            "TARGET_ACHIEVED",
            0.0,
            "The configured profit exit was reached.",
        )
    if inputs.close_rule is not ExitReason.STOP_LEVEL or not inputs.values_after:
        return None
    if inputs.quantity <= 0 or inputs.multiplier <= 0.0:
        return None

    later_peak = max(inputs.values_after)
    later_low = min(inputs.values_after)
    credit_per_unit = inputs.entry_credit / inputs.quantity / inputs.multiplier
    if later_low <= credit_per_unit + EPS:
        return CounterfactualOutcome(
            "WHIPSAWED",
            round(
                (inputs.exit_value - later_low) * inputs.quantity * inputs.multiplier,
                4,
            ),
            "The spread recovered after the stop exit.",
        )
    if later_peak > inputs.exit_value + EPS:
        return CounterfactualOutcome(
            "STOP_SAVED",
            round(
                (later_peak - inputs.exit_value) * inputs.quantity * inputs.multiplier,
                4,
            ),
            "The spread became more expensive after the stop exit.",
        )
    return None
