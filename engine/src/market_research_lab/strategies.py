"""Deterministic Strategy evaluation that emits target weights, never orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .indicators import IndicatorSeries, calculate_indicator
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
class StrategyEvaluation:
    """Time-stamped desired weights and rationale produced by a Strategy."""

    strategy_name: str
    parameters: dict[str, JsonValue]
    decision_time: str
    targets: tuple[StrategyTarget, ...]
    indicator_name: str | None = None
    latest_session_date: str | None = None
    warnings: tuple[str, ...] = ()


class LongFlatMovingAverageParams(BaseModel):
    """Validated boundary parameters for the long/flat moving-average Strategy."""

    fast_period: int = Field(default=20, ge=1, le=250)
    slow_period: int = Field(default=50, ge=2, le=500)
    ma_type: Literal["sma", "ema"] = "sma"


_BULLISH_STATES = {"bullish_cross", "bullish_above"}
_BEARISH_STATES = {"bearish_cross", "bearish_below"}


def _long_flat_weight(indicator_state: str | None, is_warmup: bool) -> tuple[float, str | None]:
    """Map the latest eligible moving-average state to a long or flat weight."""
    if is_warmup or indicator_state in (None, "warmup", "neutral"):
        return 0.0, indicator_state or "warmup"
    if indicator_state in _BULLISH_STATES:
        return 1.0, indicator_state
    if indicator_state in _BEARISH_STATES:
        return 0.0, indicator_state
    return 0.0, indicator_state


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
    config = LongFlatMovingAverageParams.model_validate(parameters)

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

    state_value = latest.values.get("state")
    indicator_state = state_value if isinstance(state_value, str) else None
    weight, state = _long_flat_weight(indicator_state, latest.is_warmup)

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
                weight=weight,
                decision_time=decision_time,
                rationale=_rationale(weight, state),
                indicator_state=state,
            ),
        ),
        indicator_name="moving_average_crossover",
        latest_session_date=latest.session_date,
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

    raise StrategyEvaluationError(
        f"Unknown Strategy '{name}'. Available: {list(STRATEGY_REGISTRY.keys())}"
    )
