from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import market_research_lab.downloads as downloads_module
from market_research_lab.api import create_app
from market_research_lab.market_data import MarketDataStore
from market_research_lab.providers import (
    ProviderCredentials,
    ProviderDownload,
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
    response = TestClient(app).post(
        "/api/datasets/download",
        json={
            "provider": "tiingo",
            "symbols": ["AAPL"],
            "start_date": "2023-06-01",
            "end_date": "2023-06-30",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["dataset_version_id"]
    assert body["dataset_version_ids"]
    assert "private-token" not in json.dumps(body)
    securities = MarketDataStore(tmp_path).list_securities()
    assert securities[0].security_id == "AAPL"
    assert securities[0].symbol == "AAPL"


def test_provider_failure_does_not_create_a_dataset_version(tmp_path):
    def fetch_json(_url, _headers):
        raise RuntimeError("upstream unavailable")

    (tmp_path / ".env.local").write_text("TIINGO_API_TOKEN=private-token\n", encoding="utf-8")
    app = create_app(workspace_root=tmp_path, provider_fetch_json=fetch_json)
    client = TestClient(app)
    response = client.post(
        "/api/datasets/download", json={"provider": "tiingo", "symbols": ["AAPL"]}
    )

    assert response.status_code == 502
    assert response.json()["code"] == "provider_error"
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
    client = TestClient(create_app(workspace_root=tmp_path, provider_fetch_json=fetch_json))

    imported = client.post(
        "/api/datasets/download",
        json={"provider": "sec_edgar", "ciks": ["1"]},
    )

    assert imported.status_code == 201
    version_id = imported.json()["dataset_version_id"]
    coverage = client.get(f"/api/datasets/{version_id}/coverage")
    assert coverage.json()["has_temporal_provenance"] is False
    assert coverage.json()["coverage_start"] == "2022-12-31"
    historical = client.get(
        f"/api/datasets/{version_id}/fundamentals",
        params={"as_of": "2023-05-01T00:00:00Z"},
    )
    assert historical.status_code == 400
    assert historical.json()["code"] == "point_in_time_data_required"

def test_download_removes_saved_versions_when_a_later_group_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    downloaded = ProviderDownload(
        daily_bars=[{"security_id": "AAPL"}],
        corporate_actions=[{"security_id": "AAPL"}],
    )
    monkeypatch.setattr(
        downloads_module,
        "download_tiingo",
        lambda *_args, **_kwargs: downloaded,
    )
    store = Store()

    with pytest.raises(ProviderDownloadError, match="data could not be persisted"):
        downloads_module.download_provider(
            store,
            TiingoDownloadSpec(symbols=("AAPL",)),
            credentials=ProviderCredentials(tiingo_api_token="token"),
        )

    assert store.ingest_calls == 2
    assert store.discarded == ["saved-first"]
