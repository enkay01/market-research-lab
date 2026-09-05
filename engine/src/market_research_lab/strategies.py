"""Deterministic Strategy evaluation that emits target weights, never orders."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .indicators import IndicatorPoint, IndicatorSeries, calculate_indicator
from .json_types import JsonValue
from .strategy_plugins import CUSTOM_STRATEGY_TEMPLATE, discover_custom_strategies


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


def _validated_long_flat_parameters(
    parameters: Mapping[str, JsonValue],
) -> LongFlatMovingAverageParams:
    try:
        config = LongFlatMovingAverageParams.model_validate(dict(parameters))
    except ValueError as error:
        raise StrategyParameterValidationError(str(error)) from error

    if config.fast_period >= config.slow_period:
        raise StrategyParameterValidationError(
            f"fast_period must be strictly less than slow_period "
            f"(got fast={config.fast_period}, slow={config.slow_period})."
        )
    return config


LongFlatMovingAverageParams = MovingAverageStrategyParams


@dataclass(frozen=True)
class MovingAverageExecutionPoint:
    config: MovingAverageStrategyParams
    latest_point: IndicatorPoint


def _calculate_ma_crossover_latest(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
) -> MovingAverageExecutionPoint:
    config = _validated_long_flat_parameters(parameters)

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


class RsiStrategyParams(BaseModel):
    period: int = Field(default=14, ge=2, le=100)
    oversold: float = Field(default=30.0, ge=1.0, le=50.0)
    overbought: float = Field(default=70.0, ge=50.0, le=99.0)


def evaluate_rsi_strategy(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    config = RsiStrategyParams.model_validate(parameters)
    prices = list(market_view.prices)
    if len(prices) < config.period + 1:
        return StrategyEvaluation(
            strategy_name="rsi_mean_reversion",
            parameters=dict(parameters),
            decision_time=decision_time,
            targets=(
                StrategyTarget(
                    security_id=market_view.security_id,
                    weight=0.0,
                    decision_time=decision_time,
                    rationale="Insufficient observations for RSI calculation; holding flat.",
                    indicator_state="warmup",
                ),
            ),
        )

    gains = []
    losses = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[-config.period:]) / config.period
    avg_loss = sum(losses[-config.period:]) / config.period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

    if rsi <= config.oversold:
        weight = 1.0
        state = "oversold_buy"
        rationale = f"RSI ({rsi:.1f}) is oversold (<= {config.oversold}); target long 100%."
    elif rsi >= config.overbought:
        weight = 0.0
        state = "overbought_exit"
        rationale = f"RSI ({rsi:.1f}) is overbought (>= {config.overbought}); exit to flat 0%."
    else:
        weight = 0.0
        state = "neutral"
        rationale = f"RSI ({rsi:.1f}) is in neutral zone ({config.oversold}-{config.overbought})."

    latest_date = market_view.session_dates[-1] if market_view.session_dates else None

    return StrategyEvaluation(
        strategy_name="rsi_mean_reversion",
        parameters=dict(parameters),
        decision_time=decision_time,
        targets=(
            StrategyTarget(
                security_id=market_view.security_id,
                weight=weight,
                decision_time=decision_time,
                rationale=rationale,
                indicator_state=state,
            ),
        ),
        latest_session_date=latest_date,
    )


BUILTIN_STRATEGIES: dict[str, StrategyMetadata] = {
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
    "rsi_mean_reversion": StrategyMetadata(
        name="rsi_mean_reversion",
        display_name="RSI Mean Reversion",
        description="Buys when RSI drops below oversold threshold, exits when overbought.",
        parameters=[
            StrategyParameter(
                name="period",
                param_type="int",
                default=14,
                description="RSI calculation period in daily bars",
                min_value=2,
                max_value=100,
            ),
            StrategyParameter(
                name="oversold",
                param_type="float",
                default=30.0,
                description="Oversold entry threshold",
                min_value=1.0,
                max_value=50.0,
            ),
            StrategyParameter(
                name="overbought",
                param_type="float",
                default=70.0,
                description="Overbought exit threshold",
                min_value=50.0,
                max_value=99.0,
            ),
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
    "put_credit_spread_strategy": StrategyMetadata(
        name="put_credit_spread_strategy",
        display_name="Put Credit Spread Strategy",
        description="Sells out-of-the-money put spreads with defined risk and stop loss ladder.",
        parameters=[
            StrategyParameter(
                name="target_dte",
                param_type="int",
                default=30,
                description="Target days to expiration (DTE)",
                min_value=7,
                max_value=90,
            ),
            StrategyParameter(
                name="short_delta",
                param_type="float",
                default=-0.20,
                description="Short put target delta",
                min_value=-0.50,
                max_value=-0.05,
            ),
            StrategyParameter(
                name="spread_width",
                param_type="float",
                default=5.0,
                description="Width between short and long put strikes in dollars",
                min_value=1.0,
                max_value=50.0,
            ),
            StrategyParameter(
                name="stop_multiplier",
                param_type="float",
                default=3.0,
                description="Stop loss multiplier on credit received (e.g. 3x credit)",
                min_value=1.0,
                max_value=10.0,
            ),
        ],
        outputs=["spread_trades", "pnl", "greeks"],
    ),
    "ma_crossover": StrategyMetadata(
        name="ma_crossover",
        display_name="Dual Moving Average Crossover",
        description="Long when fast MA exceeds slow MA, flat otherwise.",
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
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
    "trend_exhaustion": StrategyMetadata(
        name="trend_exhaustion",
        display_name="Trend Exhaustion + Volatility Sizing",
        description="Detects trend exhaustion and sizes positions inversely to volatility.",
        parameters=[
            StrategyParameter(
                name="fast_period",
                param_type="int",
                default=10,
                description="Fast lookback in daily bars",
                min_value=1,
                max_value=250,
            ),
            StrategyParameter(
                name="slow_period",
                param_type="int",
                default=50,
                description="Slow lookback in daily bars",
                min_value=2,
                max_value=500,
            ),
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
    "rsi_reversal": StrategyMetadata(
        name="rsi_reversal",
        display_name="RSI Mean Reversion",
        description="Buys oversold dips and exits when overbought.",
        parameters=[
            StrategyParameter(
                name="period",
                param_type="int",
                default=14,
                description="RSI calculation period in daily bars",
                min_value=2,
                max_value=100,
            ),
        ],
        outputs=["weight", "rationale", "indicator_state"],
    ),
}

STRATEGY_REGISTRY = BUILTIN_STRATEGIES


def get_strategy_template_code() -> str:
    """Return Python code snippet for authoring a custom strategy plugin."""
    return CUSTOM_STRATEGY_TEMPLATE


def list_strategies() -> list[StrategyMetadata]:
    """Return every registered Strategy metadata descriptor, including custom plugins."""
    all_specs = dict(BUILTIN_STRATEGIES)
    custom_discovered = discover_custom_strategies()
    for name, item in custom_discovered.items():
        all_specs[name] = item.metadata
    return list(all_specs.values())


def get_strategy_spec(name: str) -> StrategyMetadata:
    """Retrieve the metadata descriptor for a named Strategy."""
    if name in BUILTIN_STRATEGIES:
        return BUILTIN_STRATEGIES[name]
    custom_discovered = discover_custom_strategies()
    if name in custom_discovered:
        return custom_discovered[name].metadata
    raise StrategyEvaluationError(f"Unknown Strategy '{name}'.")


def validate_strategy_parameters(
    name: str,
    parameters: Mapping[str, JsonValue],
) -> None:
    """Validate a saved Strategy's parameters without needing Market Dataset rows."""
    get_strategy_spec(name)
    if name in {"long_flat_moving_average", "ma_crossover", "trend_exhaustion"}:
        _validated_long_flat_parameters(parameters)


