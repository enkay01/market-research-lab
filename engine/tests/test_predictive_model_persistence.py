"""Project persistence tests for Predictive Model Run artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from market_research_lab.projects import (
    FailedPredictiveModelRunRecord,
    PredictiveModelRunRecord,
    ProjectStore,
)


def _record() -> PredictiveModelRunRecord:
    return PredictiveModelRunRecord(
        model_revision="momentum_return_regression:v1",
        dataset_version_ids=["dataset-v1"],
        parameters={"momentum_period": 20, "training_window": 252},
        as_of="2024-01-03T00:00:00+00:00",
        completed_at="2024-01-03T12:00:00+00:00",
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
            "status": "completed",
            "model_name": "momentum_return_regression",
            "symbol": "AAPL",
            "as_of": "2024-01-03T00:00:00+00:00",
            "completed_at": "2024-01-03T12:00:00+00:00",
            "metrics": {"in_sample_r2": 0.4},
            "out_of_sample_status": "not_available_until_chronological_splits",
        },
        folds=[
            {
                "fold_index": 1,
                "period": "validation",
                "prediction_session_date": "2024-01-04",
                "target_date": "2024-01-05",
                "training_start": "2024-01-01",
                "training_end": "2024-01-03",
                "training_observations": 3,
                "fit_scope": "rolling_window_before_target",
                "artifact": {"coefficient": 0.12},
                "prediction": {"session_date": "2024-01-04", "predicted_value": 0.01},
                "metrics": {"mae": 0.01, "rmse": 0.01},
            }
        ],
    )


def test_predictive_model_run_persists_artifact_predictions_and_provenance(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Model inspection")

    run_id = store.create_predictive_model_result(project.id, _record())
    run_root = tmp_path / "projects" / project.id / "runs" / run_id

    assert (run_root / "status.json").read_text(encoding="utf-8").find('"completed"') >= 0
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "predictive_model"
    assert manifest["definition_revisions"] == ["momentum_return_regression:v1"]
    assert manifest["dataset_versions"] == ["dataset-v1"]
    assert manifest["completed_at"] == "2024-01-03T12:00:00+00:00"
    assert "folds" not in manifest["evaluation"]
    assert (run_root / "artifacts" / "fitted_model.json").exists()
    assert (run_root / "artifacts" / "predictions.json").exists()
    assert (run_root / "artifacts" / "fold_artifacts.json").exists()
    assert (run_root / "artifacts" / "folds.json").exists()
    predictive_model = json.loads(
        (run_root / "artifacts" / "predictive_model.json").read_text(encoding="utf-8")
    )
    assert "folds" not in predictive_model

    loaded = store.get_predictive_model_result(project.id, run_id)
    assert loaded is not None
    assert loaded["model_revision"] == "momentum_return_regression:v1"
    assert loaded["result"]["model_name"] == "momentum_return_regression"
    assert loaded["result"]["folds"] == _record().folds

    listed = store.list_predictive_model_results(project.id)
    assert len(listed) == 1
    assert listed[0]["run_id"] == run_id


def test_failed_predictive_model_run_persists_error_and_provenance(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Failed model inspection")

    run_id = store.create_failed_predictive_model_run(
        project.id,
        FailedPredictiveModelRunRecord(
            model_revision="momentum_return_regression:failed",
            dataset_version_ids=["dataset-v1"],
            parameters={"momentum_period": 20},
            as_of=None,
            error_message="not enough observations",
        ),
    )
    run_root = tmp_path / "projects" / project.id / "runs" / run_id

    assert '"status": "failed"' in (run_root / "status.json").read_text(encoding="utf-8")
    assert "not enough observations" in (
        run_root / "artifacts" / "error.json"
    ).read_text(encoding="utf-8")
    assert store.list_predictive_model_results(project.id) == []
