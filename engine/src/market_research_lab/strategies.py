"""Deterministic Strategy evaluation that emits target weights, never orders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .indicators import IndicatorPoint, IndicatorSeries, calculate_indicator
from .json_types import JsonValue
from .predictive_models import is_naive_benchmark_comparison_complete


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


class CombinedPredictiveModelParams(BaseModel):
    """Validated boundary parameters for the combined predictive model Strategy."""

    threshold: float = Field(default=0.0002, ge=0.0, le=0.1)
    momentum_weight: float = Field(default=0.5, ge=-2.0, le=2.0)
    potts_weight: float = Field(default=0.5, ge=-2.0, le=2.0)
    momentum_period: int = Field(default=20, ge=1, le=500)
    lookback_window: int = Field(default=60, ge=10, le=500)
    threshold_return: float = Field(default=0.05, gt=0.0, le=0.5)
    q_states: int = Field(default=4, ge=2, le=16)
    mode: Literal["long_short", "long_flat"] = "long_short"


def evaluate_combined_predictive_model(
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Evaluate combined predictive models over an eligible Market View."""
    try:
        config = CombinedPredictiveModelParams.model_validate(parameters)
    except Exception as error:
        raise StrategyParameterValidationError(str(error)) from error

    prices = list(market_view.prices)
    session_dates = list(market_view.session_dates)
    if len(session_dates) != len(prices):
        raise StrategyParameterValidationError(
            f"session_dates length ({len(session_dates)}) must match prices length ({len(prices)})."
        )

    required_history = max(config.lookback_window, config.momentum_period) + 1
    if len(prices) < required_history:
        return StrategyEvaluation(
            strategy_name="combined_predictive_model",
            parameters={
                "threshold": config.threshold,
                "momentum_weight": config.momentum_weight,
                "potts_weight": config.potts_weight,
                "momentum_period": config.momentum_period,
                "lookback_window": config.lookback_window,
                "threshold_return": config.threshold_return,
                "q_states": config.q_states,
                "mode": config.mode,
            },
            decision_time=decision_time,
            targets=(
                StrategyTarget(
                    security_id=market_view.security_id,
                    weight=0.0,
                    decision_time=decision_time,
                    rationale="Insufficient history for combined predictive model features; target flat position.",
                    indicator_state="warmup",
                ),
            ),
            latest_session_date=session_dates[-1] if session_dates else None,
            warnings=("Warm-up window: insufficient observations.",),
        )

    idx = len(prices) - 1
    mom_price = prices[idx - config.momentum_period]
    mom_return = (prices[idx] / mom_price - 1.0) if mom_price > 0 else 0.0

    window_closes = prices[idx - config.lookback_window : idx + 1]
    window_returns: list[float] = []
    for i in range(1, len(window_closes)):
        if window_closes[i - 1] > 0:
            window_returns.append(window_closes[i] / window_closes[i - 1] - 1.0)
        else:
            window_returns.append(0.0)

    tau_loss = float(config.lookback_window)
    tau_gain = float(config.lookback_window)

    running_peak = window_closes[0]
    peak_idx = 0
    for w_idx in range(1, len(window_closes)):
        price = window_closes[w_idx]
        if price > running_peak:
            running_peak = price
            peak_idx = w_idx
        if running_peak > 0:
            drop = (price - running_peak) / running_peak
            if drop <= -config.threshold_return:
                dur = float(w_idx - peak_idx)
                if dur > 0 and dur < tau_loss:
                    tau_loss = dur

    running_trough = window_closes[0]
    trough_idx = 0
    for w_idx in range(1, len(window_closes)):
        price = window_closes[w_idx]
        if price < running_trough:
            running_trough = price
            trough_idx = w_idx
        if running_trough > 0:
            gain = (price - running_trough) / running_trough
            if gain >= config.threshold_return:
                dur = float(w_idx - trough_idx)
                if dur > 0 and dur < tau_gain:
                    tau_gain = dur

    denom_tau = tau_gain + tau_loss
    asymmetry_ratio = (tau_loss - tau_gain) / denom_tau if denom_tau > 1e-12 else 0.0

    n_obs = len(window_returns)
    sorted_rets = sorted(window_returns)
    bin_counts = [0] * config.q_states
    for r in window_returns:
        rank = 0
        for s_r in sorted_rets:
            if r > s_r:
                rank += 1
        bin_idx = min(config.q_states - 1, int((rank / n_obs) * config.q_states))
        bin_counts[bin_idx] += 1

    n_max = max(bin_counts)
    expected_n = n_obs / config.q_states
    denom_m = n_obs - expected_n
    order_param = max(0.0, (n_max - expected_n) / denom_m) if denom_m > 1e-12 else 0.0

    potts_score = asymmetry_ratio * (1.0 + order_param)
    combined_score = config.momentum_weight * mom_return + config.potts_weight * potts_score

    if config.mode == "long_short":
        if combined_score > config.threshold:
            weight = 1.0
            state = "bullish_combined"
            rationale = (
                f"Combined forecast ({combined_score:.6f}) exceeds threshold {config.threshold}; "
                "target long position at 100% allocation."
            )
        elif combined_score < -config.threshold:
            weight = -1.0
            state = "bearish_combined"
            rationale = (
                f"Combined forecast ({combined_score:.6f}) is below threshold -{config.threshold}; "
                "target short position at -100% allocation."
            )
        else:
            weight = 0.0
            state = "neutral_combined"
            rationale = (
                f"Combined forecast ({combined_score:.6f}) is within threshold band; "
                "target flat position."
            )
    else:
        if combined_score > config.threshold:
            weight = 1.0
            state = "bullish_combined"
            rationale = (
                f"Combined forecast ({combined_score:.6f}) exceeds threshold {config.threshold}; "
                "target long position at 100% allocation."
            )
        else:
            weight = 0.0
            state = "neutral_combined"
            rationale = (
                f"Combined forecast ({combined_score:.6f}) is below threshold; "
                "target flat position."
            )

    return StrategyEvaluation(
        strategy_name="combined_predictive_model",
        parameters={
            "threshold": config.threshold,
            "momentum_weight": config.momentum_weight,
            "potts_weight": config.potts_weight,
            "momentum_period": config.momentum_period,
            "lookback_window": config.lookback_window,
            "threshold_return": config.threshold_return,
            "q_states": config.q_states,
            "mode": config.mode,
        },
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
        latest_session_date=session_dates[-1],
    )


