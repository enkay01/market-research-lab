from fastapi.testclient import TestClient

from market_research_lab.api import create_app


def test_project_can_be_created_reopened_and_revised(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    created = client.post("/api/projects", json={"name": "Quality compounders"})

    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Quality compounders"
    assert project["id"]

    reopened = client.get(f"/api/projects/{project['id']}")
    assert reopened.status_code == 200
    assert reopened.json() == project

    saved = client.post(
        f"/api/projects/{project['id']}/definitions",
        json={
            "kind": "valuation",
            "name": "Acme DCF",
            "definition": {"method": "fcff_dcf", "currency": "USD"},
        },
    )

    assert saved.status_code == 201
    assert saved.json()["revision"] == "v1"
    assert (tmp_path / "projects" / project["id"] / "project.json").exists()
    assert (
        tmp_path
        / "projects"
        / project["id"]
        / "definitions"
        / "valuation"
        / "acme-dcf"
        / "v1"
        / "definition.json"
    ).exists()
    assert (
        tmp_path
        / "projects"
        / project["id"]
        / "definitions"
        / "valuation"
        / "acme-dcf"
        / "draft"
        / "definition.json"
    ).exists()

    run = client.post(f"/api/projects/{project['id']}/runs")
    assert run.status_code == 201
    status_path = tmp_path / "projects" / project["id"] / "runs" / run.json()["id"] / "status.json"
    assert status_path.exists()
    assert status_path.with_name("manifest.json").exists()


def test_validation_errors_have_a_stable_shape(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.post("/api/projects", json={"name": "   "})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
