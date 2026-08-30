import io
import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from market_research_lab.api import ExecutionModelAssumptionsRequest, create_app


def test_cash_interest_request_rejects_non_finite_values():
    with pytest.raises(ValueError, match="finite"):
        ExecutionModelAssumptionsRequest.model_validate({"cash_interest_rate": float("nan")})


def test_unexpected_api_error_has_a_diagnostic_id_and_traceback(tmp_path):
    app = create_app(workspace_root=tmp_path, static_dir=tmp_path / "missing-interface")

    @app.get("/api/test-unexpected-error")
    def raise_unexpected_error() -> None:
        raise RuntimeError("diagnostic test failure")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/test-unexpected-error")

    assert response.status_code == 500
    diagnostic_id = response.headers["X-Diagnostic-ID"]
    assert response.json() == {
        "code": "unexpected_error",
        "message": "The application could not complete this request.",
        "details": {},
        "diagnostic_id": diagnostic_id,
    }
    application_log = (tmp_path / "logs" / "application.log").read_text(encoding="utf-8")
    assert f"diagnostic_id={diagnostic_id}" in application_log
    assert "RuntimeError: diagnostic test failure" in application_log


def _tiingo_prices_fetch_json(url: str, _headers: dict[str, str]) -> dict:
    if "/prices" not in url:
        return {"ticker": "AAPL", "name": "Apple Inc.", "exchangeCode": "NASDAQ"}
    return [
        {
            "date": "2023-06-12T00:00:00.000Z",
            "open": 100,
            "high": 105,
            "low": 99,
            "close": 104,
            "volume": 123,
        }
    ]


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


