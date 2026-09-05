"""Integration tests for the Strategy Verdict route (Issue #114)."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from market_research_lab.api import create_app


@pytest.fixture
def test_client(tmp_path: Path) -> TestClient:
    """Create test client with fresh temporary workspace and sample daily dataset."""
    app = create_app(workspace_root=tmp_path)
    client = TestClient(app)

    # 1. Create project
    proj_resp = client.post("/api/projects", json={"name": "Verdict Test Project"})
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 2. Upload CSV with AAPL and SPY daily bars
    dates = pd.date_range("2024-01-02", periods=20, freq="B").strftime("%Y-%m-%d").tolist()
    records = []
    for i, d in enumerate(dates):
        records.append({
            "symbol": "AAPL",
            "date": d,
            "open": 100.0 + i * 2.0,
            "high": 105.0 + i * 2.0,
            "low": 98.0 + i * 2.0,
            "close": 102.0 + i * 2.0,
            "volume": 50000.0,
            "available_at": f"{d}T21:00:00Z",
        })
        records.append({
            "symbol": "SPY",
            "date": d,
            "open": 400.0 + i * 1.0,
            "high": 405.0 + i * 1.0,
            "low": 398.0 + i * 1.0,
            "close": 402.0 + i * 1.0,
            "volume": 100000.0,
            "available_at": f"{d}T21:00:00Z",
        })

    df = pd.DataFrame(records)
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    upload_resp = client.post(
        "/api/datasets",
        files={"file": ("market_bars.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"source": "test_import"},
    )
    assert upload_resp.status_code == 201
    dataset_version_id = upload_resp.json()["dataset_version_id"]

    client.app.state.test_project_id = project_id
    client.app.state.test_dataset_id = dataset_version_id
    return client


def test_post_verdict_success(test_client: TestClient) -> None:
    """POST /api/projects/{id}/backtests/verdict executes and returns typed verdict response."""
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/verdict",
        json={
            "strategy_name": "trend_exhaustion",
            "dataset_version_id": dataset_id,
            "symbol": "AAPL",
            "benchmark_symbol": "SPY",
            "holdout_ratio": 0.25,
            "starting_cash": 100000.0,
            "parameters": {"fast_period": 2, "slow_period": 4},
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "overall_passed" in data
    assert "headline_verdict" in data
    assert "gates" in data
    assert len(data["gates"]) == 2
    assert [tier["multiplier"] for tier in data["friction_ladder"]] == [1, 2, 3]
    assert data["gates"][0]["gate_number"] == 1
    assert data["gates"][0]["name"] == "Benchmark Hurdle"

    assert "in_sample_metrics" in data
    assert "out_of_sample_metrics" in data
    assert "combined_metrics" in data
    assert "equity_curve" in data
    assert len(data["equity_curve"]) > 0

    # Ensure holdout partitioning is present on equity curve
    is_holdout_flags = [pt["is_holdout"] for pt in data["equity_curve"]]
    assert False in is_holdout_flags
    assert True in is_holdout_flags


def test_post_verdict_invalid_holdout_split(test_client: TestClient) -> None:
    """Holdout ratio outside bounds returns 422 validation error."""
    project_id = test_client.app.state.test_project_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/verdict",
        json={
            "strategy_name": "trend_exhaustion",
            "symbol": "AAPL",
            "holdout_ratio": 0.90,  # Invalid: > 0.50
        },
    )
    assert response.status_code == 422


def test_post_verdict_project_not_found(test_client: TestClient) -> None:
    """Nonexistent project returns 404."""
    response = test_client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/backtests/verdict",
        json={
            "strategy_name": "trend_exhaustion",
            "symbol": "AAPL",
        },
    )
    assert response.status_code == 404
