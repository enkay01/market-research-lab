"""HTTP seam tests for Predictive Model metadata, execution, and persistence."""

from __future__ import annotations

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
        "symbol,date,open,high,low,close,volume",
        "AAPL,2024-01-01,100,100,100,100,1000",
        "AAPL,2024-01-02,102,102,102,102,1000",
        "AAPL,2024-01-03,101,101,101,101,1000",
        "AAPL,2024-01-04,105,105,105,105,1000",
        "AAPL,2024-01-05,104,104,104,104,1000",
        "AAPL,2024-01-06,108,108,108,108,1000",
        "AAPL,2024-01-07,107,107,107,107,1000",
        "AAPL,2024-01-08,111,111,111,111,1000",
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
    assert preview_body["artifact"]["training_observations"] == 3
    assert preview_body["predictions"][-1]["actual_target"] is None
    assert preview_body["metrics"]["in_sample_r2"] is not None
    assert preview_body["out_of_sample_status"] == "not_available_until_chronological_splits"

    saved = client.post(
        f"/api/projects/{project_id}/predictive-models/runs",
        json=request,
    )

    assert saved.status_code == 201
    saved_body = saved.json()
    assert saved_body["run_id"]
    assert saved_body["model_revision"].endswith(":v1")

    listed = client.get(f"/api/projects/{project_id}/predictive-models/runs")
    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == saved_body["run_id"]

    reopened = client.get(
        f"/api/projects/{project_id}/predictive-models/runs/{saved_body['run_id']}"
    )
    assert reopened.status_code == 200
    assert reopened.json()["artifact"] == saved_body["artifact"]
    assert reopened.json()["predictions"] == saved_body["predictions"]


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
