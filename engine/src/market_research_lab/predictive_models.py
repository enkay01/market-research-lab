"""Typed, deterministic Predictive Model definitions and execution seams."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .json_types import JsonValue
from .market_data import DailyBar


class PredictiveModelError(ValueError):
    """Base error for Predictive Model discovery, validation, and calculation."""


class PredictiveModelNotFoundError(PredictiveModelError):
    """Raised when a requested Predictive Model is not registered."""


class PredictiveModelParameterError(PredictiveModelError):
    """Raised when a Predictive Model parameter is invalid."""


class PredictiveModelDataError(PredictiveModelError):
    """Raised when the requested Dataset Version cannot provide model data."""


class PredictiveModelCalculationError(PredictiveModelError):
    """Raised when a Predictive Model cannot be fitted on the supplied data."""


SplitName = Literal["training", "validation", "test"]
EvaluationMode = Literal["holdout", "expanding", "rolling"]
NaiveBenchmarkName = Literal["zero_return", "historical_mean", "persistence"]
SampleScope = Literal["in_sample", "validation", "out_of_sample"]
NaiveBenchmarkPrediction = tuple[str, str | None, float]


NaiveBenchmarkPredictor = Callable[
    [str, Sequence[float], Mapping[str, float]], float
]

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
    "Inverse waiting times capture acceleration differences between downward drawdowns and upward rallies",
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


@dataclass(frozen=True)
class _NaiveBenchmarkSpec:
    """One explicit, deterministic naive forecast rule."""

    name: NaiveBenchmarkName
    display_name: str
    description: str
    predict: NaiveBenchmarkPredictor


def _zero_return_prediction(
    _: str, __: Sequence[float], ___: Mapping[str, float]
) -> float:
    return 0.0


def _historical_mean_prediction(
    _: str, training_targets: Sequence[float], __: Mapping[str, float]
) -> float:
    return sum(training_targets) / len(training_targets) if training_targets else 0.0


def _persistence_prediction(
    session_date: str, _: Sequence[float], prior_returns: Mapping[str, float]
) -> float:
    return float(prior_returns.get(session_date, 0.0))


_NAIVE_BENCHMARKS: dict[NaiveBenchmarkName, _NaiveBenchmarkSpec] = {
    "zero_return": _NaiveBenchmarkSpec(
        name="zero_return",
        display_name="Zero Return Benchmark",
        description=(
            "Unconditional zero-return forecast corresponding to the efficient "
            "market hypothesis baseline."
        ),
        predict=_zero_return_prediction,
    ),
    "historical_mean": _NaiveBenchmarkSpec(
        name="historical_mean",
        display_name="Historical Mean Benchmark",
        description=(
            "Constant forecast equal to the historical sample mean return over "
            "the eligible training window."
        ),
        predict=_historical_mean_prediction,
    ),
    "persistence": _NaiveBenchmarkSpec(
        name="persistence",
        display_name="Persistence Benchmark",
        description=(
            "Naive random-walk forecast using the most recent observed session "
            "return available at the prediction session."
        ),
        predict=_persistence_prediction,
    ),
}


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
class NaiveBenchmarkEvaluation:
    """Explicit naive benchmark definition and comparable evaluation records."""

    name: NaiveBenchmarkName
    display_name: str
    description: str
    period_metrics: dict[str, dict[str, float]]
    out_of_sample_comparison: dict[str, JsonValue]
    completed: bool = False

    def to_json(self) -> dict[str, JsonValue]:
        """Return the complete benchmark comparison as a JSON-compatible object."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "period_metrics": self.period_metrics,
            "out_of_sample_comparison": self.out_of_sample_comparison,
            "completed": self.completed,
        }


@dataclass(frozen=True)
class PredictiveModelFoldTrainingPolicy:
    """Typed options that define one fold's eligible training window."""

    decision_session_date: str
    initial_training_start: str
    training_window: int
    evaluation_mode: Literal["expanding", "rolling"]


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


