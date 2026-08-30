"""Leakage-safe chronological evaluation for Predictive Models.

This module owns split construction, fold training, benchmark forecasts, and
metric calculation. Model definitions only provide supervised data, fit, and
forecast callables.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

import pandas as pd

from .json_types import JsonValue
from .market_data import DailyBar

if TYPE_CHECKING:
    from .predictive_models import (
        FittedModelArtifact,
        PredictiveModelCalculation,
        PredictiveModelFold,
        PredictiveModelOutput,
        PredictiveModelPeriodMetrics,
        PredictiveModelSplit,
    )

EvaluationMode = Literal["holdout", "expanding", "rolling"]
NaiveBenchmarkName = Literal["zero_return", "historical_mean", "persistence"]

NaiveBenchmarkPredictor = Callable[[str, Sequence[float], Mapping[str, float]], float]


@dataclass(frozen=True)
class NaiveBenchmarkSpec:
    name: NaiveBenchmarkName
    display_name: str
    description: str
    predict: NaiveBenchmarkPredictor


def _zero_return(_: str, __: Sequence[float], ___: Mapping[str, float]) -> float:
    return 0.0


def _historical_mean(_: str, targets: Sequence[float], __: Mapping[str, float]) -> float:
    return sum(targets) / len(targets) if targets else 0.0


def _persistence(session_date: str, _: Sequence[float], prior: Mapping[str, float]) -> float:
    return float(prior.get(session_date, 0.0))


NAIVE_BENCHMARKS: dict[NaiveBenchmarkName, NaiveBenchmarkSpec] = {
    "zero_return": NaiveBenchmarkSpec(
        "zero_return", "Zero Return Benchmark", "Unconditional zero-return forecast.", _zero_return
    ),
    "historical_mean": NaiveBenchmarkSpec(
        "historical_mean",
        "Historical Mean Benchmark",
        "Constant forecast equal to the eligible training mean.",
        _historical_mean,
    ),
    "persistence": NaiveBenchmarkSpec(
        "persistence",
        "Persistence Benchmark",
        "Forecast using the most recent observed return.",
        _persistence,
    ),
}


@dataclass(frozen=True)
class ModelEvaluationParameters:
    """All options and data needed for one deterministic evaluation."""

    training_window: int
    validation_fraction: float
    test_fraction: float
    evaluation_mode: EvaluationMode
    naive_benchmark: NaiveBenchmarkName


@dataclass(frozen=True)
class ModelEvaluationInput:
    """Typed input boundary for the evaluation runner."""

    name: str
    frame: pd.DataFrame
    feature_column: str
    bars: Sequence[DailyBar]
    parameters: Mapping[str, JsonValue]
    seed: int | None
    fit: Callable[[pd.DataFrame, dict[str, JsonValue], int | None], "FittedModelArtifact"]
    forecast: Callable[["FittedModelArtifact", pd.DataFrame], list["PredictiveModelOutput"]]
    metadata: object
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    unsupported_claims: tuple[str, ...]


@dataclass(frozen=True)
class _RegressionMetrics:
    mae: float
    rmse: float
    r2: float


def evaluate_period_metrics(
    period: str,
    predictions: Sequence["PredictiveModelOutput"],
    benchmarks: Sequence[tuple[str, str | None, float]],
) -> "PredictiveModelPeriodMetrics":
    from .predictive_models import (
        PredictiveModelCalculationError,
        PredictiveModelPeriodMetrics,
        PredictiveModelPrediction,
    )

    labelled = [p for p in predictions if isinstance(p, PredictiveModelPrediction)]
    keys = [(p.session_date, p.target_date) for p in labelled]
    benchmark_keys = [(s, t) for s, t, _ in benchmarks]
    if keys != benchmark_keys:
        raise PredictiveModelCalculationError(
            f"The naive benchmark periods do not match the labelled {period} prediction periods."
        )
    if not labelled:
        scope = (
            "in_sample"
            if period == "training"
            else "validation"
            if period == "validation"
            else "out_of_sample"
        )
        return PredictiveModelPeriodMetrics(
            period=period,
            observations=0,
            metrics={},
            benchmark_metrics={},
            comparison={},
            sample_scope=scope,
        )
    actual = [float(p.actual_target) for p in labelled]
    model = [float(p.predicted_value) for p in labelled]
    bench = [float(v) for _, _, v in benchmarks]
    if any(not math.isfinite(v) for v in actual + model + bench):
        raise PredictiveModelCalculationError(
            f"The {period} model and benchmark metrics require finite values."
        )
    mean = sum(actual) / len(actual)
    total = sum((v - mean) ** 2 for v in actual)

    def calculate(values: list[float]) -> _RegressionMetrics:
        errors = [x - y for x, y in zip(values, actual, strict=True)]
        residual = sum(e * e for e in errors)
        mae = sum(abs(e) for e in errors) / len(errors)
        rmse = math.sqrt(residual / len(errors))
        return _RegressionMetrics(mae, rmse, 1.0 - residual / total if total > 1e-15 else 0.0)

    model_result = calculate(model)
    bench_result = calculate(bench)
    model_mae, model_rmse, model_r2 = model_result.mae, model_result.rmse, model_result.r2
    bench_mae, bench_rmse, bench_r2 = bench_result.mae, bench_result.rmse, bench_result.r2
    scope = (
        "in_sample"
        if period == "training"
        else "validation"
        if period == "validation"
        else "out_of_sample"
    )
    return PredictiveModelPeriodMetrics(
        period=period,
        observations=len(labelled),
        metrics={"mae": model_mae, "rmse": model_rmse, "r2": model_r2},
        benchmark_metrics={"mae": bench_mae, "rmse": bench_rmse, "r2": bench_r2},
        comparison={
            "rmse_ratio": model_rmse / bench_rmse if bench_rmse > 1e-15 else 1.0,
            "mae_ratio": model_mae / bench_mae if bench_mae > 1e-15 else 1.0,
            "rmse_improvement": 1.0 - model_rmse / bench_rmse if bench_rmse > 1e-15 else 0.0,
            "mae_improvement": 1.0 - model_mae / bench_mae if bench_mae > 1e-15 else 0.0,
            "outperforms_benchmark": bool(model_rmse < bench_rmse),
            "same_eligible_periods": True,
        },
        sample_scope=scope,
    )


def evaluate_model(request: ModelEvaluationInput) -> "PredictiveModelCalculation":
    """Run holdout or walk-forward evaluation through one shared path."""
    from .predictive_models import (
        NaiveBenchmarkEvaluation,
        PredictiveModelCalculation,
        PredictiveModelCalculationError,
        PredictiveModelEvaluation,
        PredictiveModelFold,
        PredictiveModelPrediction,
        PredictiveModelSplit,
    )

    p = request.parameters
    options = ModelEvaluationParameters(
        int(p["training_window"]),
        float(p["validation_fraction"]),
        float(p["test_fraction"]),
        p["evaluation_mode"],
        p["naive_benchmark"],
    )
    labelled = (
        request.frame.dropna(subset=[request.feature_column, "next_session_return", "target_date"])
        .sort_values("target_date")
        .reset_index(drop=True)
    )
    validation_size = max(1, math.ceil(len(labelled) * options.validation_fraction))
    test_size = max(1, math.ceil(len(labelled) * options.test_fraction))
    training_size = len(labelled) - validation_size - test_size
    if training_size < 2:
        raise PredictiveModelCalculationError(
            "At least two labelled training observations and one validation and test "
            "observation are required for chronological evaluation."
        )
    training = labelled.iloc[:training_size].tail(options.training_window).reset_index(drop=True)
    validation = labelled.iloc[training_size : training_size + validation_size].reset_index(
        drop=True
    )
    test = labelled.iloc[training_size + validation_size :].reset_index(drop=True)
    if validation.empty or test.empty:
        raise PredictiveModelCalculationError(
            "Chronological evaluation requires non-empty validation and test periods."
        )
    scope = (
        "training_only"
        if options.evaluation_mode == "holdout"
        else "prior_observations_before_target"
        if options.evaluation_mode == "expanding"
        else "rolling_window_before_target"
    )

    def split(period: str, frame: pd.DataFrame, fit_scope: str) -> "PredictiveModelSplit":
        return PredictiveModelSplit(
            period=period,
            start=str(frame.target_date.iloc[0]),
            end=str(frame.target_date.iloc[-1]),
            feature_start=str(frame.session_date.iloc[0]),
            feature_end=str(frame.session_date.iloc[-1]),
            observations=len(frame),
            labelled_observations=len(frame),
            fit_scope=fit_scope,
        )

    periods = (
        split("training", training, "training_only"),
        split("validation", validation, scope),
        split("test", test, scope),
    )
    if not (periods[0].end < periods[1].start < periods[2].start):
        raise PredictiveModelCalculationError(
            "Training, validation, and test target periods must be strictly chronological."
        )
    benchmark = NAIVE_BENCHMARKS[options.naive_benchmark]
    sorted_bars = sorted(request.bars, key=lambda b: b.session_date)
    prior_returns = {
        bar.session_date: (bar.close / sorted_bars[i - 1].close - 1.0)
        if i and sorted_bars[i - 1].close > 0
        else 0.0
        for i, bar in enumerate(sorted_bars)
    }
    training_targets = [float(v) for v in training.next_session_return]
    artifact = request.fit(training, dict(request.parameters), request.seed)
    fold_artifacts = [artifact]
    predictions_by_session: dict[str, "PredictiveModelOutput"] = {}
    folds: list["PredictiveModelFold"] = []
    bench_by_period: dict[str, list[tuple[str, str | None, float]]] = {
        "training": [],
        "validation": [],
        "test": [],
    }
    for _, row in training.iterrows():
        bench_by_period["training"].append(
            (
                str(row.session_date),
                str(row.target_date),
                benchmark.predict(str(row.session_date), training_targets, prior_returns),
            )
        )
    if options.evaluation_mode == "holdout":
        for pred in request.forecast(artifact, request.frame):
            predictions_by_session[pred.session_date] = pred
        for period_name, period_frame in (("validation", validation), ("test", test)):
            for _, row in period_frame.iterrows():
                s = str(row.session_date)
                bench_by_period[period_name].append(
                    (s, str(row.target_date), benchmark.predict(s, training_targets, prior_returns))
                )
    else:
        fold_index = 1
        for period_name, period_frame in (("validation", validation), ("test", test)):
            for _, row in period_frame.iterrows():
                eligible = labelled[
                    (labelled.session_date < row.session_date)
                    & (labelled.target_date <= row.session_date)
                ]
                if options.evaluation_mode == "expanding":
                    eligible = eligible[eligible.session_date >= artifact.training_start]
                else:
                    eligible = eligible.tail(options.training_window)
                eligible = eligible.reset_index(drop=True)
                if len(eligible) < 2:
                    raise PredictiveModelCalculationError(
                        "Each walk-forward fold requires at least two eligible "
                        "training observations."
                    )
                fold_artifact = request.fit(eligible, dict(request.parameters), request.seed)
                fold_artifacts.append(fold_artifact)
                raw = request.forecast(fold_artifact, pd.DataFrame([row]))
                if not raw:
                    raise PredictiveModelCalculationError(
                        f"No prediction was produced for {period_name} session {row.session_date}."
                    )
                pred = (
                    replace(raw[0], period=period_name)
                    if isinstance(raw[0], PredictiveModelPrediction)
                    else raw[0]
                )
                predictions_by_session[pred.session_date] = pred
                targets = [float(v) for v in eligible.next_session_return]
                s = str(row.session_date)
                bench_by_period[period_name].append(
                    (s, str(row.target_date), benchmark.predict(s, targets, prior_returns))
                )
                error = (
                    abs(float(pred.predicted_value) - float(pred.actual_target))
                    if isinstance(pred, PredictiveModelPrediction)
                    else 0.0
                )
                folds.append(
                    PredictiveModelFold(
                        fold_index=fold_index,
                        period=period_name,
                        prediction_session_date=s,
                        target_date=pred.target_date,
                        training_start=fold_artifact.training_start,
                        training_end=fold_artifact.training_end,
                        training_observations=fold_artifact.training_observations,
                        fit_scope=scope,
                        artifact=fold_artifact,
                        prediction=pred,
                        metrics={"mae": error, "rmse": error}
                        if isinstance(pred, PredictiveModelPrediction)
                        else {},
                    )
                )
                fold_index += 1
    final_artifact = fold_artifacts[-1]
    period_by_target = {
        str(row.target_date): period
        for period, frame in (("training", training), ("validation", validation), ("test", test))
        for _, row in frame.iterrows()
    }
    predictions = []
    for _, row in request.frame.iterrows():
        if str(row.session_date) <= artifact.training_end:
            continue
        pred = predictions_by_session.get(str(row.session_date))
        if pred is None:
            values = request.forecast(final_artifact, pd.DataFrame([row]))
            if not values:
                continue
            pred = values[0]
        predictions.append(
            replace(
                pred, period=getattr(pred, "period", None) or period_by_target.get(pred.target_date)
            )
            if isinstance(pred, PredictiveModelPrediction)
            else pred
        )
    training_preds = [
        replace(x, period="training")
        for x in request.forecast(artifact, training)
        if isinstance(x, PredictiveModelPrediction)
    ]
    period_metrics = (
        evaluate_period_metrics("training", training_preds, bench_by_period["training"]),
        evaluate_period_metrics(
            "validation",
            [
                x
                for x in predictions
                if isinstance(x, PredictiveModelPrediction) and x.period == "validation"
            ],
            bench_by_period["validation"],
        ),
        evaluate_period_metrics(
            "test",
            [
                x
                for x in predictions
                if isinstance(x, PredictiveModelPrediction) and x.period == "test"
            ],
            bench_by_period["test"],
        ),
    )
    test_metric = period_metrics[2]
    if not test_metric.observations:
        raise PredictiveModelCalculationError(
            "The out-of-sample test period has no labelled observations for benchmark comparison."
        )
    comparison = {
        "benchmark_name": options.naive_benchmark,
        "period": "test",
        "sample_scope": "out_of_sample",
        "observations": test_metric.observations,
        "same_eligible_periods": True,
        "model_rmse": test_metric.metrics["rmse"],
        "benchmark_rmse": test_metric.benchmark_metrics["rmse"],
        "rmse_improvement": test_metric.comparison["rmse_improvement"],
        "model_mae": test_metric.metrics["mae"],
        "benchmark_mae": test_metric.benchmark_metrics["mae"],
        "mae_improvement": test_metric.comparison["mae_improvement"],
        "model_r2": test_metric.metrics["r2"],
        "benchmark_r2": test_metric.benchmark_metrics["r2"],
        "outperforms_benchmark": test_metric.comparison["outperforms_benchmark"],
        "status": "evaluated",
        "comparison_complete": True,
    }
    benchmark_eval = NaiveBenchmarkEvaluation(
        options.naive_benchmark,
        benchmark.display_name,
        benchmark.description,
        {m.period: m.benchmark_metrics for m in period_metrics},
        comparison,
        True,
    )
    metrics = {
        k: float(v) for k, v in artifact.training_metrics.items() if isinstance(v, (int, float))
    }
    for m in period_metrics:
        metrics.update({f"{m.period}_{k}": float(v) for k, v in m.metrics.items()})
        metrics.update(
            {f"{m.period}_benchmark_{k}": float(v) for k, v in m.benchmark_metrics.items()}
        )
        metrics.update(
            {
                f"{m.period}_{k}": float(v)
                for k, v in m.comparison.items()
                if isinstance(v, (int, float))
            }
        )
    evaluation = PredictiveModelEvaluation(
        options.evaluation_mode,
        periods,
        period_metrics,
        request.assumptions,
        request.warnings,
        request.limitations,
        request.unsupported_claims,
        tuple(folds),
        benchmark_eval,
        True,
        "Naive benchmark comparison is complete on the labelled out-of-sample test period.",
    )
    return PredictiveModelCalculation(
        request.metadata,
        artifact,
        dict(request.parameters),
        request.seed,
        predictions,
        metrics,
        artifact.training_start,
        artifact.training_end,
        "available",
        evaluation,
        fold_artifacts,
    )
