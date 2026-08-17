"""Project persistence tests for Predictive Model Run artifacts."""

from __future__ import annotations

from pathlib import Path

from market_research_lab.projects import PredictiveModelRunRecord, ProjectStore


def _record() -> PredictiveModelRunRecord:
    return PredictiveModelRunRecord(
        model_revision="momentum_return_regression:v1",
        dataset_version_ids=["dataset-v1"],
        parameters={"momentum_period": 20, "training_window": 252},
        artifact={"coefficient": 0.12, "seed": 7},
        predictions=[
            {
                "session_date": "2024-01-03",
                "feature_value": 0.04,
                "predicted_value": 0.01,
                "actual_target": 0.02,
            }
        ],
        result={
            "model_name": "momentum_return_regression",
            "symbol": "AAPL",
            "metrics": {"in_sample_r2": 0.4},
            "out_of_sample_status": "not_available_until_chronological_splits",
        },
    )


def test_predictive_model_run_persists_artifact_predictions_and_provenance(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Model inspection")

    run_id = store.create_predictive_model_result(project.id, _record())
    run_root = tmp_path / "projects" / project.id / "runs" / run_id

    assert (run_root / "status.json").read_text(encoding="utf-8").find('"completed"') >= 0
    manifest = (run_root / "manifest.json").read_text(encoding="utf-8")
    assert "predictive_model" in manifest
    assert "momentum_return_regression:v1" in manifest
    assert "dataset-v1" in manifest
    assert (run_root / "artifacts" / "fitted_model.json").exists()
    assert (run_root / "artifacts" / "predictions.json").exists()

    loaded = store.get_predictive_model_result(project.id, run_id)
    assert loaded is not None
    assert loaded["model_revision"] == "momentum_return_regression:v1"
    assert loaded["result"]["model_name"] == "momentum_return_regression"

    listed = store.list_predictive_model_results(project.id)
    assert len(listed) == 1
    assert listed[0]["run_id"] == run_id
