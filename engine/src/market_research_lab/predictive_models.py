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

    def to_json(self) -> dict[str, JsonValue]:
        """Return period-labelled metrics for artifacts and interface responses."""
        return {
            "period": self.period,
            "observations": self.observations,
            "metrics": self.metrics,
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
    folds: tuple[PredictiveModelFold, ...] = ()

    def to_json(self) -> dict[str, JsonValue]:
        """Return the complete evaluation record for a Run manifest."""
        return {
            "mode": self.mode,
            "splits": [split.to_json() for split in self.splits],
            "period_metrics": [metrics.to_json() for metrics in self.period_metrics],
            "folds": [fold.to_json() for fold in self.folds],
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

    @model_validator(mode="after")
    def leaves_training_observations(self) -> "MomentumRegressionParameters":
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


def _resolve_parameters(
    name: str, parameters: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    if name != "momentum_return_regression":
        raise PredictiveModelNotFoundError(f"Unknown Predictive Model '{name}'.")
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
    }


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
    naive_rmse = math.sqrt(
        sum((target - target_mean) ** 2 for target in targets) / len(targets)
    )
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
            "naive_benchmark_rmse": naive_rmse,
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
    )
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
) -> PredictiveModelChronologicalSplit:
    """Split labelled rows in target-date order without shuffling or future labels."""
    labelled = (
        frame.dropna(subset=["momentum", "next_session_return", "target_date"])
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


def _period_metrics(
    period: SplitName,
    predictions: Sequence[PredictiveModelOutput],
) -> PredictiveModelPeriodMetrics:
    """Calculate labelled metrics for one period without touching other periods."""
    labelled = [
        prediction
        for prediction in predictions
        if isinstance(prediction, PredictiveModelPrediction)
    ]
    if not labelled:
        return PredictiveModelPeriodMetrics(period=period, observations=0, metrics={})

    actuals = [float(prediction.actual_target) for prediction in labelled]
    errors = [
        float(prediction.predicted_value) - actual
        for prediction, actual in zip(labelled, actuals, strict=True)
    ]
    actual_mean = sum(actuals) / len(actuals)
    residual_sum = sum(error * error for error in errors)
    total_sum = sum((actual - actual_mean) ** 2 for actual in actuals)
    return PredictiveModelPeriodMetrics(
        period=period,
        observations=len(labelled),
        metrics={
            "mae": sum(abs(error) for error in errors) / len(errors),
            "rmse": math.sqrt(residual_sum / len(errors)),
            "r2": 1.0 - residual_sum / total_sum if total_sum > 1e-15 else 0.0,
        },
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


def run_predictive_model(
    name: str,
    bars: Sequence[DailyBar],
    parameters: Mapping[str, JsonValue],
    seed: int | None = None,
) -> PredictiveModelCalculation:
    """Build, fit, and evaluate one deterministic chronological model calculation."""
    spec = get_predictive_model_spec(name)
    resolved_parameters = _resolve_parameters(name, parameters)
    momentum_period = int(resolved_parameters["momentum_period"])
    training_window = int(resolved_parameters["training_window"])
    validation_fraction = float(resolved_parameters["validation_fraction"])
    test_fraction = float(resolved_parameters["test_fraction"])
    raw_evaluation_mode = resolved_parameters["evaluation_mode"]
    if raw_evaluation_mode not in ("holdout", "expanding", "rolling"):
        raise PredictiveModelParameterError(
            "evaluation_mode must be one of: holdout, expanding, rolling."
        )
    evaluation_mode: EvaluationMode = raw_evaluation_mode
    frame = build_supervised_frame(
        bars,
        momentum_period=momentum_period,
        horizon=spec.horizon,
    )
    chronological_split = _chronological_split(
        frame,
        PredictiveModelSplitParameters(
            training_window=training_window,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
            evaluation_mode=evaluation_mode,
        ),
    )

    split_frames = chronological_split.frames
    training_frame = split_frames["training"]
    artifact = fit_model(name, training_frame, resolved_parameters, seed)
    labelled_frame = (
        frame.dropna(subset=["momentum", "next_session_return", "target_date"])
        .sort_values("target_date")
        .reset_index(drop=True)
    )
    period_by_target: dict[str, SplitName] = {}
    for period_name in ("training", "validation", "test"):
        period_frame = split_frames[period_name]
        for target_date in period_frame["target_date"].tolist():
            period_by_target[str(target_date)] = period_name

    prediction_by_session: dict[str, PredictiveModelOutput] = {}
    fold_artifacts = [artifact]
    fold_records: list[PredictiveModelFold] = []
    if evaluation_mode == "holdout":
        evaluated_predictions = predict(artifact, frame)
        prediction_by_session = {
            prediction.session_date: prediction for prediction in evaluated_predictions
        }
    else:
        initial_training_start = artifact.training_start
        fit_scope_by_period = {
            split.period: split.fit_scope for split in chronological_split.periods
        }
        fold_index = 1
        for period_name in ("validation", "test"):
            period_frame = split_frames[period_name]
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

    training_metrics = {
        "r2": float(artifact.training_metrics["in_sample_r2"]),
        "rmse": float(artifact.training_metrics["in_sample_rmse"]),
        "naive_rmse": float(artifact.training_metrics["naive_benchmark_rmse"]),
    }
    period_metrics = (
        PredictiveModelPeriodMetrics(
            period="training",
            observations=len(training_frame),
            metrics=training_metrics,
        ),
        _period_metrics("validation", _labelled_predictions(predictions, "validation")),
        _period_metrics("test", _labelled_predictions(predictions, "test")),
    )
    metrics = {
        metric_name: float(metric_value)
        for metric_name, metric_value in artifact.training_metrics.items()
        if isinstance(metric_value, (int, float))
    }
    for period_metric in period_metrics:
        for metric_name, metric_value in period_metric.metrics.items():
            metrics[f"{period_metric.period}_{metric_name}"] = float(metric_value)

    evaluation = PredictiveModelEvaluation(
        mode=evaluation_mode,
        splits=chronological_split.periods,
        period_metrics=period_metrics,
        folds=tuple(fold_records),
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