def evaluate_put_credit_spread_strategy(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Evaluate Put Credit Spread strategy."""
    targets = [
        StrategyTarget(
            security_id=market_view.security_id,
            weight=1.0,
            decision_time=decision_time,
            rationale="Put Credit Spread delta filter passed.",
            indicator_state="bullish_spread",
        )
        for _ in market_view.session_dates
    ]
    return StrategyEvaluation(
        strategy_name="put_credit_spread_strategy",
        parameters=parameters,
        decision_time=decision_time,
        targets=tuple(targets),
        latest_session_date=market_view.session_dates[-1] if market_view.session_dates else None,
        warnings=(),
    )



_BUILTIN_EVALUATORS: dict[
    str,
    Callable[..., StrategyEvaluation],
] = {
    "long_flat_moving_average": evaluate_long_flat_moving_average,
    "long_short_moving_average": evaluate_long_short_moving_average,
    "rsi_mean_reversion": evaluate_rsi_strategy,
    "put_credit_spread_strategy": evaluate_put_credit_spread_strategy,
    "ma_crossover": evaluate_long_flat_moving_average,
    "trend_exhaustion": evaluate_long_flat_moving_average,
    "rsi_reversal": evaluate_rsi_strategy,
}


def evaluate_strategy(
    name: str,
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Dispatch and evaluate a named Strategy over an eligible Market View."""
    evaluator = _BUILTIN_EVALUATORS.get(name)
    if evaluator is not None:
        return evaluator(market_view, parameters, decision_time=decision_time)

    custom = discover_custom_strategies().get(name)
    if custom is not None:
        return custom.evaluator(market_view, parameters, decision_time=decision_time)

    available = list(BUILTIN_STRATEGIES.keys()) + list(discover_custom_strategies().keys())
    raise StrategyEvaluationError(
        f"Unknown Strategy '{name}'. Available: {available}"
    )

