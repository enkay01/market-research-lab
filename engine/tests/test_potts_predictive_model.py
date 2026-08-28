"""Tests for the published Potts Gain-Loss Asymmetry predictive model (Bornholdt 2021)."""

import math

import pandas as pd
import pytest

from market_research_lab.market_data import DailyBar
from market_research_lab.predictive_models import (
    PottsGainLossParameters,
    build_potts_supervised_frame,
    get_predictive_model_spec,
    list_predictive_models,
    run_predictive_model,
)


def _make_daily_bars(count: int = 300) -> list[DailyBar]:
    """Generate synthetic daily bars for deterministic testing."""
    bars: list[DailyBar] = []
    base_price = 100.0
    for i in range(count):
        cycle = math.sin(i / 10.0) * 5.0 + math.cos(i / 25.0) * 10.0
        price = max(10.0, base_price + cycle + (i * 0.05))
        session_date = f"2024-{(i // 25) + 1:02d}-{(i % 25) + 1:02d}"
        bars.append(
            DailyBar(
                security_id="TEST",
                session_date=session_date,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=10000.0,
                source="test",
                available_at=f"{session_date}T20:00:00Z",
            )
        )
    return bars


def test_potts_model_registered():
    """Verify potts_gain_loss_asymmetry is in the registry and has declared metadata."""
    models = list_predictive_models()
    names = [m.name for m in models]
    assert "potts_gain_loss_asymmetry" in names

    spec = get_predictive_model_spec("potts_gain_loss_asymmetry")
    assert spec.metadata.display_name == "Potts Gain-Loss Asymmetry"
    assert spec.metadata.target == "next_session_return"
    assert spec.metadata.horizon == 1
    assert "potts_gain_loss_score" in spec.metadata.features
    assert len(spec.metadata.parameters) >= 5


def test_build_potts_supervised_frame_structure_and_leakage():
    """Verify supervised frame builds correct columns and does not leak future feature values."""
    bars = _make_daily_bars(120)
    config = PottsGainLossParameters(
        threshold_return=0.03,
        lookback_window=30,
        q_states=4,
    )
    frame = build_potts_supervised_frame(
        bars,
        config=config,
        horizon=1,
    )

    assert "session_date" in frame.columns
    assert "potts_gain_loss_score" in frame.columns
    assert "gain_loss_asymmetry_ratio" in frame.columns
    assert "potts_order_parameter" in frame.columns
    assert "next_session_return" in frame.columns
    assert "target_date" in frame.columns

    # First 30 rows must be warmup (NaN / None) for the features
    for idx in range(30):
        assert pd.isna(frame.loc[idx, "potts_gain_loss_score"])
        assert pd.isna(frame.loc[idx, "gain_loss_asymmetry_ratio"])
        assert pd.isna(frame.loc[idx, "potts_order_parameter"])

    # After lookback window, features must be populated
    for idx in range(30, len(bars)):
        score = frame.loc[idx, "potts_gain_loss_score"]
        assert not pd.isna(score)
        assert math.isfinite(float(score))
        asym = frame.loc[idx, "gain_loss_asymmetry_ratio"]
        assert -1.0 <= float(asym) <= 1.0
        m = frame.loc[idx, "potts_order_parameter"]
        assert 0.0 <= float(m) <= 1.0

    # Last row must have None target_date and next_session_return (horizon=1)
    assert pd.isna(frame.loc[len(bars) - 1, "target_date"])
    assert pd.isna(frame.loc[len(bars) - 1, "next_session_return"])


def test_potts_parameter_validation():
    """Verify strict validation of Potts model parameters."""
    # Invalid threshold_return
    with pytest.raises(Exception):
        PottsGainLossParameters(threshold_return=-0.05)
    with pytest.raises(Exception):
        PottsGainLossParameters(threshold_return=0.6)

    # Invalid lookback_window
    with pytest.raises(Exception):
        PottsGainLossParameters(lookback_window=5)

    # Invalid q_states
    with pytest.raises(Exception):
        PottsGainLossParameters(q_states=1)
    with pytest.raises(Exception):
        PottsGainLossParameters(q_states=20)


def test_potts_model_run_holdout_evaluation():
    """Verify complete chronological holdout execution and benchmark evaluation."""
    bars = _make_daily_bars(300)
    calc = run_predictive_model(
        "potts_gain_loss_asymmetry",
        bars,
        parameters={
            "threshold_return": 0.03,
            "lookback_window": 30,
            "q_states": 4,
            "training_window": 150,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
            "evaluation_mode": "holdout",
            "naive_benchmark": "zero_return",
        },
        seed=42,
    )

    assert calc.metadata.name == "potts_gain_loss_asymmetry"
    assert calc.artifact.model_name == "potts_gain_loss_asymmetry"
    assert calc.artifact.training_observations > 50
    assert math.isfinite(calc.artifact.intercept)
    assert math.isfinite(calc.artifact.coefficient)

    # Check chronological evaluation splits
    eval_obj = calc.evaluation
    assert eval_obj.mode == "holdout"
    assert len(eval_obj.splits) == 3
    training_split, val_split, test_split = eval_obj.splits
    assert training_split.end < val_split.start
    assert val_split.end < test_split.start

    # Check benchmark comparison (MOD-009)
    assert eval_obj.benchmark.completed is True
    assert eval_obj.benchmark.name == "zero_return"
    assert eval_obj.is_eligible_for_strategy is True

    comp = eval_obj.benchmark.out_of_sample_comparison
    assert comp.get("status") == "evaluated"
    assert comp.get("period") == "test"
    assert comp.get("same_eligible_periods") is True
    assert comp.get("comparison_complete") is True
    assert isinstance(comp.get("model_rmse"), float)
    assert isinstance(comp.get("benchmark_rmse"), float)


def test_potts_model_run_expanding_and_rolling_evaluation():
    """Verify expanding and rolling walk-forward fold evaluations."""
    bars = _make_daily_bars(250)

    # Expanding mode
    calc_exp = run_predictive_model(
        "potts_gain_loss_asymmetry",
        bars,
        parameters={
            "threshold_return": 0.04,
            "lookback_window": 25,
            "q_states": 4,
            "training_window": 100,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
            "evaluation_mode": "expanding",
            "naive_benchmark": "persistence",
        },
    )
    assert calc_exp.evaluation.mode == "expanding"
    assert len(calc_exp.evaluation.folds) > 0

    # Rolling mode
    calc_roll = run_predictive_model(
        "potts_gain_loss_asymmetry",
        bars,
        parameters={
            "threshold_return": 0.04,
            "lookback_window": 25,
            "q_states": 4,
            "training_window": 100,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
            "evaluation_mode": "rolling",
            "naive_benchmark": "historical_mean",
        },
    )
    assert calc_roll.evaluation.mode == "rolling"
    assert len(calc_roll.evaluation.folds) > 0