def validate_model_eligibility_for_strategy(
    model_data: Mapping[str, JsonValue],
    *,
    require_persisted_run: bool = False,
) -> None:
    """Enforce MOD-009 before a Predictive Model can feed a Strategy.

    The check accepts a saved model result or, for non-persisted diagnostics,
    its evaluation object. It requires complete out-of-sample provenance and
    finite comparable metrics. A caller-supplied boolean is not sufficient.
    """
    if require_persisted_run and not (
        isinstance(model_data.get("run_id"), str)
        and bool(str(model_data["run_id"]).strip())
    ):
        raise StrategyEvaluationError(
            "A persisted Predictive Model Run reference is required before a "
            "Strategy can use model output (MOD-009)."
        )

    result = model_data.get("result")
    source = result if isinstance(result, dict) else model_data
    evaluation_value = source.get("evaluation")
    evaluation = evaluation_value if isinstance(evaluation_value, dict) else source

    benchmark = evaluation.get("benchmark")
    if not isinstance(benchmark, dict) or not is_naive_benchmark_comparison_complete(
        benchmark
    ):
        raise StrategyEvaluationError(
            "Predictive Model cannot feed an enabled Strategy until its naive "
            "out-of-sample benchmark comparison is complete (MOD-009)."
        )

    if evaluation.get("is_eligible_for_strategy") is not True:
        reason = evaluation.get(
            "eligibility_reason", "benchmark comparison eligibility is not verified"
        )
        raise StrategyEvaluationError(
            "Predictive Model is not eligible to feed a Strategy: "
            f"{reason} (MOD-009)."
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
    "combined_predictive_model": StrategyMetadata(
        name="combined_predictive_model",
        display_name="Combined Predictive Model",
        description=(
            "Combines signals from momentum return regression and Potts gain-loss "
            "asymmetry to produce directional target weights (MOD-008)."
        ),
        parameters=[
            StrategyParameter(
                name="threshold",
                param_type="float",
                default=0.0002,
                description="Forecast return threshold to trigger position changes",
                min_value=0.0,
                max_value=0.1,
            ),
            StrategyParameter(
                name="momentum_weight",
                param_type="float",
                default=0.5,
                description="Weight assigned to trailing momentum regression forecast",
                min_value=-2.0,
                max_value=2.0,
            ),
            StrategyParameter(
                name="potts_weight",
                param_type="float",
                default=0.5,
                description="Weight assigned to Potts gain-loss asymmetry forecast",
                min_value=-2.0,
                max_value=2.0,
            ),
            StrategyParameter(
                name="momentum_period",
                param_type="int",
                default=20,
                description="Momentum lookback period in daily bars",
                min_value=1,
                max_value=500,
            ),
            StrategyParameter(
                name="lookback_window",
                param_type="int",
                default=60,
                description="Potts lookback window in daily bars",
                min_value=10,
                max_value=500,
            ),
            StrategyParameter(
                name="threshold_return",
                param_type="float",
                default=0.05,
                description="Potts return threshold for gain/loss waiting times",
                min_value=0.01,
                max_value=0.5,
            ),
            StrategyParameter(
                name="q_states",
                param_type="int",
                default=4,
                description="Number of Potts spin states",
                min_value=2,
                max_value=16,
            ),
            StrategyParameter(
                name="mode",
                param_type="str",
                default="long_short",
                description="Strategy position mode ('long_short' or 'long_flat')",
                options=["long_short", "long_flat"],
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
    if name == "combined_predictive_model":
        return evaluate_combined_predictive_model(
            market_view, parameters, decision_time=decision_time
        )
    raise StrategyEvaluationError(
        f"Unknown Strategy '{name}'. Available: {list(STRATEGY_REGISTRY.keys())}"
    )
