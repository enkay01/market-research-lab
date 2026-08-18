"""Deterministic Strategy evaluation that emits target weights, never orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .indicators import IndicatorPoint, IndicatorSeries, calculate_indicator
from .json_types import JsonValue


class StrategyParameterValidationError(ValueError):
    """Raised when a Strategy parameter fails its validation constraints."""


class StrategyEvaluationError(Exception):
    """Raised when a Strategy cannot be evaluated or is unknown."""


@dataclass(frozen=True)
class StrategyParameter:
    """Typed specification for a Strategy configuration parameter."""

    name: str
    param_type: Literal["int", "float", "str", "bool"]
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: list[str] | None = None


@dataclass(frozen=True)
class StrategyMetadata:
    """Descriptor and parameter contract for a Strategy."""

    name: str
    display_name: str
    description: str
    parameters: list[StrategyParameter]
    outputs: list[str]


@dataclass(frozen=True)
class MarketView:
    """Read-only view of eligible observations bounded to one decision time."""

    security_id: str
    session_dates: tuple[str, ...]
    prices: tuple[float, ...]


@dataclass(frozen=True)
class StrategyTarget:
    """Desired target weight for one Security; never an order or a fill."""

    security_id: str
    weight: float
    decision_time: str
    rationale: str
    indicator_state: str | None = None


@dataclass(frozen=True)
class LongFlatDecision:
    """Long or flat target weight with the indicator state that produced it."""

    weight: float
    indicator_state: str | None


@dataclass(frozen=True)
class StrategyEvaluation:
    """Time-stamped desired weights and rationale produced by a Strategy."""

    strategy_name: str
    parameters: dict[str, JsonValue]
    decision_time: str
    targets: tuple[StrategyTarget, ...]
    indicator_name: str | None = None
    latest_session_date: str | None = None
    warnings: tuple[str, ...] = ()


class MovingAverageStrategyParams(BaseModel):
    """Validated boundary parameters for the moving-average crossover Strategies."""

    fast_period: int = Field(default=20, ge=1, le=250)
    slow_period: int = Field(default=50, ge=2, le=500)
    ma_type: Literal["sma", "ema"] = "sma"


# Backward-compatible alias
LongFlatMovingAverageParams = MovingAverageStrategyParams


@dataclass(frozen=True)
class MovingAverageExecutionPoint:
    """Calculated configuration and latest observation for moving average evaluation."""

    config: MovingAverageStrategyParams
    latest_point: IndicatorPoint


def _calculate_ma_crossover_latest(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
) -> MovingAverageExecutionPoint:
    """Validate parameters and compute the latest moving-average crossover point."""
    config = MovingAverageStrategyParams.model_validate(parameters)

    if config.fast_period >= config.slow_period:
        raise StrategyParameterValidationError(
            f"fast_period must be strictly less than slow_period "
            f"(got fast={config.fast_period}, slow={config.slow_period})."
        )

    if len(market_view.session_dates) != len(market_view.prices):
        raise StrategyParameterValidationError(
            f"session_dates length ({len(market_view.session_dates)}) must match "
            f"prices length ({len(market_view.prices)})."
        )

    series: IndicatorSeries = calculate_indicator(
        name="moving_average_crossover",
        session_dates=list(market_view.session_dates),
        prices=list(market_view.prices),
        parameters={
            "fast_period": config.fast_period,
            "slow_period": config.slow_period,
            "ma_type": config.ma_type,
        },
    )

    latest = series.points[-1] if series.points else None
    if latest is None:
        raise StrategyParameterValidationError(
            "The Market View must contain at least one eligible observation."
        )

    return MovingAverageExecutionPoint(config=config, latest_point=latest)


_BULLISH_STATES = {"bullish_cross", "bullish_above"}
_BEARISH_STATES = {"bearish_cross", "bearish_below"}


def _long_flat_decision(
    indicator_state: str | None, *, is_warmup: bool
) -> LongFlatDecision:
    """Map the latest eligible moving-average state to a long or flat decision."""
    if is_warmup or indicator_state in (None, "warmup", "neutral"):
        return LongFlatDecision(weight=0.0, indicator_state=indicator_state or "warmup")
    if indicator_state in _BULLISH_STATES:
        return LongFlatDecision(weight=1.0, indicator_state=indicator_state)
    return LongFlatDecision(weight=0.0, indicator_state=indicator_state)


def _rationale(weight: float, state: str | None) -> str:
    if weight > 0:
        return (
            f"Moving-average trend is bullish ({state}); target a long position "
            "at 100% of the single-Security allocation."
        )
    return (
        f"Moving-average trend is {state or 'neutral'}; target a flat position "
        "with 0% allocation."
    )


def evaluate_long_flat_moving_average(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Evaluate the long/flat moving-average Strategy over an eligible Market View."""
    exec_pt = _calculate_ma_crossover_latest(market_view, parameters)
    config = exec_pt.config
    latest = exec_pt.latest_point

    state_value = latest.values.get("state")
    indicator_state = state_value if isinstance(state_value, str) else None
    decision = _long_flat_decision(indicator_state, is_warmup=latest.is_warmup)

    return StrategyEvaluation(
        strategy_name="long_flat_moving_average",
        parameters={
            "fast_period": config.fast_period,
            "slow_period": config.slow_period,
            "ma_type": config.ma_type,
        },
        decision_time=decision_time,
        targets=(
            StrategyTarget(
                security_id=market_view.security_id,
                weight=decision.weight,
                decision_time=decision_time,
                rationale=_rationale(decision.weight, decision.indicator_state),
                indicator_state=decision.indicator_state,
            ),
        ),
        indicator_name="moving_average_crossover",
        latest_session_date=latest.session_date,
    )


