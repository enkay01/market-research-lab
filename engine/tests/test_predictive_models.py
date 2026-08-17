"""Behavior tests for the code-defined Predictive Model seam."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from market_research_lab.market_data import DailyBar
from market_research_lab.predictive_models import (
    PredictiveModelCalculationError,
    PredictiveModelParameterError,
    build_supervised_frame,
    fit_model,
    get_predictive_model_spec,
    list_predictive_models,
    predict,
    run_predictive_model,
)


def _bars(closes: list[float]) -> list[DailyBar]:
    return [
        DailyBar(
            security_id="AAPL",
            session_date=f"2024-01-{index + 1:02d}",
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000.0,
            source="test",
        )
        for index, close in enumerate(closes)
    ]


def test_registry_exposes_the_model_contract() -> None:
    names = {spec.name for spec in list_predictive_models()}
    spec = get_predictive_model_spec("momentum_return_regression")

    assert "momentum_return_regression" in names
    assert spec.target == "next_session_return"
    assert spec.horizon == 1
    assert spec.features == ("trailing_close_momentum",)
    assert spec.training_window == 252
    assert {parameter.name for parameter in spec.parameters} == {
        "momentum_period",
        "training_window",
        "validation_fraction",
        "test_fraction",
        "evaluation_mode",
    }
    assert "predicted_next_session_return" in spec.outputs
    assert "next session simple return" in spec.output_meaning


def test_supervised_frame_uses_trailing_close_and_next_session_label() -> None:
    frame = build_supervised_frame(
        _bars([100.0, 110.0, 121.0, 133.1]), momentum_period=2, horizon=1
    )

    assert pd.isna(frame.loc[0, "momentum"])
    assert frame.loc[2, "momentum"] == pytest.approx(0.21)
    assert frame.loc[2, "next_session_return"] == pytest.approx(0.1)
    assert frame.loc[2, "target_date"] == "2024-01-04"
    assert frame.loc[3, "momentum"] == pytest.approx(0.21)
    assert pd.isna(frame.loc[3, "next_session_return"])
    assert pd.isna(frame.loc[3, "target_date"])


def test_fit_and_predict_use_the_documented_typed_seam() -> None:
    training_frame = pd.DataFrame(
        {
            "session_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "momentum": [1.0, 2.0, 3.0],
            "next_session_return": [2.0, 4.0, 6.0],
        }
    )

    artifact = fit_model(
        "momentum_return_regression",
        training_frame,
        {"momentum_period": 2, "training_window": 3},
        seed=7,
    )
    predictions = predict(artifact, training_frame)

    assert artifact.intercept == pytest.approx(0.0)
    assert artifact.coefficient == pytest.approx(2.0)
    assert artifact.seed == 7
    assert artifact.training_observations == 3
    assert artifact.training_metrics["in_sample_r2"] == pytest.approx(1.0)
    assert [prediction.predicted_value for prediction in predictions] == pytest.approx(
        [2.0, 4.0, 6.0]
    )


def test_predictions_do_not_recalculate_earlier_values_from_future_rows() -> None:
    bars = _bars([100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 107.0])
    frame = build_supervised_frame(bars, momentum_period=2, horizon=1)
    training_frame = frame.dropna(subset=["momentum", "next_session_return"]).iloc[:3]
    artifact = fit_model(
        "momentum_return_regression",
        training_frame,
        {"momentum_period": 2, "training_window": 3},
    )

    future_changed = bars + [replace(bars[-1], session_date="2024-01-08", close=900.0)]
    changed_frame = build_supervised_frame(future_changed, momentum_period=2, horizon=1)

    before = predict(artifact, frame)
    after = predict(artifact, changed_frame)

    assert [prediction.session_date for prediction in before] == [
        prediction.session_date for prediction in after[: len(before)]
    ]
    assert [prediction.predicted_value for prediction in before] == pytest.approx(
        [prediction.predicted_value for prediction in after[: len(before)]]
    )


def test_run_limits_training_to_the_requested_window() -> None:
    result = run_predictive_model(
        "momentum_return_regression",
        _bars([100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 107.0, 111.0]),
        {"momentum_period": 2, "training_window": 3},
    )

    assert result.artifact.training_observations == 3
    assert result.training_start == "2024-01-03"
    assert result.training_end == "2024-01-05"
    assert [prediction.session_date for prediction in result.predictions] == [
        "2024-01-06",
        "2024-01-07",
        "2024-01-08",
    ]
    assert [prediction.period for prediction in result.predictions] == [
        "validation",
        "test",
        None,
    ]
    assert result.predictions[-1].actual_target is None
    assert result.out_of_sample_status == "available"


def test_run_records_chronological_periods_and_labelled_metrics() -> None:
    result = run_predictive_model(
        "momentum_return_regression",
        _bars(
            [
                100.0,
                102.0,
                101.0,
                105.0,
                104.0,
                108.0,
                107.0,
                111.0,
                115.0,
                113.0,
                118.0,
                120.0,
                119.0,
                123.0,
                126.0,
            ]
        ),
        {
            "momentum_period": 2,
            "training_window": 6,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
        },
    )

    assert [split.period for split in result.evaluation.splits] == [
        "training",
        "validation",
        "test",
    ]
    training, validation, test = result.evaluation.splits
    assert training.end < validation.start < test.start
    assert [item.period for item in result.evaluation.period_metrics] == [
        "training",
        "validation",
        "test",
    ]
    assert result.evaluation.period_metrics[1].metrics["rmse"] >= 0
    assert result.evaluation.period_metrics[2].metrics["mae"] >= 0
    assert result.artifact.preprocessing["fit_scope"] == "training_only"
    assert result.artifact.preprocessing["uses_validation_or_test"] is False
    assert result.evaluation.to_json()["leakage_policy"] == {
        "initial_feature_and_preprocessing_fit_scope": "training_only",
        "future_labels_excluded_from_each_training_window": True,
        "validation_and_test_labels_excluded_from_initial_training": True,
    }


def test_validation_and_test_observations_do_not_change_training_artifact() -> None:
    bars = _bars(
        [
            100.0,
            102.0,
            101.0,
            105.0,
            104.0,
            108.0,
            107.0,
            111.0,
            115.0,
            113.0,
            118.0,
            120.0,
            119.0,
            123.0,
            126.0,
        ]
    )
    parameters = {"momentum_period": 2, "training_window": 6}
    baseline = run_predictive_model("momentum_return_regression", bars, parameters)
    validation = baseline.evaluation.splits[1]
    test = baseline.evaluation.splits[2]
    for start, end in ((validation.start, validation.end), (test.start, test.end)):
        changed_observations = [
            replace(bar, close=900.0, open=900.0, high=900.0, low=900.0)
            if start <= bar.session_date <= end
            else bar
            for bar in bars
        ]
        changed = run_predictive_model(
            "momentum_return_regression", changed_observations, parameters
        )

        assert changed.artifact.intercept == pytest.approx(baseline.artifact.intercept)
        assert changed.artifact.coefficient == pytest.approx(baseline.artifact.coefficient)
        assert changed.artifact.training_start == baseline.artifact.training_start
        assert changed.artifact.training_end == baseline.artifact.training_end


def test_expanding_and_rolling_modes_fit_each_fold_without_current_label() -> None:
    bars = _bars(
        [
            100.0,
            102.0,
            101.0,
            105.0,
            104.0,
            108.0,
            107.0,
            111.0,
            115.0,
            113.0,
            118.0,
            120.0,
            119.0,
            123.0,
            126.0,
        ]
    )
    for mode in ("expanding", "rolling"):
        result = run_predictive_model(
            "momentum_return_regression",
            bars,
            {
                "momentum_period": 2,
                "training_window": 4,
                "evaluation_mode": mode,
            },
            seed=7,
        )

        assert result.evaluation.mode == mode
        assert len(result.fold_artifacts) > 1
        labelled_predictions = [
            prediction
            for prediction in result.predictions
            if prediction.target_date is not None
        ]
        assert len(labelled_predictions) == len(result.fold_artifacts) - 1
        assert all(
            artifact.training_end < prediction.session_date
            and artifact.training_end < prediction.target_date
            for artifact, prediction in zip(
                result.fold_artifacts[1:], labelled_predictions, strict=True
            )
        )
        expected_scope = (
            "prior_observations_before_target"
            if mode == "expanding"
            else "rolling_window_before_target"
        )
        assert result.evaluation.splits[2].fit_scope == expected_scope


def test_run_does_not_return_predictions_from_before_the_training_end() -> None:
    result = run_predictive_model(
        "momentum_return_regression",
        _bars([100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 107.0, 111.0]),
        {"momentum_period": 2, "training_window": 3},
    )

    assert all(
        prediction.session_date > result.training_end for prediction in result.predictions
    )


def test_run_rejects_invalid_parameters_and_insufficient_history() -> None:
    with pytest.raises(PredictiveModelParameterError, match="momentum_period"):
        run_predictive_model(
            "momentum_return_regression",
            _bars([100.0, 102.0, 101.0, 105.0]),
            {"momentum_period": 0},
        )

    with pytest.raises(PredictiveModelCalculationError, match="training observations"):
        run_predictive_model(
            "momentum_return_regression",
            _bars([100.0, 102.0, 101.0]),
            {"momentum_period": 2, "training_window": 3},
        )