@dataclass(frozen=True)
class PredictiveModelSplit:
    """One chronological period used by a Predictive Model Run."""

    period: SplitName
    start: str
    end: str
    feature_start: str
    feature_end: str
    observations: int
    labelled_observations: int
    fit_scope: str

    def to_json(self) -> dict[str, JsonValue]:
        """Return the split boundaries and leakage policy as JSON."""
        return {
            "period": self.period,
            "start": self.start,
            "end": self.end,
            "feature_start": self.feature_start,
            "feature_end": self.feature_end,
            "observations": self.observations,
            "labelled_observations": self.labelled_observations,
            "fit_scope": self.fit_scope,
        }


@dataclass(frozen=True)
class PredictiveModelPeriodMetrics:
    """Metrics for one labelled chronological period."""

    period: SplitName
    observations: int
    metrics: dict[str, float]
    sample_scope: SampleScope
    benchmark_metrics: dict[str, float] = field(default_factory=dict)
    comparison: dict[str, JsonValue] = field(default_factory=dict)

    def to_json(self) -> dict[str, JsonValue]:
        """Return period-labelled metrics for artifacts and interface responses."""
        return {
            "period": self.period,
            "observations": self.observations,
            "metrics": self.metrics,
            "benchmark_metrics": self.benchmark_metrics,
            "comparison": self.comparison,
            "sample_scope": self.sample_scope,
        }


