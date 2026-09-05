from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import market_research_lab.downloads as downloads_module
from market_research_lab.api import create_app
from market_research_lab.market_data import MarketDataStore
from market_research_lab.providers import (
    ProviderCredentials,
    ProviderDownloadError,
    TiingoDownloadSpec,
)


def test_provider_download_creates_dataset_versions_without_returning_credentials(tmp_path):
    def fetch_json(url, headers):
        if "/submissions/" in url:
            return {"filings": {"recent": {"accessionNumber": [], "acceptanceDateTime": []}}}
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
                "adjClose": 52,
                "divCash": 0.24,
                "splitFactor": 1,
            }
        ]

    (tmp_path / ".env.local").write_text("TIINGO_API_TOKEN=private-token\n", encoding="utf-8")
    app = create_app(workspace_root=tmp_path, provider_fetch_json=fetch_json)
    app.state.provider_wait = lambda _: None
    response = TestClient(app).post(
        "/api/downloads",
        json={
            "security_list_id": "dow-30",
            "start_date": "2023-06-01",
            "end_date": "2023-06-30",
            "downloads": [{"provider": "tiingo", "data_types": ["daily_bars"]}],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert "private-token" not in json.dumps(body)


def test_provider_failure_does_not_create_a_dataset_version(tmp_path):
    import time

    def fetch_json(_url, _headers):
        raise RuntimeError("upstream unavailable")

    (tmp_path / ".env.local").write_text("TIINGO_API_TOKEN=private-token\n", encoding="utf-8")
    app = create_app(workspace_root=tmp_path, provider_fetch_json=fetch_json)
    app.state.provider_wait = lambda _: None
    client = TestClient(app)
    response = client.post(
        "/api/downloads",
        json={
            "security_list_id": "dow-30",
            "start_date": "2023-06-01",
            "end_date": "2023-06-30",
            "downloads": [{"provider": "tiingo", "data_types": ["daily_bars"]}],
        },
    )

    assert response.status_code == 202
    download_id = response.json()["download_id"]
    for _ in range(50):
        snap = client.get(f"/api/downloads/{download_id}").json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.01)

    assert snap["state"] == "failed"
    assert not list((tmp_path / "datasets").glob("*.parquet"))


def test_sec_download_without_acceptance_time_is_not_historically_eligible(tmp_path):
    def fetch_json(url, _headers):
        if "/submissions/" in url:
            return {
                "name": "Example Corp",
                "tickers": ["EXMP"],
                "exchanges": ["NASDAQ"],
                "filings": {"recent": {}},
            }
        return {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [
                                {
                                    "accn": "0000000000-23-000001",
                                    "form": "10-K",
                                    "filed": "2023-04-20",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "end": "2022-12-31",
                                    "val": 100,
                                }
                            ]
                        }
                    }
                }
            }
        }

    (tmp_path / ".env.local").write_text(
        "SEC_EDGAR_USER_AGENT=Market Research Lab test@example.com\n",
        encoding="utf-8",
    )
    from market_research_lab.providers import SecEdgarDownloadSpec

    versions = downloads_module.download_provider(
        MarketDataStore(tmp_path),
        SecEdgarDownloadSpec(ciks=("1",)),
        credentials=ProviderCredentials(
            sec_edgar_user_agent="Market Research Lab test@example.com"
        ),
        fetch_json=fetch_json,
    )

    client = TestClient(create_app(workspace_root=tmp_path, provider_fetch_json=fetch_json))
    version_id = versions[0].id
    coverage = client.get(f"/api/datasets/{version_id}/coverage")
    assert coverage.json()["has_temporal_provenance"] is False
    assert coverage.json()["coverage_start"] == "2022-12-31"
    historical = client.get(
        f"/api/datasets/{version_id}/fundamentals",
        params={"as_of": "2023-05-01T00:00:00Z"},
    )
    assert historical.status_code == 400
    assert historical.json()["code"] == "point_in_time_data_required"

def test_download_removes_saved_versions_when_a_later_group_fails():
    class StoredVersion:
        def __init__(self, version_id: str) -> None:
            self.id = version_id

    class Store:
        def __init__(self) -> None:
            self.ingest_calls = 0
            self.discarded: list[str] = []

        def ingest_records(self, *_args, **_kwargs) -> StoredVersion:
            self.ingest_calls += 1
            if self.ingest_calls == 2:
                raise OSError("second Dataset Version failed")
            return StoredVersion("saved-first")

        def discard_dataset_version(self, version: StoredVersion) -> None:
            self.discarded.append(version.id)

        def upsert_securities(self, *_args, **_kwargs) -> None:
            raise AssertionError("Securities must not be saved after a failed Dataset Version.")

    def fetch_json(url: str, _headers: dict[str, str]):
        if "/prices" not in url:
            return {"ticker": "AAPL", "name": "Apple Inc.", "exchangeCode": "NASDAQ"}
        return [
            {
                "date": "2026-08-01T00:00:00.000Z",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 104,
                "volume": 123,
                "splitFactor": 2.0,
                "divCash": 0.5,
            }
        ]

    store = Store()

    with pytest.raises(ProviderDownloadError, match="data could not be persisted"):
        downloads_module.download_provider(
            store,
            TiingoDownloadSpec(symbols=("AAPL",)),
            credentials=ProviderCredentials(tiingo_api_token="token"),
            fetch_json=fetch_json,
        )

    assert store.ingest_calls == 2
    assert store.discarded == ["saved-first"]
