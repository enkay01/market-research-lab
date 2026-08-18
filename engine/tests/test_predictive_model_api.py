"""HTTP seam tests for Predictive Model metadata, execution, and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

from fastapi.testclient import TestClient

from market_research_lab.api import create_app
from market_research_lab.json_types import JsonValue


class ApiTestInputs(NamedTuple):
    client: TestClient
    dataset_id: str
    project_id: str


def _dataset_csv() -> bytes:
    rows = [
        "symbol,date,open,high,low,close,volume,available_at",
        "AAPL,2024-01-01,100,100,100,100,1000,2024-01-01T00:00:00Z",
        "AAPL,2024-01-02,102,102,102,102,1000,2024-01-02T00:00:00Z",
        "AAPL,2024-01-03,101,101,101,101,1000,2024-01-03T00:00:00Z",
        "AAPL,2024-01-04,105,105,105,105,1000,2024-01-04T00:00:00Z",
        "AAPL,2024-01-05,104,104,104,104,1000,2024-01-05T00:00:00Z",
        "AAPL,2024-01-06,108,108,108,108,1000,2024-01-06T00:00:00Z",
        "AAPL,2024-01-07,107,107,107,107,1000,2024-01-07T00:00:00Z",
        "AAPL,2024-01-08,111,111,111,111,1000,2024-01-08T00:00:00Z",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def _client_and_inputs(tmp_path: Path) -> ApiTestInputs:
    client = TestClient(create_app(workspace_root=tmp_path))
    imported = client.post(
        "/api/datasets",
        data={"source": "predictive-model-test"},
        files={"file": ("bars.csv", _dataset_csv(), "text/csv")},
    )
    assert imported.status_code == 201
    dataset_id = imported.json()["dataset_version_id"]
    project = client.post("/api/projects", json={"name": "Predictive Model Test"})
    assert project.status_code == 201
    return ApiTestInputs(client, dataset_id, project.json()["id"])


def _run_request(dataset_id: str) -> dict[str, JsonValue]:
    return {
        "name": "momentum_return_regression",
        "dataset_version_id": dataset_id,
        "symbol": "AAPL",
        "parameters": {"momentum_period": 2, "training_window": 3},
        "seed": 7,
        "as_of": "2099-01-01T00:00:00+00:00",
    }


def test_predictive_model_metadata_exposes_the_complete_contract(tmp_path: Path) -> None:
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.get("/api/predictive-models/momentum_return_regression")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["target"] == "next_session_return"
    assert metadata["horizon"] == 1
    assert metadata["features"] == ["trailing_close_momentum"]
    assert metadata["training_window"] == 252
    assert {parameter["name"] for parameter in metadata["parameters"]} == {
        "momentum_period",
        "training_window",
        "validation_fraction",
        "test_fraction",
        "evaluation_mode",
        "naive_benchmark",
    }


def test_predictive_model_can_run_preview_and_save_a_reproducible_run(
    tmp_path: Path,
) -> None:
    inputs = _client_and_inputs(tmp_path)
    client, dataset_id, project_id = inputs
    request = _run_request(dataset_id)

    preview = client.post("/api/predictive-models/run", json=request)

    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["run_id"] is None
    assert preview_body["status"] == "preview"
    assert preview_body["as_of"].startswith("2099-01-01")
    assert preview_body["artifact"]["training_observations"] == 3
    assert preview_body["predictions"][-1]["actual_target"] is None
    assert preview_body["metrics"]["in_sample_r2"] is not None
    assert preview_body["out_of_sample_status"] == "available"
    assert preview_body["evaluation_mode"] == "holdout"
    assert preview_body["benchmark"]["name"] == "zero_return"
    assert preview_body["benchmark"]["completed"] is True
    assert preview_body["is_eligible_for_strategy"] is True
    assert [split["period"] for split in preview_body["splits"]] == [
        "training",
        "validation",
        "test",
    ]
    assert [metric["period"] for metric in preview_body["period_metrics"]] == [
        "training",
        "validation",
        "test",
    ]
    assert preview_body["period_metrics"][1]["metrics"]["rmse"] >= 0
    assert "rmse" in preview_body["period_metrics"][1]["benchmark_metrics"]
    assert "rmse_improvement" in preview_body["period_metrics"][1]["comparison"]

    saved = client.post(
        f"/api/projects/{project_id}/predictive-models/runs",
        json=request,
    )

    assert saved.status_code == 201
    saved_body = saved.json()
    assert saved_body["run_id"]
    assert saved_body["status"] == "completed"
    assert saved_body["completed_at"]
    assert saved_body["model_revision"].endswith(":v1")

    listed = client.get(f"/api/projects/{project_id}/predictive-models/runs")
    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == saved_body["run_id"]

    reopened = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}"
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "completed"
    assert reopened.json()["run_id"] == saved_body["run_id"]
    assert reopened.json()["artifact"] == saved_body["artifact"]
    assert reopened.json()["predictions"] == saved_body["predictions"]

    run_root = tmp_path / "projects" / project_id / "runs" / saved_body["run_id"]
    predictive_model_path = run_root / "artifacts" / "predictive_model.json"
    legacy_result = json.loads(predictive_model_path.read_text(encoding="utf-8"))
    for prediction in legacy_result["predictions"]:
        prediction.pop("target_date", None)
        prediction.pop("period", None)
    predictive_model_path.write_text(json.dumps(legacy_result), encoding="utf-8")
    legacy_reopened = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}"
    )
    assert legacy_reopened.status_code == 200
    assert legacy_reopened.json()["predictions"][-1]["actual_target"] is None

    manifest = (run_root / "manifest.json").read_text(encoding="utf-8")
    assert '"evaluation"' in manifest
    assert '"validation"' in manifest
    assert (run_root / "artifacts" / "predictive_model_report.html").exists()
    assert (run_root / "artifacts" / "summary.csv").exists()

    report = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}/export/html"
    )
    assert report.status_code == 200
    assert "Chronological Periods" in report.text
    assert "Validation" in report.text or "validation" in report.text
    assert "out-of-sample" in report.text
    assert "Naive Benchmark Comparison" in report.text
    assert "Warnings" in report.text
    assert "Assumptions" in report.text
    assert "Limitations" in report.text

    csv_export = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}/export/csv"
    )
    assert csv_export.status_code == 200
    assert "Period,Observations,Metric,Model Value,Benchmark Value,Improvement" in csv_export.text
    assert "validation" in csv_export.text
    assert "out-of-sample" in csv_export.text

    json_export = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}/export/json"
    )
    assert json_export.status_code == 200
    assert json_export.json()["manifest"]["evaluation"]["mode"] == "holdout"


def test_predictive_model_api_rejects_invalid_parameters_with_stable_error(
    tmp_path: Path,
) -> None:
    inputs = _client_and_inputs(tmp_path)
    client, dataset_id, _ = inputs
    request = _run_request(dataset_id)
    request["parameters"] = {"momentum_period": 0, "training_window": 3}

    response = client.post("/api/predictive-models/run", json=request)

    assert response.status_code == 422
    assert response.json()["code"] == "parameter_validation_error"


def test_walk_forward_folds_round_trip_through_api_and_run_artifacts(
    tmp_path: Path,
) -> None:
    inputs = _client_and_inputs(tmp_path)
    client, dataset_id, project_id = inputs
    request = _run_request(dataset_id)
    request["parameters"] = {
        "momentum_period": 2,
        "training_window": 3,
        "evaluation_mode": "rolling",
    }

    preview = client.post("/api/predictive-models/run", json=request)

    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["evaluation_mode"] == "rolling"
    assert len(preview_body["folds"]) == len(preview_body["fold_artifacts"]) - 1
    first_fold = preview_body["folds"][0]
    assert first_fold["artifact"]["training_end"] < first_fold["prediction_session_date"]
    assert first_fold["metrics"]["rmse"] >= 0

    saved = client.post(
        f"/api/projects/{project_id}/predictive-models/runs",
        json=request,
    )

    assert saved.status_code == 201
    saved_body = saved.json()
    reopened = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}"
    )
    assert reopened.status_code == 200
    assert reopened.json()["folds"] == saved_body["folds"]

    run_root = tmp_path / "projects" / project_id / "runs" / saved_body["run_id"]
    assert (run_root / "artifacts" / "folds.json").exists()
    predictive_model = json.loads(
        (run_root / "artifacts" / "predictive_model.json").read_text(encoding="utf-8")
    )
    assert "folds" not in predictive_model
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert "folds" not in manifest["evaluation"]

    html_report = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}/export/html"
    )
    assert html_report.status_code == 200
    assert "Walk-forward Folds" in html_report.text

    csv_report = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}/export/csv"
    )
    assert csv_report.status_code == 200
    assert "Fold,Period,Prediction Session" in csv_report.text
    json_report = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}/export/json"
    )
    assert json_report.status_code == 200
    assert len(json_report.json()["predictive_model"]["folds"]) == len(saved_body["folds"])


def test_predictive_model_api_rejects_missing_dataset_with_stable_error(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.post(
        "/api/predictive-models/run",
        json=_run_request("missing-dataset"),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "predictive_model_data_not_found"


def test_saved_predictive_model_failure_is_persisted(tmp_path: Path) -> None:
    inputs = _client_and_inputs(tmp_path)
    client, dataset_id, project_id = inputs
    request = _run_request(dataset_id)
    request["parameters"] = {"momentum_period": 7, "training_window": 3}

    response = client.post(
        f"/api/projects/{project_id}/predictive-models/runs",
        json=request,
    )

    assert response.status_code == 400
    project_runs = tmp_path / "projects" / project_id / "runs"
    failed_statuses = [
        (run_dir / "status.json").read_text(encoding="utf-8")
        for run_dir in project_runs.iterdir()
    ]
    assert any('"status": "failed"' in status_text for status_text in failed_statuses)
