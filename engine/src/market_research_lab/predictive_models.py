"""Typed, deterministic Predictive Model definitions and execution seams."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import model_evaluation as _evaluation_types
from .json_types import JsonValue
from .market_data import DailyBar
from .model_evaluation import PredictiveModelCalculationError

NaiveBenchmarkEvaluation = _evaluation_types.NaiveBenchmarkEvaluation
PredictiveModelCalculation = _evaluation_types.PredictiveModelCalculation
PredictiveModelEvaluation = _evaluation_types.PredictiveModelEvaluation
PredictiveModelFold = _evaluation_types.PredictiveModelFold
PredictiveModelPeriodMetrics = _evaluation_types.PredictiveModelPeriodMetrics
PredictiveModelSplit = _evaluation_types.PredictiveModelSplit


class PredictiveModelError(ValueError):
    """Base error for Predictive Model discovery, validation, and calculation."""


class PredictiveModelNotFoundError(PredictiveModelError):
    """Raised when a requested Predictive Model is not registered."""


class PredictiveModelParameterError(PredictiveModelError):
    """Raised when a Predictive Model parameter is invalid."""


class PredictiveModelDataError(PredictiveModelError):
    """Raised when the requested Dataset Version cannot provide model data."""


SplitName = Literal["training", "validation", "test"]
EvaluationMode = Literal["holdout", "expanding", "rolling"]
NaiveBenchmarkName = Literal["zero_return", "historical_mean", "persistence"]
SampleScope = Literal["in_sample", "validation", "out_of_sample"]
NaiveBenchmarkPrediction = tuple[str, str | None, float]


NaiveBenchmarkPredictor = Callable[[str, Sequence[float], Mapping[str, float]], float]

_MOMENTUM_MODEL_ASSUMPTIONS = (
    "Linear relationship between trailing momentum and next session return",
    "Feature values computed solely from session observations available at decision time",
    "Target represents next session simple return without trading friction or market impact",
    "Strict chronological ordering without future data leakage in training or validation",
)
_MOMENTUM_MODEL_WARNINGS = (
    "Past predictive relationship may not persist in changing market regimes",
    "Single-feature momentum regression does not account for volatility clustering",
)
_MOMENTUM_MODEL_LIMITATIONS = (
    "Model emits forecast return values only and does not decide portfolio weights "
    "or execution orders",
    "Evaluation assumes execution at exact close price without slippage or transaction fees",
)
_MOMENTUM_MODEL_UNSUPPORTED_CLAIMS = (
    "Model does not guarantee trading profitability or positive risk-adjusted alpha",
    "Model is not an autonomous trading agent or order router",
)

_POTTS_MODEL_ASSUMPTIONS = (
    "Market price dynamics exhibit gain-loss asymmetry from collective trader imitation and fear",
    "Return distributions can be mapped into discrete q-state Potts spin configurations",
    (
        "Inverse waiting times capture acceleration differences between downward"
        " drawdowns and upward rallies"
    ),
    "Feature values computed solely from session observations available at decision time",
)
_POTTS_MODEL_WARNINGS = (
    "Empirical gain-loss asymmetry varies with market volatility regimes and coverage universe",
    "Discrete state discretization may smooth extreme tail events",
)
_POTTS_MODEL_LIMITATIONS = (
    "Model emits forecast return values only and does not execute or route orders",
    "Evaluation assumes execution at exact close price without slippage or transaction fees",
)
_POTTS_MODEL_UNSUPPORTED_CLAIMS = (
    "Model does not guarantee trading profitability or eliminate drawdown risk",
    "Model is not an autonomous trading agent or general plugin framework",
)


def is_naive_benchmark_comparison_complete(
    benchmark: Mapping[str, JsonValue] | None,
) -> bool:
    """Return whether a benchmark contains a verified comparable test result."""
    if benchmark is None:
        return False
    comparison_value = benchmark.get("out_of_sample_comparison")
    comparison = comparison_value if isinstance(comparison_value, dict) else None
    period_metrics_value = benchmark.get("period_metrics")
    period_metrics = period_metrics_value if isinstance(period_metrics_value, dict) else None
    test_metrics_value = period_metrics.get("test") if period_metrics else None
    test_metrics = test_metrics_value if isinstance(test_metrics_value, dict) else None
    comparison_metric_names = (
        "model_rmse",
        "benchmark_rmse",
        "rmse_improvement",
        "model_mae",
        "benchmark_mae",
        "mae_improvement",
        "model_r2",
        "benchmark_r2",
    )

    def finite_number(value: JsonValue) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )

    return bool(
        benchmark.get("name") in {"zero_return", "historical_mean", "persistence"}
        and benchmark.get("completed") is True
        and comparison is not None
        and comparison.get("benchmark_name") == benchmark.get("name")
        and comparison.get("period") == "test"
        and comparison.get("sample_scope") == "out_of_sample"
        and comparison.get("status") == "evaluated"
        and isinstance(comparison.get("observations"), int)
        and not isinstance(comparison.get("observations"), bool)
        and comparison.get("observations", 0) > 0
        and comparison.get("same_eligible_periods") is True
        and comparison.get("comparison_complete") is True
        and all(finite_number(comparison.get(name)) for name in comparison_metric_names)
        and test_metrics is not None
        and all(finite_number(test_metrics.get(name)) for name in ("mae", "rmse", "r2"))
    )


@dataclass(frozen=True)
class PredictiveModelParameter:
    """Typed metadata for one user-configurable Predictive Model parameter."""

    name: str
    param_type: Literal["int", "float", "str", "bool"]
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class PredictiveModelMetadata:
    """Definition contract displayed to an Analyst before a Run."""

    name: str
    display_name: str
    description: str
    target: str
    horizon: int
    features: tuple[str, ...]
    training_window: int
    parameters: tuple[PredictiveModelParameter, ...]
    output_meaning: str
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class FittedModelArtifact:
    """Serializable fitted state required to reproduce model predictions."""

    model_name: str
    feature_name: str
    target_name: str
    horizon: int
    intercept: float
    coefficient: float
    training_start: str
    training_end: str
    training_observations: int
    parameters: dict[str, JsonValue]
    seed: int | None
    training_metrics: dict[str, JsonValue]
    feature_definition: dict[str, JsonValue] = field(default_factory=dict)
    preprocessing: dict[str, JsonValue] = field(default_factory=dict)

    def to_json(self) -> dict[str, JsonValue]:
        """Return the fitted state as a JSON-compatible object."""
        return {
            "model_name": self.model_name,
            "feature_name": self.feature_name,
            "target_name": self.target_name,
            "horizon": self.horizon,
            "intercept": self.intercept,
            "coefficient": self.coefficient,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "training_observations": self.training_observations,
            "parameters": self.parameters,
            "seed": self.seed,
            "training_metrics": self.training_metrics,
            "feature_definition": self.feature_definition,
            "preprocessing": self.preprocessing,
        }


@dataclass(frozen=True)
class PredictiveModelPrediction:
    """One time-stamped model output aligned to an eligible session."""

    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: float
    target_date: str | None
    period: SplitName | None = None

    def to_json(self) -> dict[str, JsonValue]:
        """Return this prediction as a JSON-compatible object."""
        return {
            "session_date": self.session_date,
            "feature_value": self.feature_value,
            "predicted_value": self.predicted_value,
            "actual_target": self.actual_target,
            "target_date": self.target_date,
            "period": self.period,
        }


@dataclass(frozen=True)
class PredictiveModelForecast:
    """One prediction whose future target is not available yet."""

    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: None
    target_date: None
    period: None

    def to_json(self) -> dict[str, JsonValue]:
        """Return an explicit not-yet-labelled prediction record."""
        return {
            "session_date": self.session_date,
            "feature_value": self.feature_value,
            "predicted_value": self.predicted_value,
            "actual_target": self.actual_target,
            "target_date": self.target_date,
            "period": self.period,
        }


PredictiveModelOutput = PredictiveModelPrediction | PredictiveModelForecast


FitFunction = Callable[[pd.DataFrame, dict[str, JsonValue], int | None], FittedModelArtifact]
PredictFunction = Callable[[FittedModelArtifact, pd.DataFrame], list[PredictiveModelOutput]]


@dataclass(frozen=True)
class PredictiveModelSpec:
    """Metadata plus interchangeable fit and predict Strategies."""

    metadata: PredictiveModelMetadata
    fit: FitFunction
    predict: PredictFunction

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def target(self) -> str:
        return self.metadata.target

    @property
    def horizon(self) -> int:
        return self.metadata.horizon

    @property
    def features(self) -> tuple[str, ...]:
        return self.metadata.features

    @property
    def training_window(self) -> int:
        return self.metadata.training_window

    @property
    def parameters(self) -> tuple[PredictiveModelParameter, ...]:
        return self.metadata.parameters

    @property
    def outputs(self) -> tuple[str, ...]:
        return self.metadata.outputs

    @property
    def output_meaning(self) -> str:
        return self.metadata.output_meaning


class MomentumRegressionParameters(BaseModel):
    """Validated parameters for the first Predictive Model implementation."""

    model_config = ConfigDict(extra="forbid")

    momentum_period: int = Field(default=20, ge=1, le=500)
    training_window: int = Field(default=252, ge=2, le=10_000)
    validation_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    test_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    evaluation_mode: EvaluationMode = "holdout"
    naive_benchmark: NaiveBenchmarkName = "zero_return"

    @model_validator(mode="after")
    def leaves_training_observations(self) -> "MomentumRegressionParameters":
        if self.validation_fraction + self.test_fraction >= 1.0:
            raise ValueError(
                "validation_fraction plus test_fraction must leave training observations."
            )
        return self


class PottsGainLossParameters(BaseModel):
    """Validated parameters for the published Potts Gain-Loss Asymmetry technique."""

    model_config = ConfigDict(extra="forbid")

    threshold_return: float = Field(default=0.05, gt=0.0, le=0.5)
    lookback_window: int = Field(default=60, ge=10, le=500)
    q_states: int = Field(default=4, ge=2, le=16)
    training_window: int = Field(default=252, ge=2, le=10_000)
    validation_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    test_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    evaluation_mode: EvaluationMode = "holdout"
    naive_benchmark: NaiveBenchmarkName = "zero_return"

    @model_validator(mode="after")
    def leaves_training_observations(self) -> "PottsGainLossParameters":
        if self.validation_fraction + self.test_fraction >= 1.0:
            raise ValueError(
                "validation_fraction plus test_fraction must leave training observations."
            )
        return self


def build_supervised_frame(
    bars: Sequence[DailyBar], *, momentum_period: int, horizon: int
) -> pd.DataFrame:
    """Build features and next-session labels without using future feature values."""
    if momentum_period < 1:
        raise PredictiveModelParameterError(
            f"momentum_period must be at least 1, got {momentum_period}."
        )
    if horizon < 1:
        raise PredictiveModelParameterError(f"horizon must be at least 1, got {horizon}.")

    ordered_bars = sorted(bars, key=lambda bar: bar.session_date)
    closes: list[float] = []
    for bar in ordered_bars:
        if not math.isfinite(bar.close) or bar.close <= 0:
            raise PredictiveModelCalculationError(
                f"Close price for session {bar.session_date} must be a positive finite number."
            )
        closes.append(float(bar.close))

    rows: list[dict[str, float | str | None]] = []
    for index, bar in enumerate(ordered_bars):
        momentum = (
            closes[index] / closes[index - momentum_period] - 1.0
            if index >= momentum_period
            else None
        )
        next_return = (
            closes[index + horizon] / closes[index] - 1.0 if index + horizon < len(closes) else None
        )
        target_date = (
            ordered_bars[index + horizon].session_date
            if index + horizon < len(ordered_bars)
            else None
        )
        rows.append(
            {
                "session_date": bar.session_date,
                "momentum": momentum,
                "next_session_return": next_return,
                "target_date": target_date,
            }
        )

    return pd.DataFrame(
        rows,
        columns=["session_date", "momentum", "next_session_return", "target_date"],
    )


def build_potts_supervised_frame(
    bars: Sequence[DailyBar],
    config: PottsGainLossParameters | None = None,
    *,
    horizon: int = 1,
) -> pd.DataFrame:
    """Build point-in-time Potts gain-loss asymmetry features and labels (Bornholdt 2021)."""
    cfg = config or PottsGainLossParameters()
    threshold_return = cfg.threshold_return
    lookback_window = cfg.lookback_window
    q_states = cfg.q_states
    if horizon < 1:
        raise PredictiveModelParameterError(f"horizon must be at least 1, got {horizon}.")

    ordered_bars = sorted(bars, key=lambda bar: bar.session_date)
    closes: list[float] = []
    for bar in ordered_bars:
        if not math.isfinite(bar.close) or bar.close <= 0:
            raise PredictiveModelCalculationError(
                f"Close price for session {bar.session_date} must be a positive finite number."
            )
        closes.append(float(bar.close))

    returns: list[float] = [0.0]
    for i in range(1, len(closes)):
        returns.append(closes[i] / closes[i - 1] - 1.0)

    rows: list[dict[str, float | str | None]] = []
    for index, bar in enumerate(ordered_bars):
        potts_score: float | None = None
        asymmetry_ratio: float | None = None
        order_param: float | None = None

        if index >= lookback_window:
            window_closes = closes[index - lookback_window : index + 1]
            window_returns = returns[index - lookback_window + 1 : index + 1]

            # 1. Inverse statistics: shortest waiting time to drop <= -threshold_return from any
            # peak vs shortest waiting time to gain >= +threshold_return from any trough
            tau_loss = float(lookback_window)
            tau_gain = float(lookback_window)

            running_peak = window_closes[0]
            peak_idx = 0
            for w_idx in range(1, len(window_closes)):
                price = window_closes[w_idx]
                if price > running_peak:
                    running_peak = price
                    peak_idx = w_idx
                drop = (price - running_peak) / running_peak
                if drop <= -threshold_return:
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
                gain = (price - running_trough) / running_trough
                if gain >= threshold_return:
                    dur = float(w_idx - trough_idx)
                    if dur > 0 and dur < tau_gain:
                        tau_gain = dur

            # Gain-loss asymmetry ratio: (tau_loss - tau_gain) / (tau_loss + tau_gain)
            denom_tau = tau_gain + tau_loss
            if denom_tau > 1e-12:
                asymmetry_ratio = (tau_loss - tau_gain) / denom_tau
            else:
                asymmetry_ratio = 0.0

            # 2. Potts q-state spin discretization and order parameter
            n_obs = len(window_returns)
            sorted_rets = sorted(window_returns)
            bin_counts = [0] * q_states
            for r in window_returns:
                rank = 0
                for s_r in sorted_rets:
                    if r > s_r:
                        rank += 1
                bin_idx = min(q_states - 1, int((rank / n_obs) * q_states))
                bin_counts[bin_idx] += 1

            n_max = max(bin_counts)
            expected_n = n_obs / q_states
            denom_m = n_obs - expected_n
            if denom_m > 1e-12:
                order_param = max(0.0, (n_max - expected_n) / denom_m)
            else:
                order_param = 0.0

            # Composite Potts Gain-Loss feature
            potts_score = asymmetry_ratio * (1.0 + order_param)

        next_return = (
            closes[index + horizon] / closes[index] - 1.0 if index + horizon < len(closes) else None
        )
        target_date = (
            ordered_bars[index + horizon].session_date
            if index + horizon < len(ordered_bars)
            else None
        )

        rows.append(
            {
                "session_date": bar.session_date,
                "potts_gain_loss_score": potts_score,
                "gain_loss_asymmetry_ratio": asymmetry_ratio,
                "potts_order_parameter": order_param,
                "next_session_return": next_return,
                "target_date": target_date,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "session_date",
            "potts_gain_loss_score",
            "gain_loss_asymmetry_ratio",
            "potts_order_parameter",
            "next_session_return",
            "target_date",
        ],
    )


def _resolve_parameters(name: str, parameters: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    if name == "momentum_return_regression":
        try:
            config = MomentumRegressionParameters.model_validate(dict(parameters))
        except ValidationError as error:
            raise PredictiveModelParameterError(str(error)) from error
        return {
            "momentum_period": config.momentum_period,
            "training_window": config.training_window,
            "validation_fraction": config.validation_fraction,
            "test_fraction": config.test_fraction,
            "evaluation_mode": config.evaluation_mode,
            "naive_benchmark": config.naive_benchmark,
        }
    elif name == "potts_gain_loss_asymmetry":
        try:
            potts_config = PottsGainLossParameters.model_validate(dict(parameters))
        except ValidationError as error:
            raise PredictiveModelParameterError(str(error)) from error
        return {
            "threshold_return": potts_config.threshold_return,
            "lookback_window": potts_config.lookback_window,
            "q_states": potts_config.q_states,
            "training_window": potts_config.training_window,
            "validation_fraction": potts_config.validation_fraction,
            "test_fraction": potts_config.test_fraction,
            "evaluation_mode": potts_config.evaluation_mode,
            "naive_benchmark": potts_config.naive_benchmark,
        }
    raise PredictiveModelNotFoundError(f"Unknown Predictive Model '{name}'.")


def _fit_momentum_regression(
    training_frame: pd.DataFrame,
    parameters: dict[str, JsonValue],
    seed: int | None,
) -> FittedModelArtifact:
    required_columns = {"session_date", "momentum", "next_session_return"}
    if not required_columns.issubset(training_frame.columns):
        raise PredictiveModelCalculationError(
            "Training data must contain session_date, momentum, and next_session_return."
        )

    usable = training_frame.dropna(subset=["momentum", "next_session_return"]).reset_index(
        drop=True
    )
    if len(usable) < 2:
        raise PredictiveModelCalculationError(
            "At least two training observations are required to fit the Predictive Model."
        )

    features = [float(value) for value in usable["momentum"].tolist()]
    targets = [float(value) for value in usable["next_session_return"].tolist()]
    if any(not math.isfinite(value) for value in features + targets):
        raise PredictiveModelCalculationError("Training data contains non-finite values.")

    feature_mean = sum(features) / len(features)
    target_mean = sum(targets) / len(targets)
    denominator = sum((feature - feature_mean) ** 2 for feature in features)
    if denominator <= 1e-15:
        raise PredictiveModelCalculationError(
            "Training observations must contain variation in the momentum feature."
        )

    numerator = sum(
        (feature - feature_mean) * (target - target_mean)
        for feature, target in zip(features, targets, strict=True)
    )
    coefficient = numerator / denominator
    intercept = target_mean - coefficient * feature_mean
    fitted_values = [intercept + coefficient * feature for feature in features]
    residual_sum = sum(
        (target - fitted) ** 2 for target, fitted in zip(targets, fitted_values, strict=True)
    )
    total_sum = sum((target - target_mean) ** 2 for target in targets)
    in_sample_r2 = 1.0 - residual_sum / total_sum if total_sum > 1e-15 else 0.0
    in_sample_rmse = math.sqrt(residual_sum / len(targets))
    training_feature_start = str(usable.loc[0, "session_date"])
    training_feature_end = str(usable.loc[len(usable) - 1, "session_date"])

    return FittedModelArtifact(
        model_name="momentum_return_regression",
        feature_name="trailing_close_momentum",
        target_name="next_session_return",
        horizon=1,
        intercept=intercept,
        coefficient=coefficient,
        training_start=training_feature_start,
        training_end=training_feature_end,
        training_observations=len(usable),
        parameters=parameters,
        seed=seed,
        training_metrics={
            "in_sample_r2": in_sample_r2,
            "in_sample_rmse": in_sample_rmse,
        },
        feature_definition={
            "name": "trailing_close_momentum",
            "source": "close",
            "lookback": int(parameters["momentum_period"]),
            "horizon": 1,
            "uses_future_rows_for_feature": False,
            "fit_scope": "training_only",
        },
        preprocessing={
            "name": "none",
            "fit_scope": "training_only",
            "training_feature_start": training_feature_start,
            "training_feature_end": training_feature_end,
            "training_observations": len(usable),
            "uses_validation_or_test": False,
        },
    )


def _fit_potts_gain_loss(
    training_frame: pd.DataFrame,
    parameters: dict[str, JsonValue],
    seed: int | None,
) -> FittedModelArtifact:
    required_columns = {"session_date", "potts_gain_loss_score", "next_session_return"}
    if not required_columns.issubset(training_frame.columns):
        raise PredictiveModelCalculationError(
            "Training data must contain session_date, potts_gain_loss_score, and "
            "next_session_return."
        )

    usable = training_frame.dropna(
        subset=["potts_gain_loss_score", "next_session_return"]
    ).reset_index(drop=True)
    if len(usable) < 2:
        raise PredictiveModelCalculationError(
            "At least two training observations are required to fit the Predictive Model."
        )

    features = [float(value) for value in usable["potts_gain_loss_score"].tolist()]
    targets = [float(value) for value in usable["next_session_return"].tolist()]
    if any(not math.isfinite(value) for value in features + targets):
        raise PredictiveModelCalculationError("Training data contains non-finite values.")

    feature_mean = sum(features) / len(features)
    target_mean = sum(targets) / len(targets)
    denominator = sum((feature - feature_mean) ** 2 for feature in features)
    if denominator <= 1e-15:
        coefficient = 0.0
        intercept = target_mean
    else:
        numerator = sum(
            (feature - feature_mean) * (target - target_mean)
            for feature, target in zip(features, targets, strict=True)
        )
        coefficient = numerator / denominator
        intercept = target_mean - coefficient * feature_mean

    fitted_values = [intercept + coefficient * feature for feature in features]
    residual_sum = sum(
        (target - fitted) ** 2 for target, fitted in zip(targets, fitted_values, strict=True)
    )
    total_sum = sum((target - target_mean) ** 2 for target in targets)
    in_sample_r2 = 1.0 - residual_sum / total_sum if total_sum > 1e-15 else 0.0
    in_sample_rmse = math.sqrt(residual_sum / len(targets))
    training_feature_start = str(usable.loc[0, "session_date"])
    training_feature_end = str(usable.loc[len(usable) - 1, "session_date"])

    return FittedModelArtifact(
        model_name="potts_gain_loss_asymmetry",
        feature_name="potts_gain_loss_score",
        target_name="next_session_return",
        horizon=1,
        intercept=intercept,
        coefficient=coefficient,
        training_start=training_feature_start,
        training_end=training_feature_end,
        training_observations=len(usable),
        parameters=parameters,
        seed=seed,
        training_metrics={
            "in_sample_r2": in_sample_r2,
            "in_sample_rmse": in_sample_rmse,
        },
        feature_definition={
            "name": "potts_gain_loss_score",
            "source": "close",
            "lookback_window": int(parameters.get("lookback_window", 60)),
            "threshold_return": float(parameters.get("threshold_return", 0.05)),
            "q_states": int(parameters.get("q_states", 4)),
            "horizon": 1,
            "uses_future_rows_for_feature": False,
            "fit_scope": "training_only",
        },
        preprocessing={
            "name": "none",
            "fit_scope": "training_only",
            "training_feature_start": training_feature_start,
            "training_feature_end": training_feature_end,
            "training_observations": len(usable),
            "uses_validation_or_test": False,
        },
    )


def _predict_potts_gain_loss(
    artifact: FittedModelArtifact, eligible_frame: pd.DataFrame
) -> list[PredictiveModelOutput]:
    if not {"session_date", "potts_gain_loss_score"}.issubset(eligible_frame.columns):
        raise PredictiveModelCalculationError(
            "Prediction data must contain session_date and potts_gain_loss_score."
        )

    target_values = (
        eligible_frame["next_session_return"].tolist()
        if "next_session_return" in eligible_frame.columns
        else [None] * len(eligible_frame)
    )
    target_dates = (
        eligible_frame["target_date"].tolist()
        if "target_date" in eligible_frame.columns
        else [None] * len(eligible_frame)
    )
    predictions: list[PredictiveModelOutput] = []
    for date, feature, target, target_date in zip(
        eligible_frame["session_date"].tolist(),
        eligible_frame["potts_gain_loss_score"].tolist(),
        target_values,
        target_dates,
        strict=True,
    ):
        if pd.isna(feature):
            continue
        feature_value = float(feature)
        actual_target = None if pd.isna(target) else float(target)
        predicted_value = artifact.intercept + artifact.coefficient * feature_value
        if actual_target is None:
            predictions.append(
                PredictiveModelForecast(
                    session_date=str(date),
                    feature_value=feature_value,
                    predicted_value=predicted_value,
                    actual_target=None,
                    target_date=None,
                    period=None,
                )
            )
        else:
            predictions.append(
                PredictiveModelPrediction(
                    session_date=str(date),
                    feature_value=feature_value,
                    predicted_value=predicted_value,
                    actual_target=actual_target,
                    target_date=None if pd.isna(target_date) else str(target_date),
                )
            )
    return predictions


def _predict_momentum_regression(
    artifact: FittedModelArtifact, eligible_frame: pd.DataFrame
) -> list[PredictiveModelOutput]:
    if not {"session_date", "momentum"}.issubset(eligible_frame.columns):
        raise PredictiveModelCalculationError(
            "Prediction data must contain session_date and momentum."
        )

    target_values = (
        eligible_frame["next_session_return"].tolist()
        if "next_session_return" in eligible_frame.columns
        else [None] * len(eligible_frame)
    )
    target_dates = (
        eligible_frame["target_date"].tolist()
        if "target_date" in eligible_frame.columns
        else [None] * len(eligible_frame)
    )
    predictions: list[PredictiveModelOutput] = []
    for date, feature, target, target_date in zip(
        eligible_frame["session_date"].tolist(),
        eligible_frame["momentum"].tolist(),
        target_values,
        target_dates,
        strict=True,
    ):
        if pd.isna(feature):
            continue
        feature_value = float(feature)
        actual_target = None if pd.isna(target) else float(target)
        predicted_value = artifact.intercept + artifact.coefficient * feature_value
        if actual_target is None:
            predictions.append(
                PredictiveModelForecast(
                    session_date=str(date),
                    feature_value=feature_value,
                    predicted_value=predicted_value,
                    actual_target=None,
                    target_date=None,
                    period=None,
                )
            )
        else:
            predictions.append(
                PredictiveModelPrediction(
                    session_date=str(date),
                    feature_value=feature_value,
                    predicted_value=predicted_value,
                    actual_target=actual_target,
                    target_date=None if pd.isna(target_date) else str(target_date),
                )
            )
    return predictions


PREDICTIVE_MODEL_REGISTRY: dict[str, PredictiveModelSpec] = {
    "momentum_return_regression": PredictiveModelSpec(
        metadata=PredictiveModelMetadata(
            name="momentum_return_regression",
            display_name="Momentum Return Regression",
            description=(
                "Fits an ordinary least-squares regression from trailing close-price "
                "momentum to the next session's simple return."
            ),
            target="next_session_return",
            horizon=1,
            features=("trailing_close_momentum",),
            training_window=252,
            parameters=(
                PredictiveModelParameter(
                    name="momentum_period",
                    param_type="int",
                    default=20,
                    description="Number of sessions used to calculate trailing close momentum.",
                    min_value=1,
                    max_value=500,
                ),
                PredictiveModelParameter(
                    name="training_window",
                    param_type="int",
                    default=252,
                    description=(
                        "Initial number of latest labelled observations used for fitting; "
                        "rolling keeps this size and expanding grows from it."
                    ),
                    min_value=2,
                    max_value=10_000,
                ),
                PredictiveModelParameter(
                    name="validation_fraction",
                    param_type="float",
                    default=0.2,
                    description="Fraction of labelled observations reserved for validation.",
                    min_value=0.01,
                    max_value=0.49,
                ),
                PredictiveModelParameter(
                    name="test_fraction",
                    param_type="float",
                    default=0.2,
                    description=(
                        "Fraction of labelled observations reserved for out-of-sample testing."
                    ),
                    min_value=0.01,
                    max_value=0.49,
                ),
                PredictiveModelParameter(
                    name="evaluation_mode",
                    param_type="str",
                    default="holdout",
                    description="Chronological evaluation mode for validation and test folds.",
                    options=("holdout", "expanding", "rolling"),
                ),
                PredictiveModelParameter(
                    name="naive_benchmark",
                    param_type="str",
                    default="zero_return",
                    description="Explicit naive benchmark for out-of-sample comparison.",
                    options=("zero_return", "historical_mean", "persistence"),
                ),
            ),
            output_meaning=(
                "Predicted next session simple return, expressed as a decimal fraction, "
                "for each timestamp with an eligible trailing feature."
            ),
            outputs=(
                "predicted_next_session_return",
                "trailing_close_momentum",
                "actual_next_session_return",
            ),
        ),
        fit=_fit_momentum_regression,
        predict=_predict_momentum_regression,
    ),
    "potts_gain_loss_asymmetry": PredictiveModelSpec(
        metadata=PredictiveModelMetadata(
            name="potts_gain_loss_asymmetry",
            display_name="Potts Gain-Loss Asymmetry",
            description=(
                "Fits an emergent inverse-statistics and Potts spin magnetization model "
                "to predict the next session's return from gain-loss waiting-time asymmetry "
                "and discrete return polarization."
            ),
            target="next_session_return",
            horizon=1,
            features=(
                "potts_gain_loss_score",
                "gain_loss_asymmetry_ratio",
                "potts_order_parameter",
            ),
            training_window=252,
            parameters=(
                PredictiveModelParameter(
                    name="threshold_return",
                    param_type="float",
                    default=0.05,
                    description="Return threshold for gain and loss waiting times.",
                    min_value=0.01,
                    max_value=0.5,
                ),
                PredictiveModelParameter(
                    name="lookback_window",
                    param_type="int",
                    default=60,
                    description=(
                        "Number of sessions used to calculate inverse waiting times and "
                        "return state bins."
                    ),
                    min_value=10,
                    max_value=500,
                ),
                PredictiveModelParameter(
                    name="q_states",
                    param_type="int",
                    default=4,
                    description="Number of discrete Potts spin states for return partition.",
                    min_value=2,
                    max_value=16,
                ),
                PredictiveModelParameter(
                    name="training_window",
                    param_type="int",
                    default=252,
                    description=(
                        "Initial number of latest labelled observations used for fitting; "
                        "rolling keeps this size and expanding grows from it."
                    ),
                    min_value=2,
                    max_value=10_000,
                ),
                PredictiveModelParameter(
                    name="validation_fraction",
                    param_type="float",
                    default=0.2,
                    description="Fraction of labelled observations reserved for validation.",
                    min_value=0.01,
                    max_value=0.49,
                ),
                PredictiveModelParameter(
                    name="test_fraction",
                    param_type="float",
                    default=0.2,
                    description=(
                        "Fraction of labelled observations reserved for out-of-sample testing."
                    ),
                    min_value=0.01,
                    max_value=0.49,
                ),
                PredictiveModelParameter(
                    name="evaluation_mode",
                    param_type="str",
                    default="holdout",
                    description="Chronological evaluation mode for validation and test folds.",
                    options=("holdout", "expanding", "rolling"),
                ),
                PredictiveModelParameter(
                    name="naive_benchmark",
                    param_type="str",
                    default="zero_return",
                    description="Explicit naive benchmark for out-of-sample comparison.",
                    options=("zero_return", "historical_mean", "persistence"),
                ),
            ),
            output_meaning=(
                "Predicted next session simple return, expressed as a decimal fraction, "
                "derived from emergent gain-loss asymmetry."
            ),
            outputs=(
                "predicted_next_session_return",
                "potts_gain_loss_score",
                "actual_next_session_return",
            ),
        ),
        fit=_fit_potts_gain_loss,
        predict=_predict_potts_gain_loss,
    ),
}


def list_predictive_models() -> list[PredictiveModelMetadata]:
    """Return metadata for every registered Predictive Model."""
    return [spec.metadata for spec in PREDICTIVE_MODEL_REGISTRY.values()]


def get_predictive_model_spec(name: str) -> PredictiveModelSpec:
    """Retrieve one registered Predictive Model Strategy bundle."""
    spec = PREDICTIVE_MODEL_REGISTRY.get(name)
    if spec is None:
        raise PredictiveModelNotFoundError(f"Unknown Predictive Model '{name}'.")
    return spec


def fit_model(
    name: str,
    training_frame: pd.DataFrame,
    parameters: Mapping[str, JsonValue],
    seed: int | None = None,
) -> FittedModelArtifact:
    """Fit on a bounded frame; learned feature or preprocessing state stays local."""
    if seed is not None and (isinstance(seed, bool) or seed < 0):
        raise PredictiveModelParameterError("seed must be a non-negative integer when supplied.")
    spec = get_predictive_model_spec(name)
    resolved_parameters = _resolve_parameters(name, parameters)
    return spec.fit(training_frame, resolved_parameters, seed)


def predict(
    artifact: FittedModelArtifact, eligible_frame: pd.DataFrame
) -> list[PredictiveModelOutput]:
    """Predict from a fitted artifact using only the supplied eligible feature frame."""
    spec = get_predictive_model_spec(artifact.model_name)
    return spec.predict(artifact, eligible_frame)


def run_predictive_model(
    name: str,
    bars: Sequence[DailyBar],
    parameters: Mapping[str, JsonValue],
    seed: int | None = None,
) -> PredictiveModelCalculation:
    """Build model data, then delegate all evaluation to the shared runner."""
    from .model_evaluation import ModelEvaluationInput, evaluate_model

    spec = get_predictive_model_spec(name)
    resolved = _resolve_parameters(name, parameters)
    mode = resolved["evaluation_mode"]
    if mode not in ("holdout", "expanding", "rolling"):
        raise PredictiveModelParameterError(
            "evaluation_mode must be one of: holdout, expanding, rolling."
        )
    benchmark = str(resolved.get("naive_benchmark", "zero_return"))
    if benchmark not in ("zero_return", "historical_mean", "persistence"):
        raise PredictiveModelParameterError(
            "naive_benchmark must be one of: zero_return, historical_mean, persistence."
        )
    if name == "momentum_return_regression":
        frame = build_supervised_frame(
            bars, momentum_period=int(resolved["momentum_period"]), horizon=spec.horizon
        )
        feature = "momentum"
        assumptions, warnings, limitations, unsupported = (
            _MOMENTUM_MODEL_ASSUMPTIONS,
            _MOMENTUM_MODEL_WARNINGS,
            _MOMENTUM_MODEL_LIMITATIONS,
            _MOMENTUM_MODEL_UNSUPPORTED_CLAIMS,
        )
    elif name == "potts_gain_loss_asymmetry":
        config = PottsGainLossParameters(
            threshold_return=float(resolved["threshold_return"]),
            lookback_window=int(resolved["lookback_window"]),
            q_states=int(resolved["q_states"]),
            training_window=int(resolved["training_window"]),
            validation_fraction=float(resolved["validation_fraction"]),
            test_fraction=float(resolved["test_fraction"]),
            evaluation_mode=mode,
            naive_benchmark=benchmark,
        )
        frame = build_potts_supervised_frame(bars, config=config, horizon=spec.horizon)
        feature = "potts_gain_loss_score"
        assumptions, warnings, limitations, unsupported = (
            _POTTS_MODEL_ASSUMPTIONS,
            _POTTS_MODEL_WARNINGS,
            _POTTS_MODEL_LIMITATIONS,
            _POTTS_MODEL_UNSUPPORTED_CLAIMS,
        )
    else:
        raise PredictiveModelNotFoundError(f"Unknown Predictive Model '{name}'.")
    return evaluate_model(
        ModelEvaluationInput(
            name=name,
            frame=frame,
            feature_column=feature,
            bars=bars,
            parameters=resolved,
            seed=seed,
            fit=lambda training, params, model_seed: fit_model(name, training, params, model_seed),
            forecast=predict,
            metadata=spec.metadata,
            assumptions=assumptions,
            warnings=warnings,
            limitations=limitations,
            unsupported_claims=unsupported,
        )
    )