def _long_short_decision(
    indicator_state: str | None, *, is_warmup: bool
) -> LongFlatDecision:
    """Map moving-average state to long (+1.0), short (-1.0), or flat (0.0)."""
    if is_warmup or indicator_state in (None, "warmup", "neutral"):
        return LongFlatDecision(weight=0.0, indicator_state=indicator_state or "warmup")
    if indicator_state in _BULLISH_STATES:
        return LongFlatDecision(weight=1.0, indicator_state=indicator_state)
    if indicator_state in _BEARISH_STATES:
        return LongFlatDecision(weight=-1.0, indicator_state=indicator_state)
    return LongFlatDecision(weight=0.0, indicator_state=indicator_state)


def _long_short_rationale(weight: float, state: str | None) -> str:
    if weight > 0:
        return (
            f"Moving-average trend is bullish ({state}); target a long position "
            "at 100% allocation."
        )
    if weight < 0:
        return (
            f"Moving-average trend is bearish ({state}); target a short position "
            "at -100% allocation."
        )
    return (
        f"Moving-average trend is {state or 'neutral'}; target a flat position "
        "with 0% allocation."
    )


def evaluate_long_short_moving_average(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Evaluate the long/short moving-average Strategy over an eligible Market View."""
    exec_pt = _calculate_ma_crossover_latest(market_view, parameters)
    config = exec_pt.config
    latest = exec_pt.latest_point

    state_value = latest.values.get("state")
    indicator_state = state_value if isinstance(state_value, str) else None
    decision = _long_short_decision(indicator_state, is_warmup=latest.is_warmup)

    return StrategyEvaluation(
        strategy_name="long_short_moving_average",
        parameters={
            "fast_period": config.fast_period,
            "slow_period": config.slow_period,
            "ma_type": config.ma_type,
        },
        decision_time=decision_time,
        targets=(
            StrategyTarget(
                security_id=market_view.security_id,
                weight=decision.weight,
                decision_time=decision_time,
                rationale=_long_short_rationale(decision.weight, decision.indicator_state),
                indicator_state=decision.indicator_state,
            ),
        ),
        indicator_name="moving_average_crossover",
        latest_session_date=latest.session_date,
    )


class PredictiveReturnThresholdParams(BaseModel):
    """Validated parameters for the Predictive Return Threshold Strategy."""

    model_revision: str = Field(default="")
    threshold: float = Field(default=0.0, ge=-0.5, le=0.5)
    predicted_return: float = Field(default=0.001)
    benchmark_comparison_completed: bool = Field(default=True)


def validate_model_eligibility_for_strategy(model_data: dict[str, JsonValue]) -> None:
    """Enforce MOD-009: Predictive Models cannot feed Strategies without benchmark comparison."""
    evaluation = model_data.get("evaluation")
    if isinstance(evaluation, dict):
        benchmark = evaluation.get("benchmark")
        if not benchmark or not isinstance(benchmark, dict) or not benchmark.get("completed"):
            raise StrategyEvaluationError(
                "Predictive Model cannot feed an enabled Strategy until its naive "
                "benchmark comparison is complete (MOD-009)."
            )
        if evaluation.get("is_eligible_for_strategy") is False:
            raise StrategyEvaluationError(
                "Predictive Model is not eligible to feed a Strategy: "
                f"{evaluation.get('eligibility_reason', 'benchmark comparison failed')}"
            )
        return

    # Check root-level benchmark_comparison or evaluation flags
    benchmark = model_data.get("benchmark_comparison") or model_data.get("benchmark")
    if not benchmark or not isinstance(benchmark, dict) or not benchmark.get("completed"):
        raise StrategyEvaluationError(
            "Predictive Model cannot feed an enabled Strategy until its naive "
            "benchmark comparison is complete (MOD-009)."
        )


def evaluate_predictive_return_threshold(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Evaluate a Predictive Model-driven Strategy enforcing the MOD-009 guardrail."""
    try:
        config = PredictiveReturnThresholdParams.model_validate(parameters)
    except Exception as error:
        raise StrategyParameterValidationError(str(error)) from error

    if not config.benchmark_comparison_completed:
        raise StrategyEvaluationError(
            "Predictive Model cannot feed an enabled Strategy until its naive "
            "benchmark comparison is complete (MOD-009)."
        )

    weight = 1.0 if config.predicted_return >= config.threshold else 0.0
    if weight > 0:
        rationale = (
            f"Predicted return ({config.predicted_return:+.4f}) >= threshold "
            f"({config.threshold:+.4f}); target a long position at 100% allocation. "
            "Out-of-sample naive benchmark comparison verified."
        )
    else:
        rationale = (
            f"Predicted return ({config.predicted_return:+.4f}) < threshold "
            f"({config.threshold:+.4f}); target a flat position with 0% allocation."
        )

    latest_date = market_view.session_dates[-1] if market_view.session_dates else None

    return StrategyEvaluation(
        strategy_name="predictive_return_threshold",
        parameters={
            "model_revision": config.model_revision,
            "threshold": config.threshold,
            "predicted_return": config.predicted_return,
            "benchmark_comparison_completed": config.benchmark_comparison_completed,
        },
        decision_time=decision_time,
        targets=(
            StrategyTarget(
                security_id=market_view.security_id,
                weight=weight,
                decision_time=decision_time,
                rationale=rationale,
                indicator_state="model_forecast",
            ),
        ),
        indicator_name="predictive_model",
        latest_session_date=latest_date,
    )


STRATEGY_REGISTRY: dict[str, StrategyMetadata] = {
    "long_flat_moving_average": StrategyMetadata(
        name="long_flat_moving_average",
        display_name="Long/Flat Moving Average",
        description=(
            "Long when the fast moving average is above the slow moving average, "
            "flat when it is below or during the warm-up window."
        ),
        parameters=[
            StrategyParameter(
                name="fast_period",
                param_type="int",
                default=20,
                description="Fast moving-average lookback in daily bars",
                min_value=1,
                max_value=250,
            ),
            StrategyParameter(
                name="slow_period",
                param_type="int",
                default=50,
                description="Slow moving-average lookback in daily bars",
                min_value=2,
                max_value=500,
            ),
            StrategyParameter(
                name="ma_type",
                param_type="str",
                default="sma",
                description="Moving-average calculation method ('sma' or 'ema')",
                options=["sma", "ema"],
            ),
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
    "long_short_moving_average": StrategyMetadata(
        name="long_short_moving_average",
        display_name="Long/Short Moving Average",
        description=(
            "Long (+100%) when the fast moving average is above the slow moving average, "
            "short (-100%) when below, and flat (0%) during the warm-up window."
        ),
        parameters=[
            StrategyParameter(
                name="fast_period",
                param_type="int",
                default=20,
                description="Fast moving-average lookback in daily bars",
                min_value=1,
                max_value=250,
            ),
            StrategyParameter(
                name="slow_period",
                param_type="int",
                default=50,
                description="Slow moving-average lookback in daily bars",
                min_value=2,
                max_value=500,
            ),
            StrategyParameter(
                name="ma_type",
                param_type="str",
                default="sma",
                description="Moving-average calculation method ('sma' or 'ema')",
                options=["sma", "ema"],
            ),
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
    "predictive_return_threshold": StrategyMetadata(
        name="predictive_return_threshold",
        display_name="Predictive Return Threshold",
        description=(
            "Long (+100%) when predicted next-session return exceeds a threshold, "
            "flat (0%) otherwise. Requires a Predictive Model Run with completed "
            "naive benchmark comparison (MOD-009)."
        ),
        parameters=[
            StrategyParameter(
                name="threshold",
                param_type="float",
                default=0.0,
                description="Minimum predicted return to trigger a long position",
                min_value=-0.5,
                max_value=0.5,
            ),
            StrategyParameter(
                name="predicted_return",
                param_type="float",
                default=0.001,
                description="Latest predicted next-session return from the Predictive Model",
                min_value=-1.0,
                max_value=1.0,
            ),
            StrategyParameter(
                name="benchmark_comparison_completed",
                param_type="bool",
                default=True,
                description="Whether the Predictive Model has completed naive benchmark comparison",
            ),
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
}


def list_strategies() -> list[StrategyMetadata]:
    """Return every registered Strategy metadata descriptor."""
    return list(STRATEGY_REGISTRY.values())


def get_strategy_spec(name: str) -> StrategyMetadata:
    """Retrieve the metadata descriptor for a named Strategy."""
    spec = STRATEGY_REGISTRY.get(name)
    if spec is None:
        raise StrategyEvaluationError(f"Unknown Strategy '{name}'.")
    return spec


def evaluate_strategy(
    name: str,
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Dispatch and evaluate a named Strategy over an eligible Market View."""
    if name == "long_flat_moving_average":
        return evaluate_long_flat_moving_average(
            market_view, parameters, decision_time=decision_time
        )
    if name == "long_short_moving_average":
        return evaluate_long_short_moving_average(
            market_view, parameters, decision_time=decision_time
        )
    if name == "predictive_return_threshold":
        return evaluate_predictive_return_threshold(
            market_view, parameters, decision_time=decision_time
        )

    raise StrategyEvaluationError(
        f"Unknown Strategy '{name}'. Available: {list(STRATEGY_REGISTRY.keys())}"
    )
