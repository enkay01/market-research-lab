"""Typed, deterministic Predictive Model definitions and execution seams."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .json_types import JsonValue
from .market_data import DailyBar


class PredictiveModelError(ValueError):
    """Base error for Predictive Model discovery, validation, and calculation."""


class PredictiveModelNotFoundError(PredictiveModelError):
    """Raised when a requested Predictive Model is not registered."""


class PredictiveModelParameterError(PredictiveModelError):
    """Raised when a Predictive Model parameter is invalid."""


class PredictiveModelCalculationError(PredictiveModelError):
    """Raised when a Predictive Model cannot be fitted on the supplied data."""


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
        }


@dataclass(frozen=True)
class PredictiveModelPrediction:
    """One time-stamped model output aligned to an eligible session."""

    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: float | None

    def to_json(self) -> dict[str, JsonValue]:
        """Return this prediction as a JSON-compatible object."""
        return {
            "session_date": self.session_date,
            "feature_value": self.feature_value,
            "predicted_value": self.predicted_value,
            "actual_target": self.actual_target,
        }


@dataclass(frozen=True)
class PredictiveModelCalculation:
    """Complete calculation result before optional Project persistence."""

    metadata: PredictiveModelMetadata
    artifact: FittedModelArtifact
    parameters: dict[str, JsonValue]
    seed: int | None
    predictions: list[PredictiveModelPrediction]
    metrics: dict[str, float]
    training_start: str
    training_end: str
    out_of_sample_status: str


FitFunction = Callable[
    [pd.DataFrame, dict[str, JsonValue], int | None], FittedModelArtifact
]
PredictFunction = Callable[
    [FittedModelArtifact, pd.DataFrame], list[PredictiveModelPrediction]
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
        rows.append(
            {
                "session_date": bar.session_date,
                "momentum": momentum,
                "next_session_return": next_return,
            }
        )

    return pd.DataFrame(
        rows,
        columns=["session_date", "momentum", "next_session_return"],
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

    return FittedModelArtifact(
        model_name="momentum_return_regression",
        feature_name="trailing_close_momentum",
        target_name="next_session_return",
        horizon=1,
        intercept=intercept,
        coefficient=coefficient,
        training_start=str(usable.loc[0, "session_date"]),
        training_end=str(usable.loc[len(usable) - 1, "session_date"]),
        training_observations=len(usable),
        parameters=parameters,
        seed=seed,
        training_metrics={
            "in_sample_r2": in_sample_r2,
            "in_sample_rmse": in_sample_rmse,
            "naive_benchmark_rmse": naive_rmse,
        },
    )


def _predict_momentum_regression(
    artifact: FittedModelArtifact, eligible_frame: pd.DataFrame
) -> list[PredictiveModelPrediction]:
    if not {"session_date", "momentum"}.issubset(eligible_frame.columns):
        raise PredictiveModelCalculationError(
            "Prediction data must contain session_date and momentum."
        )

    target_values = (
        eligible_frame["next_session_return"].tolist()
        if "next_session_return" in eligible_frame.columns
        else [None] * len(eligible_frame)
    )
    predictions: list[PredictiveModelPrediction] = []
    for date, feature, target in zip(
        eligible_frame["session_date"].tolist(),
        eligible_frame["momentum"].tolist(),
        target_values,
        strict=True,
    ):
        if pd.isna(feature):
            continue
        feature_value = float(feature)
        actual_target = None if pd.isna(target) else float(target)
        predictions.append(
            PredictiveModelPrediction(
                session_date=str(date),
                feature_value=feature_value,
                predicted_value=artifact.intercept + artifact.coefficient * feature_value,
                actual_target=actual_target,
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
                    description="Maximum number of latest labelled observations used for fitting.",
                    min_value=2,
                    max_value=10_000,
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
    """Fit a registered Predictive Model on an already-bounded training frame."""
    if seed is not None and (isinstance(seed, bool) or seed < 0):
        raise PredictiveModelParameterError("seed must be a non-negative integer when supplied.")
    spec = get_predictive_model_spec(name)
    resolved_parameters = _resolve_parameters(name, parameters)
    return spec.fit(training_frame, resolved_parameters, seed)


def predict(
    artifact: FittedModelArtifact, eligible_frame: pd.DataFrame
) -> list[PredictiveModelPrediction]:
    """Predict from a fitted artifact using only the supplied eligible feature frame."""
    spec = get_predictive_model_spec(artifact.model_name)
    return spec.predict(artifact, eligible_frame)


def run_predictive_model(
    name: str,
    bars: Sequence[DailyBar],
    parameters: Mapping[str, JsonValue],
    seed: int | None = None,
) -> PredictiveModelCalculation:
    """Build, fit, and predict one deterministic Predictive Model calculation."""
    spec = get_predictive_model_spec(name)
    resolved_parameters = _resolve_parameters(name, parameters)
    momentum_period = int(resolved_parameters["momentum_period"])
    training_window = int(resolved_parameters["training_window"])
    frame = build_supervised_frame(
        bars,
        momentum_period=momentum_period,
        horizon=spec.horizon,
    )
    training_frame = frame.dropna(subset=["momentum", "next_session_return"]).tail(
        training_window
    )
    if len(training_frame) < 2:
        raise PredictiveModelCalculationError(
            "At least two labelled training observations are required after applying "
            f"momentum_period={momentum_period} and training_window={training_window}."
        )

    artifact = fit_model(name, training_frame, resolved_parameters, seed)
    predictions = predict(artifact, frame)
    metrics = {
        metric_name: float(metric_value)
        for metric_name, metric_value in artifact.training_metrics.items()
        if isinstance(metric_value, (int, float))
    }
    return PredictiveModelCalculation(
        metadata=spec.metadata,
        artifact=artifact,
        parameters=resolved_parameters,
        seed=seed,
        predictions=predictions,
        metrics=metrics,
        training_start=artifact.training_start,
        training_end=artifact.training_end,
        out_of_sample_status="not_available_until_chronological_splits",
    )
