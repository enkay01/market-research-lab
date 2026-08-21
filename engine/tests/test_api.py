import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from market_research_lab.api import ExecutionModelAssumptionsRequest, create_app


def test_cash_interest_request_rejects_non_finite_values():
    with pytest.raises(ValueError, match="finite"):
        ExecutionModelAssumptionsRequest.model_validate({"cash_interest_rate": float("nan")})


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

    # 5. Research Thesis operations (RES-003, RES-004)
    # Attempting thesis operation on unwatched security returns 400 security_not_watched
    unwatched_res = client.get(f"/api/projects/{project_id}/research/UNWATCHED_ID")
    assert unwatched_res.status_code == 400
    assert unwatched_res.json()["code"] == "security_not_watched"

    # Watched security returns starter template initially
    aapl_id = filtered_sec[0]["security_id"]
    thesis_initial = client.get(f"/api/projects/{project_id}/research/{aapl_id}").json()
    assert "Research Thesis: AAPL" in thesis_initial["content"]

    # Save thesis
    thesis_md = (
        "# Research Thesis: AAPL\n\n"
        "## Summary\nHigh ecosystem retention.\n\n"
        "## Evidence\n- 2B+ installed active devices.\n\n"
        "## Risks\n- Regulatory pressure.\n"
    )
    save_res = client.put(
        f"/api/projects/{project_id}/research/{aapl_id}",
        json={"content": thesis_md},
    )
    assert save_res.status_code == 200
    assert save_res.json()["summary"] == "High ecosystem retention."
    assert save_res.json()["evidence"] == ["2B+ installed active devices."]
    assert save_res.json()["risks"] == ["Regulatory pressure."]

    # Watchlist now shows has_thesis=True and thesis preview
    wl_updated = client.get(f"/api/projects/{project_id}/watchlist").json()
    aapl_item = next(i for i in wl_updated["items"] if i["security"]["symbol"] == "AAPL")
    assert aapl_item["has_thesis"] is True
    assert aapl_item["thesis_preview"] == "High ecosystem retention."

    # Filter by thesis status (RES-006)
    has_thesis_wl = client.get(
        f"/api/projects/{project_id}/watchlist",
        params={"thesis_status": "has_thesis"},
    ).json()
    assert has_thesis_wl["total"] == 1
    assert has_thesis_wl["items"][0]["security"]["symbol"] == "AAPL"

    no_thesis_wl = client.get(
        f"/api/projects/{project_id}/watchlist",
        params={"thesis_status": "no_thesis"},
    ).json()
    assert no_thesis_wl["total"] == 2

    # 6. Removing security retains thesis file, re-adding restores research
    del_res = client.delete(f"/api/projects/{project_id}/watchlist/{aapl_id}")
    assert del_res.status_code == 200
    assert del_res.json()["total"] == 2

    # Re-add AAPL
    client.post(f"/api/projects/{project_id}/watchlist", json={"identifier": "AAPL"})
    restored_thesis = client.get(f"/api/projects/{project_id}/research/{aapl_id}").json()
    assert restored_thesis["summary"] == "High ecosystem retention."

    # 7. Persistence across restart
    restarted_client = TestClient(create_app(workspace_root=tmp_path))
    restarted_wl = restarted_client.get(f"/api/projects/{project_id}/watchlist").json()
    assert restarted_wl["total"] == 3
    restarted_thesis = restarted_client.get(f"/api/projects/{project_id}/research/{aapl_id}").json()
    assert restarted_thesis["summary"] == "High ecosystem retention."


