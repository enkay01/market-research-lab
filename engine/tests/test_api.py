import json

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

    run = client.post(
        f"/api/projects/{project['id']}/runs",
        json={
            "definition_revisions": [
                {"kind": "valuation", "name": "Acme DCF", "revision": "v1"}
            ],
            "dataset_versions": ["prices-2026-08-09"],
            "parameters": {"starting_cash": 10_000},
        },
    )
    assert run.status_code == 201
    status_path = tmp_path / "projects" / project["id"] / "runs" / run.json()["id"] / "status.json"
    assert status_path.exists()
    assert status_path.with_name("manifest.json").exists()
    manifest = json.loads(status_path.with_name("manifest.json").read_text(encoding="utf-8"))
    assert manifest["definition_revisions"] == [
        {"kind": "valuation", "name": "Acme DCF", "revision": "v1"}
    ]

    reopened_run = client.get(f"/api/projects/{project['id']}/runs/{run.json()['id']}")
    assert reopened_run.status_code == 200
    assert reopened_run.json()["status"] == "pending"
    assert reopened_run.json()["artifacts"] == []

    completed = client.post(f"/api/projects/{project['id']}/runs/{run.json()['id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["artifacts"] == []

    completed_again = client.post(f"/api/projects/{project['id']}/runs/{run.json()['id']}/complete")
    assert completed_again.status_code == 409
    assert completed_again.json()["code"] == "run_not_pending"


def test_saved_draft_can_be_promoted_to_an_immutable_revision(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Quality compounders"}).json()
    draft_url = f"/api/projects/{project['id']}/definitions/valuation/Acme%20DCF/draft"

    saved_draft = client.put(draft_url, json={"definition": {"wacc": 0.09}})
    promoted = client.post(draft_url.replace("/draft", "/revisions"))
    client.put(draft_url, json={"definition": {"wacc": 0.1}})
    promoted_again = client.post(draft_url.replace("/draft", "/revisions"))

    assert saved_draft.status_code == 200
    assert promoted.json() == {"revision": "v1"}
    assert promoted_again.json() == {"revision": "v2"}
    revision_path = (
        tmp_path
        / "projects"
        / project["id"]
        / "definitions"
        / "valuation"
        / "acme-dcf"
        / "v1"
        / "definition.json"
    )
    assert json.loads(revision_path.read_text(encoding="utf-8"))["definition"] == {"wacc": 0.09}


def test_project_can_be_renamed_and_deleted(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    created = client.post("/api/projects", json={"name": "To be renamed"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    renamed = client.patch(f"/api/projects/{project_id}", json={"name": "Renamed project"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed project"
    
    reopened = client.get(f"/api/projects/{project_id}")
    assert reopened.json()["name"] == "Renamed project"

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204

    not_found = client.get(f"/api/projects/{project_id}")
    assert not_found.status_code == 404
    assert not (tmp_path / "projects" / project_id).exists()


def test_validation_errors_have_a_stable_shape(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.post("/api/projects", json={"name": "   "})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_run_cannot_reference_a_missing_definition_revision(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Quality compounders"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/runs",
        json={
            "definition_revisions": [
                {"kind": "valuation", "name": "Acme DCF", "revision": "v1"}
            ]
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "definition_revision_not_found"