def test_cleanup_api_protects_run_provenance_before_deleting_data(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Cleanup API"}).json()

    imported = client.post(
        "/api/datasets",
        data={"source": "cleanup-source"},
        files={
            "file": (
                "bars.csv",
                b"symbol,date,open,high,low,close,volume\n"
                b"AAPL,2024-01-02,100,101,99,100.5,1000\n",
                "text/csv",
            )
        },
    )
    assert imported.status_code == 201
    dataset_id = imported.json()["dataset_version_id"]
    parquet_files = list((tmp_path / "datasets").glob("*.parquet"))
    assert len(parquet_files) == 1

    created_run = client.post(
        f"/api/projects/{project['id']}/runs",
        params={"dataset_version_id": dataset_id},
    )
    assert created_run.status_code == 201
    run_id = created_run.json()["id"]

    listed = client.get(f"/api/projects/{project['id']}/runs")
    assert listed.status_code == 200
    assert listed.json()[0]["dataset_version_ids"] == [dataset_id]

    blocked = client.delete(f"/api/datasets/{dataset_id}")
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "dataset_version_in_use"
    assert run_id in blocked.json()["message"]
    assert any(
        (r if isinstance(r, str) else r.get("run_id")) == run_id
        for r in blocked.json()["details"]["referencing_runs"]
    )
    assert parquet_files[0].exists()

    deleted_run = client.delete(f"/api/projects/{project['id']}/runs/{run_id}")
    assert deleted_run.status_code == 204
    deleted_dataset = client.delete(f"/api/datasets/{dataset_id}")
    assert deleted_dataset.status_code == 204
    assert client.get("/api/datasets").json() == []
    assert not parquet_files[0].exists()


def test_validation_errors_return_a_stable_error_response(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.post("/api/projects", json={"name": "   "})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("filename", ["bars.json", "bars.parquet"])
def test_dataset_upload_accepts_json_and_parquet(filename, tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    rows = [
        {
            "symbol": "MSFT",
            "date": "2023-01-01",
            "open": 240.0,
            "high": 245.0,
            "low": 239.0,
            "close": 244.0,
            "volume": 500000.0,
        }
    ]
    if filename.endswith(".json"):
        content = io.BytesIO(pd.DataFrame(rows).to_json(orient="records").encode())
    else:
        content = io.BytesIO()
        pd.DataFrame(rows).to_parquet(content, index=False)
        content.seek(0)

    response = client.post(
        "/api/datasets",
        data={"source": "test-source"},
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 201
    coverage = client.get(f"/api/datasets/{response.json()['dataset_version_id']}/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["row_count"] == 1


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


def test_dataset_corporate_actions_endpoint_applies_point_in_time_filter(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    csv_content = (
        "symbol,type,effective_date,value,units,available_at\n"
        "AAPL,split,2023-06-12,4,ratio,2023-06-13T09:00:00Z\n"
        "AAPL,dividend,2023-08-10,0.24,USD/share,2023-08-11T09:00:00Z\n"
    )

    imported = client.post(
        "/api/datasets",
        data={"source": "corporate-actions-source"},
        files={"file": ("corporate-actions.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert imported.status_code == 201
    dataset_version_id = imported.json()["dataset_version_id"]

    coverage = client.get(f"/api/datasets/{dataset_version_id}/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["is_corporate_actions"] is True

    response = client.get(
        f"/api/datasets/{dataset_version_id}/corporate-actions",
        params={"symbol": "AAPL", "as_of": "2023-07-01T00:00:00Z"},
    )
    assert response.status_code == 200
    actions = response.json()
    assert len(actions) == 1
    assert actions[0]["type"] == "split"
    assert actions[0]["effective_date"] == "2023-06-12"
    assert actions[0]["units"] == "ratio"


def test_dataset_catalogue_lists_file_and_provider_versions_in_one_view(tmp_path):
    (tmp_path / ".env.local").write_text("TIINGO_API_TOKEN=private-token\n", encoding="utf-8")
    client = TestClient(
        create_app(workspace_root=tmp_path, provider_fetch_json=_tiingo_prices_fetch_json)
    )

    file_res = client.post(
        "/api/datasets",
        data={"source": "file_source"},
        files={
            "file": (
                "bars.csv",
                (
                    "symbol,date,open,high,low,close,volume,available_at\n"
                    "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    assert file_res.status_code == 201

    download_res = client.post(
        "/api/datasets/download", json={"provider": "tiingo", "symbols": ["AAPL"]}
    )
    assert download_res.status_code == 201

    catalogue = client.get("/api/datasets")
    assert catalogue.status_code == 200
    versions = catalogue.json()
    assert {version["source"] for version in versions} == {"file_source", "tiingo"}
    for version in versions:
        assert version["row_count"] > 0
        assert version["retrieval_time"]
        assert "has_temporal_provenance" in version
        assert "dataset_type" in version


def test_epic2_workflow_ingest_inspect_and_query_historically(tmp_path):
    (tmp_path / ".env.local").write_text("TIINGO_API_TOKEN=private-token\n", encoding="utf-8")
    client = TestClient(
        create_app(workspace_root=tmp_path, provider_fetch_json=_tiingo_prices_fetch_json)
    )

    # File ingestion
    imported = client.post(
        "/api/datasets",
        data={"source": "file_source"},
        files={
            "file": (
                "bars.csv",
                (
                    "symbol,date,open,high,low,close,volume,available_at\n"
                    "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
                    "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,2023-01-02T16:00:00Z\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    assert imported.status_code == 201
    file_version_id = imported.json()["dataset_version_id"]

    # Coverage inspection
    coverage = client.get(f"/api/datasets/{file_version_id}/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["has_temporal_provenance"] is True
    assert coverage.json()["row_count"] == 2

    # Historical query excludes the later-eligible bar
    history = client.get(
        f"/api/datasets/{file_version_id}/history",
        params={"as_of": "2023-01-01T18:00:00Z"},
    )
    assert history.status_code == 200
    assert [bar["session_date"] for bar in history.json()] == ["2023-01-01"]

    # Later observations in a new Dataset Version must not change the earlier
    # as-of result (Epic acceptance criterion 2).
    later = client.post(
        "/api/datasets",
        data={"source": "file_source"},
        files={
            "file": (
                "bars_later.csv",
                (
                    "symbol,date,open,high,low,close,volume,available_at\n"
                    "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
                    "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,2023-01-02T16:00:00Z\n"
                    "AAPL,2023-01-03,157.0,160.0,156.0,159.0,1100000,2023-01-03T16:00:00Z\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )
    assert later.status_code == 201
    later_version_id = later.json()["dataset_version_id"]

    replayed = client.get(
        f"/api/datasets/{later_version_id}/history",
        params={"as_of": "2023-01-01T18:00:00Z"},
    )
    assert replayed.status_code == 200
    assert [bar["session_date"] for bar in replayed.json()] == ["2023-01-01"]

    # Provider download adds versions to the same catalogue.
    downloaded = client.post(
        "/api/datasets/download", json={"provider": "tiingo", "symbols": ["AAPL"]}
    )
    assert downloaded.status_code == 201
    downloaded_ids = set(downloaded.json()["dataset_version_ids"])

    catalogue = client.get("/api/datasets")
    assert catalogue.status_code == 200
    version_ids = {version["id"] for version in catalogue.json()}
    assert {file_version_id, later_version_id} <= version_ids
    assert downloaded_ids <= version_ids
    assert {version["source"] for version in catalogue.json()} == {"file_source", "tiingo"}


def test_invalid_as_of_format_returns_422(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    res = client.get("/api/datasets/dummy-id/history", params={"as_of": "not-a-date"})
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"

    res = client.get("/api/datasets/dummy-id/fundamentals", params={"as_of": "invalid-timestamp"})
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"


def test_securities_watchlist_and_research_workflow(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    # 1. Ingest market dataset to register securities in catalogue
    csv_content = (
        "symbol,name,exchange,currency,date,open,high,low,close,volume\n"
        "AAPL,Apple Inc.,NASDAQ,USD,2023-01-01,150.0,155.0,149.0,154.0,1000000\n"
        "AAPL,Apple Inc.,NASDAQ,USD,2023-01-02,154.0,158.0,153.0,157.0,1200000\n"
        "MSFT,Microsoft Corp.,NASDAQ,USD,2023-01-01,240.0,245.0,239.0,242.0,500000\n"
        "SPY,SPDR S&P 500 ETF,NYSE Arca,USD,2023-01-01,380.0,385.0,379.0,382.0,5000000\n"
    )
    import_res = client.post(
        "/api/datasets",
        data={"source": "test_catalogue"},
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    assert import_res.status_code == 201

    # 2. Search securities (RES-001)
    all_sec = client.get("/api/securities").json()
    assert len(all_sec) == 3
    assert [s["symbol"] for s in all_sec] == ["AAPL", "MSFT", "SPY"]

    filtered_sec = client.get("/api/securities", params={"query": "apple"}).json()
    assert len(filtered_sec) == 1
    assert filtered_sec[0]["symbol"] == "AAPL"

    # Security details with covering dataset summary (RES-005)
    sec_details = client.get(f"/api/securities/{filtered_sec[0]['security_id']}").json()
    assert sec_details["security"]["symbol"] == "AAPL"
    assert sec_details["daily_bars_count"] == 2
    assert sec_details["daily_bars_start"] == "2023-01-01"
    assert sec_details["daily_bars_end"] == "2023-01-02"
    assert len(sec_details["daily_bars_dataset_versions"]) == 1

    # 3. Create a project and manage watchlist (RES-002)
    project = client.post("/api/projects", json={"name": "Alpha Fund"}).json()
    project_id = project["id"]

    empty_wl = client.get(f"/api/projects/{project_id}/watchlist").json()
    assert empty_wl["total"] == 0
    assert empty_wl["items"] == []

    # Attempting to add an uncatalogued security returns 404 security_not_found
    missing_res = client.post(
        f"/api/projects/{project_id}/watchlist",
        json={"identifier": "UNREGISTERED"},
    )
    assert missing_res.status_code == 404
    assert missing_res.json()["code"] == "security_not_found"

    # Add valid securities by symbol or ID
    wl_after_aapl = client.post(
        f"/api/projects/{project_id}/watchlist",
        json={"identifier": "AAPL"},
    )
    assert wl_after_aapl.status_code == 201
    assert wl_after_aapl.json()["total"] == 1

    client.post(
        f"/api/projects/{project_id}/watchlist",
        json={"identifier": "MSFT"},
    )
    client.post(
        f"/api/projects/{project_id}/watchlist",
        json={"identifier": "SPY"},
    )

    # 4. Watchlist filtering and sorting (RES-006)
    # Filter by query
    query_res = client.get(
        f"/api/projects/{project_id}/watchlist",
        params={"query": "micro"},
    ).json()
    assert query_res["total"] == 1
    assert query_res["items"][0]["security"]["symbol"] == "MSFT"

    # Filter by exchange
    nyse_res = client.get(
        f"/api/projects/{project_id}/watchlist",
        params={"exchange": "NYSE Arca"},
    ).json()
    assert nyse_res["total"] == 1
    assert nyse_res["items"][0]["security"]["symbol"] == "SPY"

    # Sorting
    sort_desc = client.get(
        f"/api/projects/{project_id}/watchlist",
        params={"sort_by": "symbol", "sort_order": "desc"},
    ).json()
    assert [item["security"]["symbol"] for item in sort_desc["items"]] == ["SPY", "MSFT", "AAPL"]



def test_indicator_endpoints_and_definition_lifecycle(tmp_path: pytest.TempPathFactory):
    client = TestClient(create_app(workspace_root=tmp_path))

    # 1. List indicators
    res = client.get("/api/indicators")
    assert res.status_code == 200
    indicators = res.json()
    names = [ind["name"] for ind in indicators]
    assert "sma" in names
    assert "ema" in names
    assert "moving_average_crossover" in names

    # 2. Get single indicator metadata
    cross_res = client.get("/api/indicators/moving_average_crossover")
    assert cross_res.status_code == 200
    cross_meta = cross_res.json()
    assert cross_meta["name"] == "moving_average_crossover"
    assert len(cross_meta["parameters"]) == 3

    # 3. Ingest market data for indicator calculation
    csv_content = (
        "symbol,name,exchange,session_date,open,high,low,close,volume,available_at\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-02,100,105,99,102,1000,2024-01-02T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-03,102,108,101,106,1200,2024-01-03T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-04,106,110,105,108,1100,2024-01-04T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-05,108,112,107,110,1300,2024-01-05T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-08,110,111,103,104,1500,2024-01-08T20:00:00Z\n"
    )
    import_res = client.post(
        "/api/datasets",
        data={"source": "test_provider"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert import_res.status_code == 201
    dataset_version_id = import_res.json()["dataset_version_id"]

    # 4. Calculate indicator
    calc_res = client.post(
        "/api/indicators/calculate",
        json={
            "name": "moving_average_crossover",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert calc_res.status_code == 200
    series = calc_res.json()
    assert series["indicator_name"] == "moving_average_crossover"
    assert series["symbol"] == "AAPL"
    assert series["total_bars"] == 5
    assert series["warmup_period"] == 3
    assert series["valid_bars"] == 2
    assert len(series["points"]) == 5

    # Check first point (warmup)
    assert series["points"][0]["is_warmup"] is True
    assert series["points"][0]["session_date"] == "2024-01-02"
    assert series["points"][0]["price"] == 102.0

    # Check 4th point (index 3, first valid bar)
    # Fast SMA(2) of [108, 110] = 109.0
    # Slow SMA(4) of [102, 106, 108, 110] = 106.5
    # Spread = +2.5
    p3 = series["points"][3]
    assert p3["is_warmup"] is False
    assert p3["values"]["fast_ma"] == 109.0
    assert p3["values"]["slow_ma"] == 106.5
    assert p3["values"]["spread"] == 2.5
    assert p3["values"]["state"] == "bullish_above"

    # 5. Invalid parameters return 422
    bad_param_res = client.post(
        "/api/indicators/calculate",
        json={
            "name": "moving_average_crossover",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": {"fast_period": 10, "slow_period": 5},
        },
    )
    assert bad_param_res.status_code == 422
    assert bad_param_res.json()["code"] == "parameter_validation_error"

    # 6. Save indicator definition and revision in a project
    proj_res = client.post("/api/projects", json={"name": "Indicator Research"})
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    save_def_res = client.post(
        f"/api/projects/{proj_id}/definitions",
        json={
            "kind": "indicator",
            "name": "aapl_trend_crossover",
            "definition": {
                "indicator": "moving_average_crossover",
                "symbol": "AAPL",
                "dataset_version_id": dataset_version_id,
                "fast_period": 20,
                "slow_period": 50,
                "ma_type": "sma",
            },
        },
    )
    assert save_def_res.status_code == 201
    assert save_def_res.json()["revision"] == "v1"


def test_strategy_endpoints_and_definition_lifecycle(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    # 1. List strategies
    res = client.get("/api/strategies")
    assert res.status_code == 200
    strategies = res.json()
    names = [s["name"] for s in strategies]
    assert "long_flat_moving_average" in names

    # 2. Get single strategy metadata
    meta_res = client.get("/api/strategies/long_flat_moving_average")
    assert meta_res.status_code == 200
    meta = meta_res.json()
    assert meta["name"] == "long_flat_moving_average"
    assert {p["name"] for p in meta["parameters"]} == {"fast_period", "slow_period", "ma_type"}

    # 3. Ingest eligible market data
    csv_content = (
        "symbol,name,exchange,session_date,open,high,low,close,volume,available_at\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-02,100,105,99,102,1000,2024-01-02T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-03,102,108,101,106,1200,2024-01-03T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-04,106,110,105,108,1100,2024-01-04T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-05,108,112,107,110,1300,2024-01-05T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-08,110,114,109,112,1500,2024-01-08T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-09,112,116,111,114,1400,2024-01-09T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-10,114,118,113,116,1600,2024-01-10T20:00:00Z\n"
    )
    import_res = client.post(
        "/api/datasets",
        data={"source": "test_provider"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert import_res.status_code == 201
    dataset_version_id = import_res.json()["dataset_version_id"]

    # 4. Evaluate strategy emits desired weights and rationale, not orders
    eval_res = client.post(
        "/api/strategies/evaluate",
        json={
            "name": "long_flat_moving_average",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert eval_res.status_code == 200
    result = eval_res.json()
    assert result["strategy_name"] == "long_flat_moving_average"
    assert result["symbol"] == "AAPL"
    assert result["indicator_name"] == "moving_average_crossover"
    assert len(result["targets"]) == 1
    target = result["targets"][0]
    assert target["security_id"] == "AAPL"
    assert target["weight"] == 1.0
    assert "long" in target["rationale"]
    assert target["indicator_state"] == "bullish_above"

    # 5. Save as immutable Definition Revision (CORE-005)
    proj_res = client.post("/api/projects", json={"name": "Strategy Research"})
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    save_res = client.post(
        f"/api/projects/{proj_id}/strategies/evaluate",
        json={
            "name": "long_flat_moving_average",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert save_res.status_code == 201
    saved = save_res.json()
    assert saved["revision"] == "v1"
    assert saved["strategy_revision"] == "long_flat_moving_average:v1"
    assert saved["targets"][0]["weight"] == 1.0
    strategy_defs = tmp_path / "projects" / proj_id / "definitions" / "strategy"
    assert strategy_defs.is_dir()
    revision_files = [
        entry / "v1" / "definition.json" for entry in strategy_defs.iterdir() if entry.is_dir()
    ]
    assert any(path.is_file() for path in revision_files)


def test_strategy_only_uses_observations_eligible_at_decision_time(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    # A downtrend through 2024-01-06, then a sharp rally on 2024-01-09.
    csv_content = (
        "symbol,name,exchange,session_date,open,high,low,close,volume,available_at\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-02,100,100,100,100,1000,2024-01-02T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-03,90,90,90,90,1000,2024-01-03T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-04,80,80,80,80,1000,2024-01-04T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-05,70,70,70,70,1000,2024-01-05T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-06,60,60,60,60,1000,2024-01-06T20:00:00Z\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-09,200,200,200,200,1000,2024-01-09T20:00:00Z\n"
    )
    import_res = client.post(
        "/api/datasets",
        data={"source": "pit_source"},
        files={"file": ("pit.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert import_res.status_code == 201
    dataset_version_id = import_res.json()["dataset_version_id"]

    params = {"fast_period": 2, "slow_period": 4, "ma_type": "sma"}

    # As of the downtrend the Strategy must stay flat...
    early = client.post(
        "/api/strategies/evaluate",
        json={
            "name": "long_flat_moving_average",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": params,
            "as_of": "2024-01-06T21:00:00Z",
        },
    )
    assert early.status_code == 200
    assert early.json()["targets"][0]["weight"] == 0.0
    assert early.json()["latest_session_date"] == "2024-01-06"

    # ...while the same Strategy goes long once the rally is eligible.
    late = client.post(
        "/api/strategies/evaluate",
        json={
            "name": "long_flat_moving_average",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": params,
            "as_of": "2024-01-09T21:00:00Z",
        },
    )
    assert late.status_code == 200
    assert late.json()["targets"][0]["weight"] == 1.0
    assert late.json()["latest_session_date"] == "2024-01-09"


def test_backtest_run_end_to_end_returns_ledger_and_metrics(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    project = client.post("/api/projects", json={"name": "Backtest project"}).json()

    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2024-01-02,100,105,99,102,1000,2024-01-02T20:00:00Z\n"
        "AAPL,2024-01-03,102,108,101,106,1200,2024-01-03T20:00:00Z\n"
        "AAPL,2024-01-04,106,110,105,108,1100,2024-01-04T20:00:00Z\n"
        "AAPL,2024-01-05,108,112,107,110,1300,2024-01-05T20:00:00Z\n"
        "AAPL,2024-01-08,110,114,109,112,1500,2024-01-08T20:00:00Z\n"
        "AAPL,2024-01-09,112,116,111,114,1400,2024-01-09T20:00:00Z\n"
        "AAPL,2024-01-10,114,118,113,116,1600,2024-01-10T20:00:00Z\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "test_source"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201
    dataset_version_id = imported.json()["dataset_version_id"]

    response = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v1",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "start_date": "2024-01-02",
            "end_date": "2024-01-10",
            "starting_cash": 100000,
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
            "execution": {
                "commission_rate": 0.001,
                "slippage_rate": 0.0005,
                "cash_interest_rate": 0.02,
            },
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["run_id"]
    assert result["strategy_revision"] == "long_flat_moving_average:v1"
    assert result["ledger"]
    assert "total_return" in result["metrics"]
    assert result["manifest"]["kind"] == "backtest"
    assert result["specification"]["execution"]["cash_interest_rate"] == 0.02
    assert result["manifest"]["execution"]["cash_interest_rate"] == 0.02
    assert "total_cash_interest" in result["manifest"]["costs"]

    listed = client.get(f"/api/projects/{project['id']}/backtests")
    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == result["run_id"]

    single = client.get(f"/api/projects/{project['id']}/backtests/{result['run_id']}")
    assert single.status_code == 200
    assert single.json()["run_id"] == result["run_id"]


def test_backtest_run_rejects_start_after_end(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Bad window"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v1",
            "dataset_version_id": "any-dataset",
            "symbol": "AAPL",
            "start_date": "2024-01-10",
            "end_date": "2024-01-02",
            "starting_cash": 100000,
            "parameters": {},
        },
    )
    assert response.status_code == 422

    # Verify failed run artifact persistence (CORE-008)
    runs_dir = tmp_path / "projects" / project["id"] / "runs"
    assert runs_dir.is_dir()
    run_folders = list(runs_dir.iterdir())
    assert len(run_folders) == 1
    failed_run = run_folders[0]
    status_file = json.loads((failed_run / "status.json").read_text(encoding="utf-8"))
    assert status_file["status"] == "failed"
    assert "start_date must not be after end_date" in status_file["error"]
    error_artifact = json.loads(
        (failed_run / "artifacts" / "error.json").read_text(encoding="utf-8")
    )
    assert "start_date must not be after end_date" in error_artifact["error"]
    run_log = (failed_run / "logs.txt").read_text(encoding="utf-8")
    assert "Backtest Run failed" in run_log
    assert f"diagnostic_id={response.headers['X-Diagnostic-ID']}" in run_log


def test_backtest_run_exports_html_csv_json(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Export Project"}).json()

    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2024-01-02,100,105,99,102,1000,2024-01-02T20:00:00Z\n"
        "AAPL,2024-01-03,102,108,101,106,1200,2024-01-03T20:00:00Z\n"
        "AAPL,2024-01-04,106,110,105,108,1100,2024-01-04T20:00:00Z\n"
        "AAPL,2024-01-05,108,112,107,110,1300,2024-01-05T20:00:00Z\n"
        "AAPL,2024-01-08,110,114,109,112,1500,2024-01-08T20:00:00Z\n"
        "AAPL,2024-01-09,112,116,111,114,1400,2024-01-09T20:00:00Z\n"
        "AAPL,2024-01-10,114,118,113,116,1600,2024-01-10T20:00:00Z\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "test_source"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201
    version_id = imported.json()["dataset_version_id"]

    response = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v1",
            "dataset_version_id": version_id,
            "symbol": "AAPL",
            "start_date": "2024-01-02",
            "end_date": "2024-01-10",
            "starting_cash": 100000,
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    # HTML export
    html_res = client.get(f"/api/projects/{project['id']}/backtests/{run_id}/export/html")
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    assert f"backtest_{run_id}.html" in html_res.headers["content-disposition"]
    assert "Backtest Report" in html_res.text

    # CSV export
    csv_res = client.get(f"/api/projects/{project['id']}/backtests/{run_id}/export/csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert f"backtest_{run_id}.csv" in csv_res.headers["content-disposition"]
    assert "Performance Metrics" in csv_res.text

    # JSON export
    json_res = client.get(f"/api/projects/{project['id']}/backtests/{run_id}/export/json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    assert f"backtest_manifest_{run_id}.json" in json_res.headers["content-disposition"]
    data = json_res.json()
    assert "manifest" in data
    assert "backtest" in data


def test_backtest_run_multi_symbol_with_benchmark(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Multi-Security Project"}).json()

    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2024-01-02,100,105,99,102,1000,2024-01-02T20:00:00Z\n"
        "AAPL,2024-01-03,102,108,101,106,1200,2024-01-03T20:00:00Z\n"
        "AAPL,2024-01-04,106,110,105,108,1100,2024-01-04T20:00:00Z\n"
        "AAPL,2024-01-05,108,112,107,110,1300,2024-01-05T20:00:00Z\n"
        "MSFT,2024-01-02,200,205,198,202,2000,2024-01-02T20:00:00Z\n"
        "MSFT,2024-01-03,202,208,201,206,2200,2024-01-03T20:00:00Z\n"
        "MSFT,2024-01-04,206,210,205,208,2100,2024-01-04T20:00:00Z\n"
        "MSFT,2024-01-05,208,212,207,210,2300,2024-01-05T20:00:00Z\n"
        "SPY,2024-01-02,400,405,398,402,5000,2024-01-02T20:00:00Z\n"
        "SPY,2024-01-03,402,408,401,404,5200,2024-01-03T20:00:00Z\n"
        "SPY,2024-01-04,404,410,403,406,5100,2024-01-04T20:00:00Z\n"
        "SPY,2024-01-05,406,412,405,408,5300,2024-01-05T20:00:00Z\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "test_source"},
        files={"file": ("multi_bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201
    version_id = imported.json()["dataset_version_id"]

    response = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v1",
            "dataset_version_id": version_id,
            "symbols": ["AAPL", "MSFT"],
            "benchmark_symbol": "SPY",
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
            "starting_cash": 100000,
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["run_id"]
    assert result["specification"]["universe"] == ["AAPL", "MSFT"]
    assert len(result["benchmark_equity_curve"]) == 4
    assert result["metrics"]["benchmark_relative_return"] is not None
    assert "AAPL" in result["ledger"][0]["positions"]
    assert "MSFT" in result["ledger"][0]["positions"]


def test_enable_strategy_revision_requires_an_immutable_revision(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Signals"}).json()

    draft = client.post(
        f"/api/projects/{project['id']}/strategies/enable",
        json={"name": "long_flat_moving_average - AAPL", "revision": "draft"},
    )
    assert draft.status_code == 400
    assert draft.json()["code"] == "revision_not_immutable"

    missing = client.post(
        f"/api/projects/{project['id']}/strategies/enable",
        json={"name": "long_flat_moving_average - AAPL", "revision": "v9"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "revision_not_found"


def test_backtest_run_shorting_and_borrow_fees(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Shorting Strategy Project"}).json()

    # Falling AAPL prices triggers bearish signals (short positions)
    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2024-01-02,100,105,99,100,1000,2024-01-02T20:00:00Z\n"
        "AAPL,2024-01-03,95,96,90,92,1200,2024-01-03T20:00:00Z\n"
        "AAPL,2024-01-04,90,91,85,88,1100,2024-01-04T20:00:00Z\n"
        "AAPL,2024-01-05,85,86,80,82,1300,2024-01-05T20:00:00Z\n"
        "AAPL,2024-01-06,80,81,75,78,1400,2024-01-06T20:00:00Z\n"
        "AAPL,2024-01-07,75,76,70,72,1500,2024-01-07T20:00:00Z\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "pit_short_source"},
        files={"file": ("falling_bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201
    version_id = imported.json()["dataset_version_id"]

    response = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_short_moving_average",
            "strategy_revision": "long_short_moving_average:v1",
            "dataset_version_id": version_id,
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-07",
            "starting_cash": 100000,
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
            "execution": {
                "schedule": "daily",
                "allow_shorting": True,
                "borrow_fee_rate": 0.05,
                "unavailable_borrow": [],
            },
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["run_id"]
    assert result["specification"]["execution"]["allow_shorting"] is True
    assert result["specification"]["execution"]["borrow_fee_rate"] == 0.05
    assert len(result["signals"]) >= 1
    # Check that short positions and borrow fees were produced
    has_short = any(
        row["positions"].get("AAPL", {}).get("shares", 0.0) < 0
        for row in result["ledger"]
    )
    assert has_short
    total_borrow_fees = sum(row.get("borrow_fees", 0.0) for row in result["ledger"])
    assert total_borrow_fees > 0.0


def test_backtest_run_with_corporate_actions_and_calendar(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Corporate Actions Project"}).json()

    # Import DailyBars
    bars_csv = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2024-01-08,10,10,10,10,1000,2024-01-08T20:00:00Z\n"
        "AAPL,2024-01-09,11,11,11,11,1000,2024-01-09T20:00:00Z\n"
        "AAPL,2024-01-10,12,12,12,12,1000,2024-01-10T20:00:00Z\n"
        "AAPL,2024-01-11,13,13,13,13,1000,2024-01-11T20:00:00Z\n"
        "AAPL,2024-01-12,14,14,14,14,1000,2024-01-12T20:00:00Z\n"
        "AAPL,2024-01-16,14,14,14,14,1000,2024-01-16T20:00:00Z\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "bars_source"},
        files={"file": ("bars.csv", io.BytesIO(bars_csv.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201
    version_id = imported.json()["dataset_version_id"]

    # Import Corporate Actions
    actions_csv = (
        "symbol,type,effective_date,value,available_at\n"
        "AAPL,dividend,2024-01-16,0.50,2024-01-12T21:00:00Z\n"
    )
    imported_actions = client.post(
        "/api/datasets",
        data={"source": "actions_source"},
        files={"file": ("actions.csv", io.BytesIO(actions_csv.encode("utf-8")), "text/csv")},
    )
    assert imported_actions.status_code == 201

    # Run backtest with US calendar
    response = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v1",
            "dataset_version_id": version_id,
            "symbols": ["AAPL"],
            "start_date": "2024-01-08",
            "end_date": "2024-01-16",
            "starting_cash": 100000,
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
            "calendar": "US",
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["run_id"]
    assert result["specification"]["calendar"] == "US"
    # Verification of US calendar dates (Jan 8, 9, 10, 11, 12, 16 - MLK Day skipped)
    ledger_dates = [row["session_date"] for row in result["ledger"]]
    assert ledger_dates == [
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
        "2024-01-11",
        "2024-01-12",
        "2024-01-16",
    ]


def test_backtest_run_compare(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Compare Project"}).json()

    csv_content = (
        "symbol,date,open,high,low,close,volume,available_at\n"
        "AAPL,2024-01-02,100,105,99,102,1000,2024-01-02T20:00:00Z\n"
        "AAPL,2024-01-03,102,108,101,106,1200,2024-01-03T20:00:00Z\n"
        "AAPL,2024-01-04,106,110,105,108,1100,2024-01-04T20:00:00Z\n"
        "AAPL,2024-01-05,108,112,107,110,1300,2024-01-05T20:00:00Z\n"
        "AAPL,2024-01-08,110,114,109,112,1500,2024-01-08T20:00:00Z\n"
        "AAPL,2024-01-09,112,116,111,114,1400,2024-01-09T20:00:00Z\n"
        "AAPL,2024-01-10,114,118,113,116,1600,2024-01-10T20:00:00Z\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "test_source"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201
    version_id = imported.json()["dataset_version_id"]

    res1 = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v1",
            "dataset_version_id": version_id,
            "symbol": "AAPL",
            "start_date": "2024-01-02",
            "end_date": "2024-01-10",
            "starting_cash": 100000,
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert res1.status_code == 201
    run_id_1 = res1.json()["run_id"]

    res2 = client.post(
        f"/api/projects/{project['id']}/backtests",
        json={
            "strategy_name": "long_flat_moving_average",
            "strategy_revision": "long_flat_moving_average:v2",
            "dataset_version_id": version_id,
            "symbol": "AAPL",
            "start_date": "2024-01-02",
            "end_date": "2024-01-10",
            "starting_cash": 50000,
            "parameters": {"fast_period": 3, "slow_period": 5, "ma_type": "sma"},
            "execution": {"commission_rate": 0.002},
        },
    )
    assert res2.status_code == 201
    run_id_2 = res2.json()["run_id"]

    # Compare both runs
    cmp_res = client.post(
        f"/api/projects/{project['id']}/backtests/compare",
        json={"run_ids": [run_id_1, run_id_2]},
    )
    assert cmp_res.status_code == 200
    cmp_data = cmp_res.json()
    assert len(cmp_data["items"]) == 2
    assert cmp_data["compared_at"]

    item1 = next(item for item in cmp_data["items"] if item["run_id"] == run_id_1)
    item2 = next(item for item in cmp_data["items"] if item["run_id"] == run_id_2)

    assert item1["strategy_revision"] == "long_flat_moving_average:v1"
    assert item1["starting_cash"] == 100000.0
    assert item1["universe"] == ["AAPL"]
    assert "total_return" in item1["metrics"]

    assert item2["strategy_revision"] == "long_flat_moving_average:v2"
    assert item2["starting_cash"] == 50000.0
    assert item2["execution"]["commission_rate"] == 0.002

    # Validation check: empty run_ids rejected
    empty_cmp = client.post(
        f"/api/projects/{project['id']}/backtests/compare",
        json={"run_ids": []},
    )
    assert empty_cmp.status_code == 422

    # Validation check: non-existent run_id returns 404
    missing_cmp = client.post(
        f"/api/projects/{project['id']}/backtests/compare",
        json={"run_ids": ["non-existent-run-id"]},
    )
    assert missing_cmp.status_code == 404


def test_massive_download_request_and_template_endpoint(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    # Test template endpoint
    template_res = client.get("/api/strategies-meta/template")
    assert template_res.status_code == 200
    assert "SPEC = StrategyMetadata" in template_res.json()["code"]

    # Test strategy list includes built-ins
    strategies_res = client.get("/api/strategies")
    assert strategies_res.status_code == 200
    strategy_names = [s["name"] for s in strategies_res.json()]
    assert "long_flat_moving_average" in strategy_names
    assert "rsi_mean_reversion" in strategy_names
    assert "put_credit_spread_strategy" in strategy_names