@dataclass(frozen=True)
class PredictiveModelFold:
    """One walk-forward prediction and the artifact that produced it."""

    fold_index: int
    period: Literal["validation", "test"]
    prediction_session_date: str
    target_date: str | None
    training_start: str
    training_end: str
    training_observations: int
    fit_scope: str
    artifact: FittedModelArtifact
    prediction: PredictiveModelOutput
    metrics: dict[str, float]

    def to_json(self) -> dict[str, JsonValue]:
        """Return fold provenance, prediction, and single-observation errors."""
        return {
            "fold_index": self.fold_index,
            "period": self.period,
            "prediction_session_date": self.prediction_session_date,
            "target_date": self.target_date,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "training_observations": self.training_observations,
            "fit_scope": self.fit_scope,
            "artifact": self.artifact.to_json(),
            "prediction": self.prediction.to_json(),
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class PredictiveModelEvaluation:
    """Chronological split and metric records for one model calculation."""

    mode: EvaluationMode
    splits: tuple[PredictiveModelSplit, ...]
    period_metrics: tuple[PredictiveModelPeriodMetrics, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    folds: tuple[PredictiveModelFold, ...] = ()
    benchmark: NaiveBenchmarkEvaluation | None = None
    is_eligible_for_strategy: bool = False
    eligibility_reason: str = (
        "Predictive Model is not eligible for a Strategy until the naive benchmark "
        "comparison is complete."
    )

    def to_json(self) -> dict[str, JsonValue]:
        """Return the complete evaluation record for a Run manifest."""
        return {
            "mode": self.mode,
            "splits": [split.to_json() for split in self.splits],
            "period_metrics": [metrics.to_json() for metrics in self.period_metrics],
            "folds": [fold.to_json() for fold in self.folds],
            "benchmark": self.benchmark.to_json() if self.benchmark else None,
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "unsupported_claims": list(self.unsupported_claims),
            "is_eligible_for_strategy": self.is_eligible_for_strategy,
            "eligibility_reason": self.eligibility_reason,
            "leakage_policy": {
                "initial_feature_and_preprocessing_fit_scope": "training_only",
                "future_labels_excluded_from_each_training_window": True,
                "validation_and_test_labels_excluded_from_initial_training": True,
                "fold_training_eligibility": (
                    "feature_session_before_prediction_session_and_label_available_by_"
                    "prediction_session"
                ),
                "fold_feature_and_preprocessing_policy": (
                    "causal_features_from_session_history_and_learned_state_fit_on_"
                    "each_fold_training_window"
                ),
            },
        }


@dataclass(frozen=True)
class PredictiveModelCalculation:
    """Complete calculation result before optional Project persistence."""

    metadata: PredictiveModelMetadata
    artifact: FittedModelArtifact
    parameters: dict[str, JsonValue]
    seed: int | None
    predictions: list[PredictiveModelOutput]
    metrics: dict[str, float]
    training_start: str
    training_end: str
    out_of_sample_status: str
    evaluation: PredictiveModelEvaluation
    fold_artifacts: list[FittedModelArtifact] = field(default_factory=list)


FitFunction = Callable[
    [pd.DataFrame, dict[str, JsonValue], int | None], FittedModelArtifact
]
PredictFunction = Callable[
    [FittedModelArtifact, pd.DataFrame], list[PredictiveModelOutput]
]


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
            closes[index + horizon] / closes[index] - 1.0
            if index + horizon < len(closes)
            else None
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

            # 1. Inverse statistics: shortest waiting time to drop <= -threshold_return from any peak
            # vs shortest waiting time to gain >= +threshold_return from any trough
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
            closes[index + horizon] / closes[index] - 1.0
            if index + horizon < len(closes)
            else None
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


def _resolve_parameters(
    name: str, parameters: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
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

    usable = training_frame.dropna(
        subset=["momentum", "next_session_return"]
    ).reset_index(drop=True)
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
        (target - fitted) ** 2
        for target, fitted in zip(targets, fitted_values, strict=True)
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
            "Training data must contain session_date, potts_gain_loss_score, and next_session_return."
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
        (target - fitted) ** 2
        for target, fitted in zip(targets, fitted_values, strict=True)
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
            features=("potts_gain_loss_score", "gain_loss_asymmetry_ratio", "potts_order_parameter"),
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
                    description="Number of sessions used to calculate inverse waiting times and return state bins.",
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


def _split_period(
    period: SplitName,
    frame: pd.DataFrame,
    fit_scope: str,
) -> PredictiveModelSplit:
    """Describe one non-empty labelled period using target and feature dates."""
    if frame.empty:
        raise PredictiveModelCalculationError(f"The {period} period must not be empty.")
    return PredictiveModelSplit(
        period=period,
        start=str(frame["target_date"].iloc[0]),
        end=str(frame["target_date"].iloc[-1]),
        feature_start=str(frame["session_date"].iloc[0]),
        feature_end=str(frame["session_date"].iloc[-1]),
        observations=len(frame),
        labelled_observations=len(frame),
        fit_scope=fit_scope,
    )


@dataclass(frozen=True)
class PredictiveModelChronologicalSplit:
    """Named result of the chronological frame split."""

    frames: dict[SplitName, pd.DataFrame]
    periods: tuple[PredictiveModelSplit, ...]


@dataclass(frozen=True)
class PredictiveModelSplitParameters:
    """Configuration used to build one chronological evaluation split."""

    training_window: int
    validation_fraction: float
    test_fraction: float
    evaluation_mode: EvaluationMode


def _chronological_split(
    frame: pd.DataFrame,
    parameters: PredictiveModelSplitParameters,
    feature_column: str = "momentum",
) -> PredictiveModelChronologicalSplit:
    """Split labelled rows in target-date order without shuffling or future labels."""
    labelled = (
        frame.dropna(subset=[feature_column, "next_session_return", "target_date"])
        .sort_values("target_date")
        .reset_index(drop=True)
    )
    validation_size = max(1, math.ceil(len(labelled) * parameters.validation_fraction))
    test_size = max(1, math.ceil(len(labelled) * parameters.test_fraction))
    training_size = len(labelled) - validation_size - test_size
    if training_size < 2:
        raise PredictiveModelCalculationError(
            "At least two labelled training observations and one validation and test "
            "observation are required for chronological evaluation."
        )

    training_pool = labelled.iloc[:training_size]
    training = training_pool.tail(parameters.training_window).reset_index(drop=True)
    validation_start = training_size
    validation_end = validation_start + validation_size
    validation = labelled.iloc[validation_start:validation_end].reset_index(drop=True)
    test = labelled.iloc[validation_end:].reset_index(drop=True)
    if validation.empty or test.empty:
        raise PredictiveModelCalculationError(
            "Chronological evaluation requires non-empty validation and test periods."
        )

    fit_scopes = {
        "training": "training_only",
        "validation": (
            "training_only"
            if parameters.evaluation_mode == "holdout"
            else "prior_observations_before_target"
            if parameters.evaluation_mode == "expanding"
            else "rolling_window_before_target"
        ),
        "test": (
            "training_only"
            if parameters.evaluation_mode == "holdout"
            else "prior_observations_before_target"
            if parameters.evaluation_mode == "expanding"
            else "rolling_window_before_target"
        ),
    }
    periods = (
        _split_period("training", training, fit_scopes["training"]),
        _split_period("validation", validation, fit_scopes["validation"]),
        _split_period("test", test, fit_scopes["test"]),
    )
    if not (
        periods[0].end < periods[1].start
        and periods[1].end < periods[2].start
    ):
        raise PredictiveModelCalculationError(
            "Training, validation, and test target periods must be strictly chronological."
        )
    return PredictiveModelChronologicalSplit(
        frames={
            "training": training,
            "validation": validation,
            "test": test,
        },
        periods=periods,
    )


def _eligible_training_frame(
    labelled_frame: pd.DataFrame,
    policy: PredictiveModelFoldTrainingPolicy,
) -> pd.DataFrame:
    """Return labels known before a prediction session for one walk-forward fold."""
    eligible = labelled_frame.loc[
        (labelled_frame["session_date"] < policy.decision_session_date)
        & (labelled_frame["target_date"] <= policy.decision_session_date)
    ]
    if policy.evaluation_mode == "expanding":
        eligible = eligible.loc[
            eligible["session_date"] >= policy.initial_training_start
        ]
    else:
        eligible = eligible.tail(policy.training_window)
    eligible = eligible.reset_index(drop=True)
    if len(eligible) < 2:
        raise PredictiveModelCalculationError(
            "Each walk-forward fold requires at least two eligible training observations."
        )
    return eligible


def _evaluate_period_metrics(
    period: SplitName,
    predictions: Sequence[PredictiveModelOutput],
    benchmark_predictions: Sequence[NaiveBenchmarkPrediction],
) -> PredictiveModelPeriodMetrics:
    """Calculate labelled model and naive benchmark metrics for one chronological period."""
    if period == "training":
        sample_scope: SampleScope = "in_sample"
    elif period == "validation":
        sample_scope = "validation"
    else:
        sample_scope = "out_of_sample"
    labelled = [
        prediction
        for prediction in predictions
        if isinstance(prediction, PredictiveModelPrediction)
    ]
    labelled_keys = [
        (prediction.session_date, prediction.target_date) for prediction in labelled
    ]
    benchmark_keys = [
        (session_date, target_date)
        for session_date, target_date, _ in benchmark_predictions
    ]
    same_eligible_periods = benchmark_keys == labelled_keys
    if not same_eligible_periods:
        raise PredictiveModelCalculationError(
            f"The naive benchmark periods do not match the labelled {period} "
            "prediction periods."
        )
    if len(benchmark_predictions) != len(labelled):
        raise PredictiveModelCalculationError(
            f"The naive benchmark produced {len(benchmark_predictions)} observations "
            f"for {len(labelled)} labelled {period} predictions."
        )
    if not labelled:
        return PredictiveModelPeriodMetrics(
            period=period,
            observations=0,
            metrics={},
            benchmark_metrics={},
            comparison={},
            sample_scope=sample_scope,
        )

    actuals = [float(prediction.actual_target) for prediction in labelled]
    model_preds = [float(prediction.predicted_value) for prediction in labelled]
    bench_preds = [float(value) for _, _, value in benchmark_predictions]
    if any(not math.isfinite(value) for value in actuals + model_preds + bench_preds):
        raise PredictiveModelCalculationError(
            f"The {period} model and benchmark metrics require finite values."
        )

    model_errors = [m - a for m, a in zip(model_preds, actuals, strict=True)]
    bench_errors = [b - a for b, a in zip(bench_preds, actuals, strict=True)]

    actual_mean = sum(actuals) / len(actuals)
    total_sum = sum((a - actual_mean) ** 2 for a in actuals)

    model_residual_sum = sum(e * e for e in model_errors)
    model_mae = sum(abs(e) for e in model_errors) / len(model_errors)
    model_rmse = math.sqrt(model_residual_sum / len(model_errors))
    model_r2 = 1.0 - model_residual_sum / total_sum if total_sum > 1e-15 else 0.0

    bench_residual_sum = sum(e * e for e in bench_errors)
    bench_mae = sum(abs(e) for e in bench_errors) / len(bench_errors)
    bench_rmse = math.sqrt(bench_residual_sum / len(bench_errors))
    bench_r2 = 1.0 - bench_residual_sum / total_sum if total_sum > 1e-15 else 0.0

    rmse_ratio = model_rmse / bench_rmse if bench_rmse > 1e-15 else 1.0
    mae_ratio = model_mae / bench_mae if bench_mae > 1e-15 else 1.0
    rmse_improvement = 1.0 - rmse_ratio if bench_rmse > 1e-15 else 0.0
    mae_improvement = 1.0 - mae_ratio if bench_mae > 1e-15 else 0.0
    outperforms_benchmark = bool(model_rmse < bench_rmse)

    return PredictiveModelPeriodMetrics(
        period=period,
        observations=len(labelled),
        metrics={
            "mae": model_mae,
            "rmse": model_rmse,
            "r2": model_r2,
        },
        benchmark_metrics={
            "mae": bench_mae,
            "rmse": bench_rmse,
            "r2": bench_r2,
        },
        comparison={
            "rmse_ratio": rmse_ratio,
            "mae_ratio": mae_ratio,
            "rmse_improvement": rmse_improvement,
            "mae_improvement": mae_improvement,
            "outperforms_benchmark": outperforms_benchmark,
            "same_eligible_periods": same_eligible_periods,
        },
        sample_scope=sample_scope,
    )


def _fold_metrics(prediction: PredictiveModelOutput) -> dict[str, float]:
    """Return honest single-observation errors for one walk-forward fold."""
    if not isinstance(prediction, PredictiveModelPrediction):
        return {}
    error = float(prediction.predicted_value) - float(prediction.actual_target)
    absolute_error = abs(error)
    return {"mae": absolute_error, "rmse": absolute_error}


def _labelled_predictions(
    predictions: Sequence[PredictiveModelOutput],
    period: SplitName,
) -> list[PredictiveModelPrediction]:
    return [
        prediction
        for prediction in predictions
        if isinstance(prediction, PredictiveModelPrediction)
        and prediction.period == period
    ]


def _benchmark_prediction(
    session_date: str,
    target_date: str | None,
    value: float,
) -> NaiveBenchmarkPrediction:
    """Return a benchmark forecast with the exact session and target keys."""
    return session_date, target_date, float(value)


def run_predictive_model(
    name: str,
    bars: Sequence[DailyBar],
    parameters: Mapping[str, JsonValue],
    seed: int | None = None,
) -> PredictiveModelCalculation:
    """Build, fit, and evaluate one deterministic chronological model calculation."""
    spec = get_predictive_model_spec(name)
    resolved_parameters = _resolve_parameters(name, parameters)
    training_window = int(resolved_parameters["training_window"])
    validation_fraction = float(resolved_parameters["validation_fraction"])
    test_fraction = float(resolved_parameters["test_fraction"])
    raw_evaluation_mode = resolved_parameters["evaluation_mode"]
    if raw_evaluation_mode not in ("holdout", "expanding", "rolling"):
        raise PredictiveModelParameterError(
            "evaluation_mode must be one of: holdout, expanding, rolling."
        )
    evaluation_mode: EvaluationMode = raw_evaluation_mode
    raw_benchmark_name = str(resolved_parameters.get("naive_benchmark", "zero_return"))
    if raw_benchmark_name not in _NAIVE_BENCHMARKS:
        raise PredictiveModelParameterError(
            "naive_benchmark must be one of: zero_return, historical_mean, persistence."
        )
    naive_benchmark_name = raw_benchmark_name
    benchmark_spec = _NAIVE_BENCHMARKS[naive_benchmark_name]

    if name == "momentum_return_regression":
        momentum_period = int(resolved_parameters["momentum_period"])
        frame = build_supervised_frame(
            bars,
            momentum_period=momentum_period,
            horizon=spec.horizon,
        )
        feature_col = "momentum"
        model_assumptions = _MOMENTUM_MODEL_ASSUMPTIONS
        model_warnings = _MOMENTUM_MODEL_WARNINGS
        model_limitations = _MOMENTUM_MODEL_LIMITATIONS
        model_unsupported = _MOMENTUM_MODEL_UNSUPPORTED_CLAIMS
    elif name == "potts_gain_loss_asymmetry":
        potts_cfg = PottsGainLossParameters(
            threshold_return=float(resolved_parameters["threshold_return"]),
            lookback_window=int(resolved_parameters["lookback_window"]),
            q_states=int(resolved_parameters["q_states"]),
            training_window=training_window,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
            evaluation_mode=evaluation_mode,
            naive_benchmark=naive_benchmark_name,
        )
        frame = build_potts_supervised_frame(
            bars,
            config=potts_cfg,
            horizon=spec.horizon,
        )
        feature_col = "potts_gain_loss_score"
        model_assumptions = _POTTS_MODEL_ASSUMPTIONS
        model_warnings = _POTTS_MODEL_WARNINGS
        model_limitations = _POTTS_MODEL_LIMITATIONS
        model_unsupported = _POTTS_MODEL_UNSUPPORTED_CLAIMS
    else:
        raise PredictiveModelNotFoundError(f"Unknown Predictive Model '{name}'.")

    chronological_split = _chronological_split(
        frame,
        PredictiveModelSplitParameters(
            training_window=training_window,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
            evaluation_mode=evaluation_mode,
        ),
        feature_column=feature_col,
    )

    # Build prior realized return lookup for persistence benchmark
    sorted_bars = sorted(bars, key=lambda b: b.session_date)
    prior_returns: dict[str, float] = {}
    for i, bar in enumerate(sorted_bars):
        if i > 0 and sorted_bars[i - 1].close > 0:
            prior_returns[bar.session_date] = (bar.close / sorted_bars[i - 1].close) - 1.0
        else:
            prior_returns[bar.session_date] = 0.0

    split_frames = chronological_split.frames
    training_frame = split_frames["training"]
    artifact = fit_model(name, training_frame, resolved_parameters, seed)
    labelled_frame = (
        frame.dropna(subset=[feature_col, "next_session_return", "target_date"])
        .sort_values("target_date")
        .reset_index(drop=True)
    )
    period_by_target: dict[str, SplitName] = {}
    for period_name in ("training", "validation", "test"):
        period_frame = split_frames[period_name]
        for target_date in period_frame["target_date"].tolist():
            period_by_target[str(target_date)] = period_name

    training_targets = [float(t) for t in training_frame["next_session_return"].tolist()]

    prediction_by_session: dict[str, PredictiveModelOutput] = {}
    fold_artifacts = [artifact]
    fold_records: list[PredictiveModelFold] = []
    validation_bench_preds: list[NaiveBenchmarkPrediction] = []
    test_bench_preds: list[NaiveBenchmarkPrediction] = []

    if evaluation_mode == "holdout":
        evaluated_predictions = predict(artifact, frame)
        prediction_by_session = {
            prediction.session_date: prediction for prediction in evaluated_predictions
        }
        for period_name, bench_list in (
            ("validation", validation_bench_preds),
            ("test", test_bench_preds),
        ):
            period_frame = split_frames[period_name]
            for _, row in period_frame.iterrows():
                session_date = str(row["session_date"])
                bench_list.append(
                    _benchmark_prediction(
                        session_date,
                        str(row["target_date"]),
                        benchmark_spec.predict(
                            session_date, training_targets, prior_returns
                        ),
                    )
                )
    else:
        initial_training_start = artifact.training_start
        fit_scope_by_period = {
            split.period: split.fit_scope for split in chronological_split.periods
        }
        fold_index = 1
        for period_name in ("validation", "test"):
            period_frame = split_frames[period_name]
            target_bench_list = (
                validation_bench_preds if period_name == "validation" else test_bench_preds
            )
            for _, row in period_frame.iterrows():
                prediction_session_date = str(row["session_date"])
                fitting_frame = _eligible_training_frame(
                    labelled_frame,
                    PredictiveModelFoldTrainingPolicy(
                        decision_session_date=prediction_session_date,
                        initial_training_start=initial_training_start,
                        training_window=training_window,
                        evaluation_mode=evaluation_mode,
                    ),
                )
                fold_artifact = fit_model(name, fitting_frame, resolved_parameters, seed)
                fold_artifacts.append(fold_artifact)
                fold_prediction = predict(fold_artifact, pd.DataFrame([row]))
                if not fold_prediction:
                    raise PredictiveModelCalculationError(
                        f"No prediction was produced for {period_name} session "
                        f"{prediction_session_date}."
                    )
                raw_prediction = fold_prediction[0]
                prediction = (
                    replace(raw_prediction, period=period_name)
                    if isinstance(raw_prediction, PredictiveModelPrediction)
                    else raw_prediction
                )
                prediction_by_session[prediction.session_date] = prediction

                fold_targets = [
                    float(t) for t in fitting_frame["next_session_return"].tolist()
                ]
                target_bench_list.append(
                    _benchmark_prediction(
                        prediction_session_date,
                        str(row["target_date"]),
                        benchmark_spec.predict(
                            prediction_session_date,
                            fold_targets,
                            prior_returns,
                        ),
                    )
                )

                fold_records.append(
                    PredictiveModelFold(
                        fold_index=fold_index,
                        period=period_name,
                        prediction_session_date=prediction.session_date,
                        target_date=(
                            prediction.target_date
                            if isinstance(prediction, PredictiveModelPrediction)
                            else None
                        ),
                        training_start=fold_artifact.training_start,
                        training_end=fold_artifact.training_end,
                        training_observations=fold_artifact.training_observations,
                        fit_scope=fit_scope_by_period[period_name],
                        artifact=fold_artifact,
                        prediction=prediction,
                        metrics=_fold_metrics(prediction),
                    )
                )
                fold_index += 1

    final_artifact = fold_artifacts[-1]
    predictions: list[PredictiveModelOutput] = []
    for _, row in frame.iterrows():
        session_date = str(row["session_date"])
        if session_date <= artifact.training_end:
            continue
        prediction = prediction_by_session.get(session_date)
        if prediction is None:
            final_prediction = predict(final_artifact, pd.DataFrame([row]))
            if not final_prediction:
                continue
            prediction = final_prediction[0]
        if isinstance(prediction, PredictiveModelPrediction):
            period = prediction.period or period_by_target.get(prediction.target_date)
            predictions.append(replace(prediction, period=period))
        else:
            predictions.append(prediction)

    # Training benchmark predictions
    training_bench_preds: list[NaiveBenchmarkPrediction] = []
    for _, row in training_frame.iterrows():
        session_date = str(row["session_date"])
        training_bench_preds.append(
            _benchmark_prediction(
                session_date,
                str(row["target_date"]),
                benchmark_spec.predict(session_date, training_targets, prior_returns),
            )
        )

    training_model_predictions = [
        replace(p, period="training")
        for p in predict(artifact, training_frame)
        if isinstance(p, PredictiveModelPrediction)
    ]
    training_period_metric = _evaluate_period_metrics(
        "training", training_model_predictions, training_bench_preds
    )
    validation_period_metric = _evaluate_period_metrics(
        "validation",
        _labelled_predictions(predictions, "validation"),
        validation_bench_preds,
    )
    test_period_metric = _evaluate_period_metrics(
        "test",
        _labelled_predictions(predictions, "test"),
        test_bench_preds,
    )

    period_metrics = (
        training_period_metric,
        validation_period_metric,
        test_period_metric,
    )

    out_of_sample_comparison: dict[str, JsonValue] = {
        "benchmark_name": naive_benchmark_name,
        "period": "test",
        "sample_scope": "out_of_sample",
        "observations": test_period_metric.observations,
        "same_eligible_periods": test_period_metric.comparison.get(
            "same_eligible_periods", False
        ),
        "model_rmse": test_period_metric.metrics.get("rmse", 0.0),
        "benchmark_rmse": test_period_metric.benchmark_metrics.get("rmse", 0.0),
        "rmse_improvement": test_period_metric.comparison.get("rmse_improvement", 0.0),
        "model_mae": test_period_metric.metrics.get("mae", 0.0),
        "benchmark_mae": test_period_metric.benchmark_metrics.get("mae", 0.0),
        "mae_improvement": test_period_metric.comparison.get("mae_improvement", 0.0),
        "model_r2": test_period_metric.metrics.get("r2", 0.0),
        "benchmark_r2": test_period_metric.benchmark_metrics.get("r2", 0.0),
        "outperforms_benchmark": test_period_metric.comparison.get(
            "outperforms_benchmark", False
        ),
        "status": "evaluated",
        "comparison_complete": True,
    }

    if test_period_metric.observations == 0:
        raise PredictiveModelCalculationError(
            "The out-of-sample test period has no labelled observations for benchmark "
            "comparison."
        )

    benchmark_eval = NaiveBenchmarkEvaluation(
        name=naive_benchmark_name,
        display_name=benchmark_spec.display_name,
        description=benchmark_spec.description,
        period_metrics={pm.period: pm.benchmark_metrics for pm in period_metrics},
        out_of_sample_comparison=out_of_sample_comparison,
        completed=True,
    )

    metrics: dict[str, float] = {
        metric_name: float(metric_value)
        for metric_name, metric_value in artifact.training_metrics.items()
        if isinstance(metric_value, (int, float))
    }
    for period_metric in period_metrics:
        for metric_name, metric_value in period_metric.metrics.items():
            metrics[f"{period_metric.period}_{metric_name}"] = float(metric_value)
        for metric_name, metric_value in period_metric.benchmark_metrics.items():
            metrics[f"{period_metric.period}_benchmark_{metric_name}"] = float(metric_value)
        for metric_name, metric_value in period_metric.comparison.items():
            if isinstance(metric_value, (int, float)):
                metrics[f"{period_metric.period}_{metric_name}"] = float(metric_value)

    is_eligible = bool(
        benchmark_eval.completed
        and test_period_metric.observations > 0
        and out_of_sample_comparison.get("comparison_complete") is True
        and out_of_sample_comparison.get("same_eligible_periods") is True
    )
    eligibility_reason = (
        "Naive benchmark comparison is complete on the labelled out-of-sample test period."
        if is_eligible
        else "Naive benchmark comparison is incomplete or missing labelled out-of-sample data."
    )

    evaluation = PredictiveModelEvaluation(
        mode=evaluation_mode,
        splits=chronological_split.periods,
        period_metrics=period_metrics,
        folds=tuple(fold_records),
        benchmark=benchmark_eval,
        assumptions=model_assumptions,
        warnings=model_warnings,
        limitations=model_limitations,
        unsupported_claims=model_unsupported,
        is_eligible_for_strategy=is_eligible,
        eligibility_reason=eligibility_reason,
    )
    return PredictiveModelCalculation(
        metadata=spec.metadata,
        artifact=artifact,
        parameters=resolved_parameters,
        seed=seed,
        predictions=predictions,
        metrics=metrics,
        training_start=artifact.training_start,
        training_end=artifact.training_end,
        out_of_sample_status="available",
        evaluation=evaluation,
        fold_artifacts=fold_artifacts,
    )
