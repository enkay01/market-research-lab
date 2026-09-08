"""Integration tests for the canonical Candidate Ranking route."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from market_research_lab.api import create_app


@pytest.fixture
def test_client(tmp_path: Path) -> TestClient:
    """Create a client with a multi-security daily-bar dataset."""
    app = create_app(workspace_root=tmp_path)
    client = TestClient(app)

    project_response = client.post("/api/projects", json={"name": "Ranking Test Project"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    dates = pd.date_range("2024-01-02", periods=25, freq="B").strftime("%Y-%m-%d").tolist()
    records: list[dict[str, object]] = []
    for index, date in enumerate(dates):
        prices = {
            "AAPL": (100.0 + index * 2.5, 102.0 + index * 2.5, 50000.0),
            "MSFT": (200.0 + index, 202.0 + index, 40000.0),
            "TSLA": (300.0 - index * 2.0, 298.0 - index * 2.0, 60000.0),
            "ZZZ": (150.0, 150.0, 30000.0),
            "SPY": (400.0 + index * 0.8, 402.0 + index * 0.8, 100000.0),
        }
        for symbol, (open_price, close_price, volume) in prices.items():
            records.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "open": open_price,
                    "high": max(open_price, close_price) + 3.0,
                    "low": min(open_price, close_price) - 3.0,
                    "close": close_price,
                    "volume": volume,
                    "available_at": f"{date}T21:00:00Z",
                }
            )

    upload_response = client.post(
        "/api/datasets",
        files={
            "file": (
                "market_bars.csv",
                io.BytesIO(pd.DataFrame(records).to_csv(index=False).encode("utf-8")),
                "text/csv",
            )
        },
        data={"source": "test_import"},
    )
    assert upload_response.status_code == 201

    client.app.state.test_project_id = project_id
    client.app.state.test_dataset_id = upload_response.json()["dataset_version_id"]
    return client


def _ranking_request(dataset_id: str, **overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "strategy_name": "top_n_momentum",
        "strategy_revision": "top_n_momentum:v1",
        "dataset_version_id": dataset_id,
        "symbols": ["AAPL", "MSFT", "TSLA"],
        "benchmark_symbol": "SPY",
        "starting_cash": 100000.0,
        "parameters": {"lookback_period": 2, "top_n": 1, "weighting": "equal"},
    }
    request.update(overrides)
    return request


def test_candidate_ranking_returns_latest_canonical_snapshot(test_client: TestClient) -> None:
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/candidate-ranking",
        json=_ranking_request(dataset_id),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["strategy_name"] == "top_n_momentum"
    assert data["strategy_revision"] == "top_n_momentum:v1"
    assert data["benchmark_symbol"] == "SPY"
    assert set(data) == {
        "strategy_name",
        "strategy_revision",
        "benchmark_symbol",
        "session_date",
        "decision_time",
        "rankings",
    }

    rankings = data["rankings"]
    assert {row["security_id"] for row in rankings} == {"AAPL", "MSFT", "TSLA"}
    assert {(row["session_date"], row["decision_time"]) for row in rankings} == {
        (data["session_date"], data["decision_time"])
    }
    assert [row["rank"] for row in rankings] == [1, 2, 3]
    assert set(rankings[0]) == {
        "session_date",
        "decision_time",
        "security_id",
        "score",
        "rank",
        "selected",
        "target_weight",
        "rationale",
    }
    assert not any("gate" in field for field in rankings[0])


def test_candidate_ranking_default_megacap_uses_every_dataset_security(
    test_client: TestClient,
) -> None:
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/candidate-ranking",
        json=_ranking_request(dataset_id, symbols=None),
    )

    assert response.status_code == 200
    assert {row["security_id"] for row in response.json()["rankings"]} == {
        "AAPL",
        "MSFT",
        "TSLA",
        "ZZZ",
    }


def test_verdict_attaches_primary_run_ranking_without_screener_alias(
    test_client: TestClient,
) -> None:
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/verdict",
        json=_ranking_request(dataset_id, symbols=None, universe_preset="megacap"),
    )

    assert response.status_code == 200
    data = response.json()
    assert "candidate_ranking" in data
    assert data["candidate_ranking"] is not None
    assert "screener_sweep" not in data
    assert len(data["candidate_ranking"]["rankings"]) == 4


def test_candidate_ranking_rejects_non_cross_sectional_strategy(test_client: TestClient) -> None:
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/candidate-ranking",
        json=_ranking_request(
            dataset_id,
            strategy_name="ma_crossover",
            parameters={"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        ),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "parameter_validation_error"


def test_candidate_ranking_rejects_unknown_explicit_symbol(test_client: TestClient) -> None:
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/candidate-ranking",
        json=_ranking_request(dataset_id, symbols=["AAPL", "MISSING"]),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "parameter_validation_error"
    assert "MISSING" in response.json()["message"]


def test_candidate_ranking_validation_errors(test_client: TestClient) -> None:
    project_id = test_client.app.state.test_project_id

    cases = [
        {"strategy_name": "", "symbols": ["AAPL"]},
        {"strategy_name": "top_n_momentum", "starting_cash": 0.0},
        {
            "strategy_name": "top_n_momentum",
            "start_date": "2024-02-01",
            "end_date": "2024-01-01",
        },
        {"strategy_name": "top_n_momentum", "symbols": ["   "]},
    ]
    for case in cases:
        response = test_client.post(
            f"/api/projects/{project_id}/backtests/candidate-ranking",
            json=case,
        )
        assert response.status_code == 422


def test_screener_alias_is_removed(test_client: TestClient) -> None:
    project_id = test_client.app.state.test_project_id
    response = test_client.post(
        f"/api/projects/{project_id}/backtests/screener",
        json={"strategy_name": "top_n_momentum"},
    )
    assert response.status_code == 405


def test_candidate_ranking_requires_existing_benchmark(test_client: TestClient) -> None:
    project_id = test_client.app.state.test_project_id
    dataset_id = test_client.app.state.test_dataset_id

    response = test_client.post(
        f"/api/projects/{project_id}/backtests/candidate-ranking",
        json=_ranking_request(dataset_id, benchmark_symbol="MISSING"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "parameter_validation_error"


def test_candidate_ranking_project_not_found(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/backtests/candidate-ranking",
        json={"strategy_name": "top_n_momentum"},
    )
    assert response.status_code == 404
