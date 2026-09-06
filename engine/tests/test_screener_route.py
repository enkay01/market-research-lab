"""Integration tests for the Strategy Screener Sweep route (Issue #118)."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from market_research_lab.api import create_app


@pytest.fixture
def test_client(tmp_path: Path) -> TestClient:
    """Create test client with fresh temporary workspace and multi-security dataset."""
    app = create_app(workspace_root=tmp_path)
    client = TestClient(app)

    # 1. Create project
    proj_resp = client.post("/api/projects", json={"name": "Screener Test Project"})
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 2. Upload CSV with AAPL, MSFT, TSLA and SPY daily bars
    dates = pd.date_range("2024-01-02", periods=25, freq="B").strftime("%Y-%m-%d").tolist()
    records = []
    for i, d in enumerate(dates):
        # AAPL: upward trend
        records.append({
            "symbol": "AAPL",
            "date": d,
            "open": 100.0 + i * 2.5,
            "high": 105.0 + i * 2.5,
            "low": 98.0 + i * 2.5,
            "close": 102.0 + i * 2.5,
            "volume": 50000.0,
            "available_at": f"{d}T21:00:00Z",
        })
        # MSFT: mild trend
        records.append({
            "symbol": "MSFT",
            "date": d,
            "open": 200.0 + i * 1.0,
            "high": 205.0 + i * 1.0,
            "low": 198.0 + i * 1.0,
            "close": 202.0 + i * 1.0,
            "volume": 40000.0,
            "available_at": f"{d}T21:00:00Z",
        })
        # TSLA: downward trend
        records.append({
            "symbol": "TSLA",
            "date": d,
            "open": 300.0 - i * 2.0,
            "high": 305.0 - i * 2.0,
            "low": 295.0 - i * 2.0,
            "close": 298.0 - i * 2.0,
            "volume": 60000.0,
            "available_at": f"{d}T21:00:00Z",
        })
        # SPY: benchmark
        records.append({
            "symbol": "SPY",
            "date": d,
            "open": 400.0 + i * 0.8,
            "high": 405.0 + i * 0.8,
            "low": 398.0 + i * 0.8,
            "close": 402.0 + i * 0.8,
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


def test_post_screener_success(test_client: TestClient) -> None:
    """POST /api/projects/{id}/backtests/screener executes sweep across securities."""
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/screener",
        json={
            "strategy_name": "trend_exhaustion",
            "dataset_version_id": dataset_id,
            "symbols": ["AAPL", "MSFT", "TSLA"],
            "benchmark_symbol": "SPY",
            "starting_cash": 100000.0,
            "parameters": {"fast_period": 2, "slow_period": 4},
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["strategy_name"] == "trend_exhaustion"
    assert data["benchmark_symbol"] == "SPY"
    assert "diagnostic_banner" in data
    assert "candidates" in data

    candidates = data["candidates"]
    assert len(candidates) == 3

    # Ranking must be strictly sequential 1, 2, 3
    ranks = [c["rank"] for c in candidates]
    assert ranks == [1, 2, 3]

    # Sorted descending by net edge
    net_edges = [c["net_edge"] for c in candidates]
    assert net_edges == sorted(net_edges, reverse=True)

    # All expected fields present
    first = candidates[0]
    assert "symbol" in first
    assert "name" in first
    assert "sector" in first
    assert "strategy_return" in first
    assert "benchmark_return" in first
    assert "net_edge" in first
    assert "trades_count" in first
    assert "status" in first
    assert first["status"] in {"PASS", "FAIL"}

    # Diagnostic banner checks
    banner = data["diagnostic_banner"]
    assert "market_edge_detected" in banner
    assert "edge_distribution" in banner
    assert "headline" in banner
    assert "summary" in banner
    assert banner["total_securities"] == 3


def test_post_screener_megacap_preset(test_client: TestClient) -> None:
    """Screener resolves available dataset symbols matching universe preset."""
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/screener",
        json={
            "strategy_name": "trend_exhaustion",
            "dataset_version_id": dataset_id,
            "universe_preset": "megacap",
            "benchmark_symbol": "SPY",
            "parameters": {"fast_period": 2, "slow_period": 4},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) >= 2
    symbols = {c["symbol"] for c in data["candidates"]}
    assert "AAPL" in symbols
    assert "MSFT" in symbols


def test_post_verdict_includes_screener_sweep(test_client: TestClient) -> None:
    """Verdict endpoint attaches screener sweep across dataset securities."""
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/verdict",
        json={
            "strategy_name": "trend_exhaustion",
            "dataset_version_id": dataset_id,
            "symbol": "AAPL",
            "benchmark_symbol": "SPY",
            "parameters": {"fast_period": 2, "slow_period": 4},
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "screener_sweep" in data
    assert data["screener_sweep"] is not None
    sweep = data["screener_sweep"]
    assert "diagnostic_banner" in sweep
    assert "candidates" in sweep
    assert len(sweep["candidates"]) >= 1


def test_post_screener_missing_benchmark(test_client: TestClient) -> None:
    """Missing benchmark price history returns 422 Unprocessable Content."""
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/screener",
        json={
            "strategy_name": "trend_exhaustion",
            "dataset_version_id": dataset_id,
            "symbols": ["AAPL"],
            "benchmark_symbol": "NONEXISTENT",
        },
    )
    assert response.status_code == 422


def test_post_screener_project_not_found(test_client: TestClient) -> None:
    """Nonexistent project returns 404."""
    response = test_client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/backtests/screener",
        json={
            "strategy_name": "trend_exhaustion",
            "symbols": ["AAPL"],
        },
    )
    assert response.status_code == 404
