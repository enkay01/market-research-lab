from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from market_research_lab.api import create_app
from market_research_lab.downloads import download_provider
from market_research_lab.market_data import MarketDataStore
from market_research_lab.providers import (
    AlpacaCredentials,
    AlpacaDownloadSpec,
    ProviderCredentials,
    ProviderDownloadError,
    download_alpaca,
)

ALPACA_RETRIEVAL_TIME = "2026-08-24T12:00:00Z"


def _alpaca_fetcher(calls: list[tuple[str, dict[str, str]]]):
    def fetch_json(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        parsed = urlparse(url)
        if parsed.path == "/v2/stocks/SPY/bars":
            return {
                "bars": [
                    {
                        "t": "2024-01-02T14:30:00Z",
                        "o": 100,
                        "h": 101,
                        "l": 99,
                        "c": 100.5,
                        "v": 1200,
                    }
                ]
            }
        if parsed.path == "/v2/options/contracts":
            return {
                "option_contracts": [
                    {
                        "id": "contract-id",
                        "symbol": "SPY240119P00400000",
                        "underlying_symbol": "SPY",
                        "expiration_date": "2024-01-19",
                        "strike_price": "400",
                        "type": "put",
                        "style": "american",
                        "size": "100",
                    }
                ]
            }
        if parsed.path == "/v1beta1/options/SPY240119P00400000/trades":
            return {"trades": [{"t": "2024-01-02T14:30:00Z", "p": 2.5, "s": 10}]}
        raise AssertionError(f"Unexpected Alpaca URL: {url}")

    return fetch_json


def test_alpaca_builds_bounded_endpoints_and_normalizes_options_records():
    calls: list[tuple[str, dict[str, str]]] = []
    result = download_alpaca(
        AlpacaDownloadSpec("SPY", date(2024, 1, 2), date(2024, 1, 3)),
        credentials=AlpacaCredentials("key", "secret"),
        retrieval_time=ALPACA_RETRIEVAL_TIME,
        fetch_json=_alpaca_fetcher(calls),
    )

    assert [urlparse(url).path for url, _ in calls] == [
        "/v2/stocks/SPY/bars",
        "/v2/options/contracts",
        "/v1beta1/options/SPY240119P00400000/trades",
    ]
    stock_query = parse_qs(urlparse(calls[0][0]).query)
    assert stock_query == {
        "timeframe": ["1Min"],
        "start": ["2024-01-02"],
        "end": ["2024-01-03"],
        "limit": ["10000"],
        "feed": ["iex"],
        "sort": ["asc"],
    }
    contract_query = parse_qs(urlparse(calls[1][0]).query)
    assert contract_query["underlying_symbols"] == ["SPY"]
    assert contract_query["expiration_date_gte"] == ["2024-01-02"]
    assert contract_query["expiration_date_lte"] == ["2024-01-03"]
    trade_query = parse_qs(urlparse(calls[2][0]).query)
    assert trade_query["start"] == ["2024-01-02"]
    assert trade_query["end"] == ["2024-01-03"]
    assert trade_query["feed"] == ["indicative"]
    assert calls[0][1] == {
        "Accept": "application/json",
        "APCA-API-KEY-ID": "key",
        "APCA-API-SECRET-KEY": "secret",
    }
    assert all("secret" not in url for url, _ in calls)

    assert {row["record_type"] for row in result.options_records} == {
        "stock_bar",
        "contract",
        "trade",
    }
    contract = next(row for row in result.options_records if row["record_type"] == "contract")
    assert contract["contract_id"] == "contract-id"
    assert contract["contract_symbol"] == "SPY240119P00400000"
    assert contract["right"] == "put"
    assert contract["multiplier"] == 100
    trade = next(row for row in result.options_records if row["record_type"] == "trade")
    assert trade["contract_id"] == "contract-id"
    assert trade["price"] == 2.5
    assert trade["available_at"] == ALPACA_RETRIEVAL_TIME


def test_alpaca_download_persists_one_options_dataset_version(tmp_path):
    calls: list[tuple[str, dict[str, str]]] = []
    store = MarketDataStore(tmp_path)

    versions = download_provider(
        store,
        AlpacaDownloadSpec("SPY", date(2024, 1, 2), date(2024, 1, 3)),
        credentials=ProviderCredentials(alpaca=AlpacaCredentials("key", "secret")),
        fetch_json=_alpaca_fetcher(calls),
    )

    assert len(versions) == 1
    coverage = store.coverage(versions[0].id)
    assert coverage.source == "alpaca"
    assert coverage.dataset_type == "options"
    assert coverage.row_count == 3
    assert len(calls) == 3


def test_alpaca_route_reads_credentials_from_local_env(tmp_path):
    (tmp_path / ".env.local").write_text(
        "ALPACA_API_KEY=key\nALPACA_API_SECRET=secret\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, dict[str, str]]] = []
    response = TestClient(
        create_app(workspace_root=tmp_path, provider_fetch_json=_alpaca_fetcher(calls))
    ).post(
        "/api/datasets/download",
        json={
            "provider": "alpaca",
            "symbol": "spy",
            "start_date": "2024-01-02",
            "end_date": "2024-01-03",
        },
    )

    assert response.status_code == 201, response.text
    assert "secret" not in response.text
    assert response.json()["dataset_version_ids"]


def test_alpaca_requires_local_credentials():
    with pytest.raises(
        ProviderDownloadError,
        match="Alpaca credentials are missing: set ALPACA_API_KEY and ALPACA_API_SECRET",
    ):
        download_alpaca(
            AlpacaDownloadSpec("SPY", date(2024, 1, 2), date(2024, 1, 3)),
            credentials=AlpacaCredentials(),
            retrieval_time=ALPACA_RETRIEVAL_TIME,
            fetch_json=lambda _url, _headers: {},
        )
