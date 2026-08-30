"""Tests verifying that each active domain sub-router can be mounted independently."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_research_lab.market_data import MarketDataStore
from market_research_lab.projects import ProjectStore
from market_research_lab.routes import (
    backtests_router,
    cleanup_router,
    indicators_router,
    market_data_router,
    options_router,
    projects_router,
    register_domain_exception_handlers,
    strategies_router,
)
from market_research_lab.routes.deps import get_market_store, get_project_store


def test_projects_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(projects_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_projects_router_isolated_error_contract(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(projects_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    missing_id = uuid4()
    response = client.get(f"/api/projects/{missing_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "project_not_found"
    assert data["message"] == "The requested Project does not exist."


def test_indicators_router_mounts_in_isolation(tmp_path: Path) -> None:
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(indicators_router)

    client = TestClient(app)
    response = client.get("/api/indicators")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_strategies_router_mounts_in_isolation(tmp_path: Path) -> None:
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(strategies_router)

    client = TestClient(app)
    response = client.get("/api/strategies")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_strategies_router_isolated_error_contract(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Strategy Error")
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(strategies_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.post(
        f"/api/projects/{project.id}/strategies/enable",
        json={"name": "sma_crossover", "revision": "v999"},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "revision_not_found"


def test_market_data_router_mounts_in_isolation(tmp_path: Path) -> None:
    market_store = MarketDataStore(tmp_path)
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(market_data_router)
    app.dependency_overrides[get_market_store] = lambda: market_store

    client = TestClient(app)
    response = client.get("/api/securities")
    assert response.status_code == 200
    assert response.json() == []


def test_market_data_router_isolated_error_contract(tmp_path: Path) -> None:
    market_store = MarketDataStore(tmp_path)
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(market_data_router)
    app.dependency_overrides[get_market_store] = lambda: market_store

    client = TestClient(app)
    response = client.get("/api/datasets/missing_version_id/coverage")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "dataset_version_not_found"


def test_backtests_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Backtests")
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(backtests_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{project.id}/backtests")
    assert response.status_code == 200
    assert response.json() == []


def test_backtests_router_isolated_error_contract(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(backtests_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{uuid4()}/backtests")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "project_not_found"


def test_options_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Options")
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(options_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{project.id}/options-backtests")
    assert response.status_code == 200
    assert response.json() == []


def test_options_router_isolated_error_contract(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(options_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.get(f"/api/projects/{uuid4()}/options-backtests")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "project_not_found"


def test_cleanup_router_mounts_in_isolation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Test Cleanup")
    run_id = f"run_{uuid4().hex[:16]}"
    run_dir = tmp_path / "projects" / str(project.id) / "runs" / run_id
    run_dir.mkdir(parents=True)

    app = FastAPI()
    register_domain_exception_handlers(app)
    app.include_router(cleanup_router)
    app.dependency_overrides[get_project_store] = lambda: store

    client = TestClient(app)
    response = client.delete(f"/api/projects/{project.id}/runs/{run_id}")
    assert response.status_code == 204
    assert not run_dir.exists()
