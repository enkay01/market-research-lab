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


def test_dataset_history_as_of_excludes_future_observations(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
        "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,2023-01-02T16:00:00Z\n"
        "AAPL,2023-01-03,157.0,160.0,156.0,159.0,1100000,2023-01-03T16:00:00Z\n"
    )

    res = client.post(
        "/api/datasets",
        data={"source": "test_source"},
        files={"file": ("history.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert res.status_code == 201
    dataset_version_id = res.json()["dataset_version_id"]

    history_res = client.get(
        f"/api/datasets/{dataset_version_id}/history",
        params={"symbol": "AAPL", "as_of": "2023-01-02T18:00:00Z"},
    )
    assert history_res.status_code == 200
    bars = history_res.json()
    assert len(bars) == 2
    assert [b["session_date"] for b in bars] == ["2023-01-01", "2023-01-02"]
    assert bars[0]["security_id"] == "AAPL"
    assert bars[0]["close"] == 154.0
    assert bars[0]["units"] == "USD"


def test_dataset_history_lacking_temporal_provenance_returns_400(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    csv_content = (
        "symbol,date,open,high,low,close,volume\nAAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000\n"
    )

    res = client.post(
        "/api/datasets",
        data={"source": "no_pit_source"},
        files={"file": ("nopit.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert res.status_code == 201
    dataset_version_id = res.json()["dataset_version_id"]

    cov_res = client.get(f"/api/datasets/{dataset_version_id}/coverage")
    assert cov_res.status_code == 200
    assert cov_res.json()["has_temporal_provenance"] is False

    history_res = client.get(
        f"/api/datasets/{dataset_version_id}/history",
        params={"as_of": "2023-01-01T18:00:00Z"},
    )
    assert history_res.status_code == 400
    err = history_res.json()
    assert err["code"] == "point_in_time_data_required"
    assert (
        "Market observations lack required point-in-time eligibility timestamps" in err["message"]
    )
    assert err["details"] == {}

    fund_res = client.get(
        f"/api/datasets/{dataset_version_id}/fundamentals",
        params={"as_of": "2023-01-01T18:00:00Z"},
    )
    assert fund_res.status_code == 400
    err2 = fund_res.json()
    assert err2["code"] == "point_in_time_data_required"
    assert (
        "Market observations lack required point-in-time eligibility timestamps" in err2["message"]
    )


def test_invalid_available_at_returns_stable_point_in_time_error(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,not-a-timestamp\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "invalid_pit_source"},
        files={"file": ("invalid.csv", csv_content.encode("utf-8"), "text/csv")},
    )

    response = client.get(
        f"/api/datasets/{imported.json()['dataset_version_id']}/history",
        params={"as_of": "2023-01-02T18:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "point_in_time_data_required"


def test_historical_run_rejects_partial_temporal_provenance(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Historical analysis"}).json()
    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
        "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "mixed_pit_source"},
        files={"file": ("mixed.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    dataset_version_id = imported.json()["dataset_version_id"]

    current_run = client.post(
        f"/api/projects/{project['id']}/runs",
        params={"dataset_version_id": dataset_version_id},
    )
    assert current_run.status_code == 201

    historical_run = client.post(
        f"/api/projects/{project['id']}/runs",
        params={"dataset_version_id": dataset_version_id, "historical": True},
    )
    assert historical_run.status_code == 400
    assert historical_run.json()["code"] == "point_in_time_data_required"


def test_historical_run_requires_a_dataset_version(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Historical analysis"}).json()

    response = client.post(f"/api/projects/{project['id']}/runs", params={"historical": True})

    assert response.status_code == 422


def test_dataset_fundamentals_endpoint(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    csv_content = (
        "security_id,field,fiscal_period,value,unit,filed_at,available_at\n"
        "AAPL,net_income,2022Q4,30000000000,USD,2023-01-15T00:00:00Z,2023-01-16T09:00:00Z\n"
        "AAPL,net_income,2023Q1,24000000000,USD,2023-04-15T00:00:00Z,2023-04-16T09:00:00Z\n"
    )

    res = client.post(
        "/api/datasets",
        data={"source": "fundamentals_source"},
        files={"file": ("fundamentals.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert res.status_code == 201
    dataset_version_id = res.json()["dataset_version_id"]

    fund_res = client.get(
        f"/api/datasets/{dataset_version_id}/fundamentals",
        params={"symbol": "AAPL", "as_of": "2023-02-01T00:00:00Z"},
    )
    assert fund_res.status_code == 200
    facts = fund_res.json()
    assert len(facts) == 1
    assert facts[0]["security_id"] == "AAPL"
    assert facts[0]["field"] == "net_income"
    assert facts[0]["fiscal_period"] == "2022Q4"
    assert facts[0]["value"] == 30000000000.0
    assert facts[0]["unit"] == "USD"
    assert facts[0]["available_at"] == "2023-01-16T09:00:00Z"


def test_invalid_as_of_format_returns_422(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    res = client.get("/api/datasets/dummy-id/history", params={"as_of": "not-a-date"})
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"

    res = client.get("/api/datasets/dummy-id/fundamentals", params={"as_of": "invalid-timestamp"})
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"