def test_comparable_valuation_uses_local_inputs_and_keeps_provenance(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    prices = (
        "symbol,name,exchange,currency,date,open,high,low,close,volume\n"
        "AAPL,Apple Inc.,NASDAQ,USD,2023-01-01,100,100,100,100,10\n"
        "MSFT,Microsoft Corp.,NASDAQ,USD,2023-01-01,200,200,200,200,10\n"
    )
    price_import = client.post(
        "/api/datasets",
        data={"source": "prices"},
        files={"file": ("prices.csv", prices, "text/csv")},
    )
    assert price_import.status_code == 201

    fundamentals = (
        "security_id,field,fiscal_period,value,unit,filed_at\n"
        "AAPL,shares_outstanding,2023FY,3,shares,2023-01-01T00:00:00Z\n"
        "AAPL,total_debt,2023FY,50,USD,2023-01-01T00:00:00Z\n"
        "AAPL,cash,2023FY,20,USD,2023-01-01T00:00:00Z\n"
        "AAPL,revenue,2023FY,100,USD,2023-01-01T00:00:00Z\n"
        "AAPL,ebitda,2023FY,25,USD,2023-01-01T00:00:00Z\n"
        "AAPL,net_income,2023FY,10,USD,2023-01-01T00:00:00Z\n"
        "AAPL,free_cash_flow,2023FY,15,USD,2023-01-01T00:00:00Z\n"
        "MSFT,shares_outstanding,2023FY,3,shares,2023-01-01T00:00:00Z\n"
        "MSFT,total_debt,2023FY,100,USD,2023-01-01T00:00:00Z\n"
        "MSFT,cash,2023FY,50,USD,2023-01-01T00:00:00Z\n"
        "MSFT,revenue,2023FY,200,USD,2023-01-01T00:00:00Z\n"
        "MSFT,ebitda,2023FY,50,USD,2023-01-01T00:00:00Z\n"
        "MSFT,net_income,2023FY,20,USD,2023-01-01T00:00:00Z\n"
        "MSFT,free_cash_flow,2023FY,30,USD,2023-01-01T00:00:00Z\n"
    )
    fundamental_import = client.post(
        "/api/datasets",
        data={"source": "fundamentals"},
        files={"file": ("fundamentals.csv", fundamentals, "text/csv")},
    )
    assert fundamental_import.status_code == 201

    response = client.post(
        "/api/valuations/comparables",
        json={"target_security_id": "AAPL", "peer_security_ids": ["MSFT"]},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["target"]["price_to_earnings"] == 30
    assert result["target"]["ev_to_revenue"] == 3.3
    assert result["peers"][0]["ev_to_ebitda"] == 13
    assert result["peer_medians"]["free_cash_flow_yield"] == 0.05
    assert (
        result["target"]["inputs"]["provenance"]["revenue"]
        == (fundamental_import.json()["dataset_version_id"])
    )
    assert result["target"]["inputs"]["units"]["revenue"] == "USD"
    project = client.post("/api/projects", json={"name": "Comparable research"}).json()
    saved = client.post(
        f"/api/projects/{project['id']}/valuations/comparables",
        json={"target_security_id": "AAPL", "peer_security_ids": ["MSFT"]},
    )
    assert saved.status_code == 201
    saved_result = saved.json()
    assert saved_result["method_revision"] == "trading_comparables:v1"
    assert saved_result["run_id"]
    manifest = (
        tmp_path / "projects" / project["id"] / "runs" / saved_result["run_id"] / "manifest.json"
    )
    assert manifest.exists()
    reloaded = client.get(f"/api/projects/{project['id']}/valuations")
    assert reloaded.status_code == 200
    assert reloaded.json()[0]["result"]["target"]["symbol"] == "AAPL"
    assert reloaded.json()[0]["result"]["method_revision"] == "trading_comparables:v1"
    assert reloaded.json()[0]["result"]["run_id"] == saved_result["run_id"]
    assert result["dataset_version_ids"] == sorted(
        [price_import.json()["dataset_version_id"], fundamental_import.json()["dataset_version_id"]]
    )


def test_dcf_valuation_endpoints_seed_revisions_and_durability(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    prices = (
        "symbol,name,exchange,currency,date,open,high,low,close,volume\n"
        "AAPL,Apple Inc.,NASDAQ,USD,2023-01-01,150,150,150,150,1000\n"
        "MSFT,Microsoft Corporation,NASDAQ,USD,2023-01-01,300,300,300,300,1000\n"
    )
    price_import = client.post(
        "/api/datasets",
        data={"source": "prices"},
        files={"file": ("prices.csv", prices, "text/csv")},
    )
    assert price_import.status_code == 201

    fundamentals = (
        "security_id,field,fiscal_period,value,unit,filed_at\n"
        "AAPL,shares_outstanding,2023FY,10,shares,2023-01-01T00:00:00Z\n"
        "AAPL,total_debt,2023FY,50,USD,2023-01-01T00:00:00Z\n"
        "AAPL,cash,2023FY,30,USD,2023-01-01T00:00:00Z\n"
        "AAPL,revenue,2023FY,200,USD,2023-01-01T00:00:00Z\n"
        "AAPL,ebitda,2023FY,60,USD,2023-01-01T00:00:00Z\n"
        "AAPL,net_income,2023FY,40,USD,2023-01-01T00:00:00Z\n"
        "MSFT,shares_outstanding,2023FY,20,shares,2023-01-01T00:00:00Z\n"
        "MSFT,total_debt,2023FY,40,USD,2023-01-01T00:00:00Z\n"
        "MSFT,cash,2023FY,50,USD,2023-01-01T00:00:00Z\n"
        "MSFT,revenue,2023FY,300,USD,2023-01-01T00:00:00Z\n"
        "MSFT,ebitda,2023FY,100,USD,2023-01-01T00:00:00Z\n"
        "MSFT,net_income,2023FY,70,USD,2023-01-01T00:00:00Z\n"
    )
    fundamental_import = client.post(
        "/api/datasets",
        data={"source": "fundamentals"},
        files={"file": ("fundamentals.csv", fundamentals, "text/csv")},
    )
    assert fundamental_import.status_code == 201

    project = client.post("/api/projects", json={"name": "Valuation DCF Lab"}).json()

    # 1. Seed DCF inputs from local catalogue
    seed_res = client.get(f"/api/projects/{project['id']}/valuations/seed/AAPL")
    assert seed_res.status_code == 200
    seed_data = seed_res.json()
    assert seed_data["symbol"] == "AAPL"
    assert seed_data["base_revenue"] == 200.0
    assert seed_data["shares_outstanding"] == 10.0
    assert seed_data["total_debt"] == 50.0
    assert seed_data["cash"] == 30.0
    assert seed_data["market_cap"] == 1500.0

    # 2. Pure DCF calculation endpoint
    dcf_req = {
        "target_security_id": "AAPL",
        "base_revenue": 200.0,
        "revenue_growth_rate": 0.08,
        "operating_margin": 0.30,
        "tax_rate": 0.21,
        "reinvestment_rate": 0.20,
        "wacc": 0.085,
        "terminal_growth_rate": 0.025,
        "shares_outstanding": 10.0,
        "total_debt": 50.0,
        "cash": 30.0,
        "forecast_years": 5,
    }
    calc_res = client.post("/api/valuations/dcf", json=dcf_req)
    assert calc_res.status_code == 200
    calc_data = calc_res.json()
    assert calc_data["symbol"] == "AAPL"
    assert calc_data["value_per_share"] is not None
    assert calc_data["value_per_share"] > 0
    assert len(calc_data["forecast_cash_flows"]) == 5
    assert len(calc_data["scenarios"]) == 3
    assert len(calc_data["sensitivity"]["grid"]) == 5
    assert calc_data["inputs"]["base_revenue"] == 200.0
    assert calc_data["inputs"]["tax_rate"] == 0.21
    assert "market_cap" in calc_data["provenance"]
    assert calc_data["units"]["market_cap"] == "USD"

    # 3. Save DCF revision v1
    save1 = client.post(f"/api/projects/{project['id']}/valuations/dcf", json=dcf_req)
    assert save1.status_code == 201
    save1_data = save1.json()
    assert save1_data["method_revision"] == "fcff_dcf:v1"
    assert save1_data["inputs"]["tax_rate"] == 0.21
    run1_id = save1_data["run_id"]
    assert run1_id

    # 4. Modify assumption (growth 0.12) and save DCF revision v2
    dcf_req["revenue_growth_rate"] = 0.12
    save2 = client.post(f"/api/projects/{project['id']}/valuations/dcf", json=dcf_req)
    assert save2.status_code == 201
    save2_data = save2.json()
    assert save2_data["method_revision"] == "fcff_dcf:v2"
    run2_id = save2_data["run_id"]
    assert run2_id != run1_id

    # 5. Check artifacts written to disk
    runs_dir = tmp_path / "projects" / project["id"] / "runs"
    assert (runs_dir / run1_id / "manifest.json").exists()
    assert (runs_dir / run1_id / "artifacts" / "valuation.json").exists()
    assert (runs_dir / run1_id / "artifacts" / "valuation_report.html").exists()
    assert (runs_dir / run1_id / "artifacts" / "summary.csv").exists()

    # 6. Test exports (HTML, CSV, JSON)
    html_export = client.get(f"/api/projects/{project['id']}/valuations/{run1_id}/export/html")
    assert html_export.status_code == 200
    assert "<!DOCTYPE html>" in html_export.text
    assert "fcff_dcf:v1" in html_export.text
    assert "Out-of-sample" in html_export.text

    csv_export = client.get(f"/api/projects/{project['id']}/valuations/{run1_id}/export/csv")
    assert csv_export.status_code == 200
    assert "Value Per Share" in csv_export.text

    json_export = client.get(f"/api/projects/{project['id']}/valuations/{run1_id}/export/json")
    assert json_export.status_code == 200
    assert "manifest" in json_export.json()
    assert "valuation" in json_export.json()
    assert "inputs" in json_export.json()["valuation"]

    # 7. Side-by-side comparison endpoint
    comp_res = client.post(
        f"/api/projects/{project['id']}/valuations/compare",
        json={"run_ids": [run1_id, run2_id]},
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert len(comp_data["items"]) == 2
    assert comp_data["items"][0]["method_revision"] == "fcff_dcf:v1"
    assert comp_data["items"][1]["method_revision"] == "fcff_dcf:v2"
    assert comp_data["items"][0]["key_assumptions"]["tax_rate"] == 0.21
    assert comp_data["items"][0]["key_assumptions"]["reinvestment_rate"] == 0.20
    assert comp_data["items"][1]["value_per_share"] > comp_data["items"][0]["value_per_share"]

    # Save a comparable company valuation to test incompatible comparison validation
    comp_save = client.post(
        f"/api/projects/{project['id']}/valuations/comparables",
        json={"target_security_id": "AAPL", "peer_security_ids": ["MSFT"]},
    )
    assert comp_save.status_code == 201
    comp_run_id = comp_save.json()["run_id"]

    incomp_res = client.post(
        f"/api/projects/{project['id']}/valuations/compare",
        json={"run_ids": [run1_id, comp_run_id]},
    )
    assert incomp_res.status_code == 422
    assert incomp_res.json()["detail"]["code"] == "incompatible_valuation_methods"

    # 8. Test durability after restart/reloading app instance
    reloaded_client = TestClient(create_app(workspace_root=tmp_path))
    val_list = reloaded_client.get(f"/api/projects/{project['id']}/valuations")
    assert val_list.status_code == 200
    vals = val_list.json()
    assert len(vals) == 3
    assert {v["method_revision"] for v in vals} == {
        "fcff_dcf:v1",
        "fcff_dcf:v2",
        "trading_comparables:v1",
    }


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


def test_strategy_model_feed_requires_a_completed_benchmark_comparison(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Model gate"}).json()
    request = {
        "name": "long_flat_moving_average",
        "dataset_version_id": "dataset-not-used-before-model-gate",
        "symbol": "AAPL",
        "parameters": {"predictive_model_run_id": "missing-run"},
    }

    missing_run = client.post(
        f"/api/projects/{project['id']}/strategies/evaluate", json=request
    )

    assert missing_run.status_code == 400
    assert missing_run.json()["code"] == "strategy_evaluation_error"
    assert "MOD-009" in missing_run.json()["message"]

    request["parameters"] = {
        "predictive_model_evaluation": {"evaluation": {"mode": "holdout"}}
    }
    incomplete_run = client.post(
        f"/api/projects/{project['id']}/strategies/evaluate", json=request
    )

    assert incomplete_run.status_code == 400
    assert incomplete_run.json()["code"] == "strategy_evaluation_error"
    assert "persisted Predictive Model Run" in incomplete_run.json()["message"]

    fabricated_run = {
        "evaluation": {
            "benchmark": {
                "name": "zero_return",
                "completed": True,
                "period_metrics": {
                    "test": {"mae": 1.0, "rmse": 1.0, "r2": 0.0}
                },
                "out_of_sample_comparison": {
                    "benchmark_name": "zero_return",
                    "period": "test",
                    "sample_scope": "out_of_sample",
                    "observations": 1,
                    "same_eligible_periods": True,
                    "model_rmse": 1.0,
                    "benchmark_rmse": 1.0,
                    "rmse_improvement": 0.0,
                    "model_mae": 1.0,
                    "benchmark_mae": 1.0,
                    "mae_improvement": 0.0,
                    "model_r2": 0.0,
                    "benchmark_r2": 0.0,
                    "status": "evaluated",
                    "comparison_complete": True,
                },
            },
            "is_eligible_for_strategy": True,
        }
    }
    request["parameters"] = {"predictive_model_evaluation": fabricated_run}
    fabricated = client.post(
        f"/api/projects/{project['id']}/strategies/evaluate", json=request
    )

    assert fabricated.status_code == 400
    assert "persisted Predictive Model Run" in fabricated.json()["message"]

    preview = client.post("/api/strategies/evaluate", json=request)
    assert preview.status_code == 400
    assert "saved Predictive Model Run" in preview.json()["message"]


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


def test_enable_and_refresh_produces_a_traceable_signal(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Signals"}).json()

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
    imported = client.post(
        "/api/datasets",
        data={"source": "test_provider"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    dataset_version_id = imported.json()["dataset_version_id"]

    saved = client.post(
        f"/api/projects/{project['id']}/strategies/evaluate",
        json={
            "name": "long_flat_moving_average",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    assert saved.status_code == 201
    definition_name = f"{saved.json()['strategy_name']} - {saved.json()['symbol']}"
    assert saved.json()["revision"] == "v1"

    listed = client.get(f"/api/projects/{project['id']}/strategies")
    assert listed.status_code == 200
    listed_revisions = listed.json()
    assert any(
        item["name"] == definition_name and item["revision"] == "v1"
        for item in listed_revisions
    )

    enabled = client.post(
        f"/api/projects/{project['id']}/strategies/enable",
        json={"name": definition_name, "revision": "v1"},
    )
    assert enabled.status_code == 201

    enabled_list = client.get(f"/api/projects/{project['id']}/strategies/enabled")
    assert enabled_list.status_code == 200
    assert enabled_list.json()[0]["revision"] == "v1"

    refreshed = client.post(f"/api/projects/{project['id']}/alerts/refresh")
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["failures"] == []
    assert len(body["signals"]) == 1
    signal = body["signals"][0]
    assert signal["security_id"] == "AAPL"
    assert signal["action"] == "long"
    assert signal["weight"] == 1.0
    assert signal["strategy_revision"] == f"{definition_name}:v1"
    assert signal["decision_time"]
    assert signal["data_time"] == "2024-01-10T20:00:00Z"
    assert "long" in signal["rationale"]
    assert signal["dataset_version_id"] == dataset_version_id

    alerts = client.get(f"/api/projects/{project['id']}/alerts")
    assert alerts.status_code == 200
    assert len(alerts.json()) == 1
    assert alerts.json()[0]["signal_id"] == signal["signal_id"]


def test_refresh_preserves_failure_and_creates_no_partial_signal(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Signals"}).json()

    csv_content = (
        "symbol,name,exchange,session_date,open,high,low,close,volume\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-02,100,105,99,102,1000\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-03,102,108,101,106,1200\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-04,106,110,105,108,1100\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-05,108,112,107,110,1300\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-08,110,114,109,112,1500\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-09,112,116,111,114,1400\n"
        "AAPL,Apple Inc.,NASDAQ,2024-01-10,114,118,113,116,1600\n"
    )
    imported = client.post(
        "/api/datasets",
        data={"source": "test_provider"},
        files={"file": ("bars.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    dataset_version_id = imported.json()["dataset_version_id"]

    saved = client.post(
        f"/api/projects/{project['id']}/strategies/evaluate",
        json={
            "name": "long_flat_moving_average",
            "dataset_version_id": dataset_version_id,
            "symbol": "AAPL",
            "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        },
    )
    definition_name = f"{saved.json()['strategy_name']} - {saved.json()['symbol']}"
    client.post(
        f"/api/projects/{project['id']}/strategies/enable",
        json={"name": definition_name, "revision": "v1"},
    )

    refreshed = client.post(f"/api/projects/{project['id']}/alerts/refresh")
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["signals"] == []
    assert len(body["failures"]) == 1
    assert body["failures"][0]["strategy_revision"] == f"{definition_name}:v1"

    alerts = client.get(f"/api/projects/{project['id']}/alerts")
    assert alerts.json() == []
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
