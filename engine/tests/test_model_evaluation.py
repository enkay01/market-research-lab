"""Direct regression tests for the shared Predictive Model evaluator."""

from dataclasses import dataclass

import pandas as pd
import pytest

from market_research_lab.model_evaluation import (
    ModelEvaluationInput,
    evaluate_model,
    evaluate_period_metrics,
)
from market_research_lab.predictive_models import (
    FittedModelArtifact,
    PredictiveModelCalculationError,
    PredictiveModelMetadata,
    PredictiveModelPrediction,
)


@dataclass(frozen=True)
class _CallLog:
    frames: list[pd.DataFrame]


def _request(mode: str, benchmark: str = "zero_return") -> tuple[ModelEvaluationInput, _CallLog]:
    dates = [f"2024-01-{day:02d}" for day in range(1, 15)]
    frame = pd.DataFrame(
        {
            "session_date": dates,
            "target_date": [f"2024-01-{day:02d}" for day in range(2, 16)],
            "feature": [float(day) for day in range(14)],
            "next_session_return": [0.01 * day for day in range(14)],
        }
    )
    log = _CallLog([])

    def fit(
        training: pd.DataFrame, parameters: dict[str, object], seed: int | None
    ) -> FittedModelArtifact:
        del parameters, seed
        log.frames.append(training.copy())
        return FittedModelArtifact(
            model_name="synthetic",
            feature_name="feature",
            target_name="next_session_return",
            horizon=1,
            intercept=0.0,
            coefficient=1.0,
            training_start=str(training.session_date.iloc[0]),
            training_end=str(training.session_date.iloc[-1]),
            training_observations=len(training),
            parameters={},
            seed=None,
            training_metrics={"rmse": 0.0},
        )

    def forecast(
        artifact: FittedModelArtifact, eligible: pd.DataFrame
    ) -> list[PredictiveModelPrediction]:
        del artifact
        return [
            PredictiveModelPrediction(
                session_date=str(row.session_date),
                feature_value=float(row.feature),
                predicted_value=float(row.next_session_return),
                actual_target=float(row.next_session_return),
                target_date=str(row.target_date),
            )
            for row in eligible.itertuples()
        ]

    metadata = PredictiveModelMetadata(
        name="synthetic",
        display_name="Synthetic",
        description="Synthetic evaluation fixture",
        target="next_session_return",
        horizon=1,
        features=("feature",),
        training_window=4,
        parameters=(),
        output_meaning="return",
        outputs=("predicted_value",),
    )
    request = ModelEvaluationInput(
        name="synthetic",
        frame=frame,
        feature_column="feature",
        bars=[],
        parameters={
            "training_window": 4,
            "validation_fraction": 0.25,
            "test_fraction": 0.25,
            "evaluation_mode": mode,
            "naive_benchmark": benchmark,
        },
        seed=7,
        fit=fit,
        forecast=forecast,
        metadata=metadata,
        assumptions=(),
        warnings=(),
        limitations=(),
        unsupported_claims=(),
    )
    return request, log


@pytest.mark.parametrize("mode", ["holdout", "expanding", "rolling"])
def test_evaluator_has_exact_chronological_periods(mode: str) -> None:
    request, log = _request(mode)
    result = evaluate_model(request)

    assert [(split.period, split.start, split.end) for split in result.evaluation.splits] == [
        ("training", "2024-01-04", "2024-01-07"),
        ("validation", "2024-01-08", "2024-01-11"),
        ("test", "2024-01-12", "2024-01-15"),
    ]
    assert result.evaluation.splits[0].feature_start == "2024-01-03"
    assert result.evaluation.splits[0].feature_end == "2024-01-06"
    assert result.evaluation.splits[1].feature_start == "2024-01-07"
    assert result.evaluation.splits[2].feature_end == "2024-01-14"
    if mode != "holdout":
        assert all(
            frame.target_date.iloc[-1] <= fold.prediction_session_date
            for frame, fold in zip(log.frames[1:], result.evaluation.folds, strict=True)
        )


def test_walk_forward_folds_have_unique_indices_and_causal_training() -> None:
    request, log = _request("rolling")
    baseline = evaluate_model(request)
    folds = baseline.evaluation.folds

    assert [fold.fold_index for fold in folds] == list(range(1, len(folds) + 1))
    assert all(
        frame.session_date.iloc[-1] < fold.prediction_session_date
        for frame, fold in zip(log.frames[1:], folds, strict=True)
    )

    changed_request, changed_log = _request("rolling")
    changed_request.frame.loc[12:, "next_session_return"] = 99.0
    changed = evaluate_model(changed_request)
    assert (
        changed.evaluation.folds[0].prediction.predicted_value
        == baseline.evaluation.folds[0].prediction.predicted_value
    )
    assert changed_log.frames[1].equals(log.frames[1])


@pytest.mark.parametrize("benchmark", ["zero_return", "historical_mean", "persistence"])
def test_benchmark_predictions_use_the_same_labelled_keys_and_metrics(benchmark: str) -> None:
    result = evaluate_model(_request("holdout", benchmark)[0])
    evaluation = result.evaluation

    assert evaluation.benchmark is not None
    assert evaluation.benchmark.name == benchmark
    assert all(
        metric.comparison["same_eligible_periods"] is True for metric in evaluation.period_metrics
    )
    assert {"training_benchmark_mae", "validation_benchmark_rmse", "test_benchmark_r2"}.issubset(
        result.metrics
    )
    assert {"training_rmse_improvement", "validation_mae_improvement", "test_rmse_ratio"}.issubset(
        result.metrics
    )


def test_evaluator_rejects_misaligned_benchmark_keys() -> None:
    prediction = PredictiveModelPrediction("2024-01-02", 1.0, 0.1, 0.1, "2024-01-03")

    with pytest.raises(PredictiveModelCalculationError, match="do not match"):
        evaluate_period_metrics("test", [prediction], [("2024-01-02", "2024-01-04", 0.0)])
