"""Tests verifying that each domain sub-router can be mounted independently."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_research_lab.market_data import MarketDataStore
from market_research_lab.projects import ProjectStore
from market_research_lab.routes import (
    alerts_router,
    backtests_router,
    cleanup_router,
    indicators_router,
    market_data_router,
    options_router,
    predictive_models_router,
    projects_router,
    strategies_router,
    valuations_router,
)
from market_research_lab.routes.deps import get_market_store, get_project_store


def test_projects_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_indicators_router_mounts_in_isolation(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(indicators_router)

    client = TestClient(app)
    response = client.get("/api/indicators")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_strategies_router_mounts_in_isolation(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(strategies_router)

    client = TestClient(app)
    response = client.get("/api/strategies")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_predictive_models_router_mounts_in_isolation(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(predictive_models_router)

    client = TestClient(app)
    response = client.get("/api/predictive-models")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_market_data_router_mounts_in_isolation(tmp_path: Path) -> None:
    market_store = MarketDataStore(tmp_path)
    app = FastAPI()
    app.include_router(market_data_router)
    app.dependency_overrides[get_market_store] = lambda: market_store

    client = TestClient(app)
    response = client.get("/api/securities")
    assert response.status_code == 200
    assert response.json() == []


def test_valuations_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Valuations")
    app = FastAPI()
    app.include_router(valuations_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{project.id}/valuations")
    assert response.status_code == 200
    assert response.json() == []


def test_backtests_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Backtests")
    app = FastAPI()
    app.include_router(backtests_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{project.id}/backtests")
    assert response.status_code == 200
    assert response.json() == []


def test_options_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Options")
    app = FastAPI()
    app.include_router(options_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{project.id}/options-backtests")
    assert response.status_code == 200
    assert response.json() == []


def test_alerts_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Alerts")
    app = FastAPI()
    app.include_router(alerts_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{project.id}/alerts")
    assert response.status_code == 200
    assert response.json() == []


def test_cleanup_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Cleanup")
    run_id = f"run_{uuid4().hex[:16]}"
    run_dir = tmp_path / "projects" / str(project.id) / "runs" / run_id
    run_dir.mkdir(parents=True)

    app = FastAPI()
    app.include_router(cleanup_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.delete(f"/api/projects/{project.id}/runs/{run_id}")
    assert response.status_code == 204
    assert not run_dir.exists()

