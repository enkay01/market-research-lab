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
    assert frame.loc[3, "momentum"] == pytest.approx(0.21)
    assert pd.isna(frame.loc[3, "next_session_return"])


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
    assert result.training_start == "2024-01-05"
    assert result.training_end == "2024-01-07"
    assert [prediction.session_date for prediction in result.predictions] == ["2024-01-08"]
    assert result.predictions[-1].actual_target is None
    assert result.out_of_sample_status == "not_available_until_chronological_splits"


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
