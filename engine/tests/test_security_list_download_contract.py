"""Public contracts for Security List downloads.

These tests are intentionally red. They specify the next implementation without
reaching into provider adapters or storage internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING, Literal

from fastapi.testclient import TestClient

from market_research_lab.api import create_app
from market_research_lab.json_types import JsonValue

if TYPE_CHECKING:
    from pathlib import Path


ETF_SECURITY_LIST_ID = "us-sector-index-etfs"
ETF_SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLF",
    "XLK",
    "XLE",
    "XLV",
    "XLI",
    "XLP",
    "XLY",
    "XLU",
    "XLC",
    "XLRE",
)
SECURITY_LIST_MINIMUMS = {
    ETF_SECURITY_LIST_ID: 14,
    "dow-30": 30,
    "sp-100": 100,
    "nasdaq-100": 100,
    "sp-500": 500,
}
ProviderName = Literal["tiingo", "massive", "sec_edgar"]


def _security_lists_module() -> ModuleType:
    return import_module("market_research_lab.security_lists")


def _write_provider_credentials(workspace_root: Path) -> None:
    (workspace_root / ".env.local").write_text(
        "TIINGO_API_TOKEN=tiingo-token\n"
        "MASSIVE_API_KEY=massive-token\n"
        "SEC_EDGAR_USER_AGENT=Market Research Lab test@example.com\n"
        "MASSIVE_REQUEST_INTERVAL_SECONDS=12\n",
        encoding="utf-8",
    )


def _provider_name(url: str) -> ProviderName:
    if "tiingo.com" in url:
        return "tiingo"
    if "polygon.io" in url:
        return "massive"
    return "sec_edgar"


def _tiingo_response(url: str) -> JsonValue:
    if "/prices" in url:
        return [
            {
                "date": "2024-01-02T00:00:00.000Z",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1000,
            }
        ]
    symbol = url.split("/tiingo/daily/", maxsplit=1)[1].split("/", maxsplit=1)[0]
    return {"ticker": symbol, "name": f"{symbol} Fund", "exchangeCode": "NYSE"}


def _sec_edgar_response(url: str) -> JsonValue:
    if "/submissions/" in url:
        return {
            "name": "Example issuer",
            "tickers": ["EXMP"],
            "exchanges": ["NYSE"],
            "filings": {
                "recent": {
                    "accessionNumber": ["0000000000-24-000001"],
                    "acceptanceDateTime": ["2024-01-02T21:00:00.000Z"],
                }
            },
        }
    return {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000000000-24-000001",
                                "form": "10-K",
                                "filed": "2024-01-02",
                                "fy": 2023,
                                "fp": "FY",
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 100,
                                "frame": "CY2023",
                            }
                        ]
                    }
                }
            }
        }
    }


def _massive_response() -> JsonValue:
    return {
        "results": [
            {"t": 1704205800000, "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000}
        ]
    }


@dataclass
class ProviderStub:
    failing_provider: ProviderName | None = None
    calls: list[str] = field(default_factory=list)

    def __call__(self, url: str, _headers: dict[str, str]) -> JsonValue:
        provider = _provider_name(url)
        self.calls.append(url)
        if provider == self.failing_provider:
            raise RuntimeError(f"{provider} is unavailable")
        if provider == "tiingo":
            return _tiingo_response(url)
        if provider == "massive":
            return _massive_response()
        return _sec_edgar_response(url)


def _composite_request(
    security_list_id: str = "dow-30",
    downloads: list[dict[str, JsonValue]] | None = None,
) -> dict[str, JsonValue]:
    return {
        "security_list_id": security_list_id,
        "start_date": "2024-01-02",
        "end_date": "2024-01-03",
        "downloads": downloads
        or [
            {"provider": "tiingo", "data_types": ["daily_bars"]},
            {"provider": "massive", "data_types": ["minute_bars"]},
            {"provider": "sec_edgar", "data_types": ["fundamentals"]},
        ],
    }


def test_security_list_catalogue_returns_named_dated_lists(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.get("/api/security-lists")

    assert response.status_code == 200
    lists = {item["id"]: item for item in response.json()}
    assert set(lists) == set(SECURITY_LIST_MINIMUMS)
    for list_id, minimum_members in SECURITY_LIST_MINIMUMS.items():
        assert lists[list_id]["member_count"] >= minimum_members
        assert lists[list_id]["as_of_date"]
        assert lists[list_id]["source_url"].startswith("https://")


def _wait_for_download(
    client: TestClient,
    download_id: str,
    timeout_seconds: float = 5.0,
) -> dict[str, JsonValue]:
    import time
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        res = client.get(f"/api/downloads/{download_id}")
        assert res.status_code == 200
        snap = res.json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        time.sleep(0.01)
    raise TimeoutError(f"Download {download_id} did not finish within {timeout_seconds}s")


def test_sector_and_index_etf_list_resolves_to_the_agreed_symbols():
    security_lists = _security_lists_module()

    security_list = security_lists.get_security_list(ETF_SECURITY_LIST_ID)

    assert security_list.id == ETF_SECURITY_LIST_ID
    assert tuple(member.symbol for member in security_list.members) == ETF_SYMBOLS


def test_each_security_list_has_unique_members_and_a_dated_source():
    security_lists = _security_lists_module()

    for summary in security_lists.list_security_lists():
        security_list = security_lists.get_security_list(summary.id)
        symbols = [member.symbol for member in security_list.members]

        assert len(symbols) >= SECURITY_LIST_MINIMUMS[security_list.id]
        assert len(symbols) == len(set(symbols))
        assert security_list.as_of_date
        assert security_list.source_url.startswith("https://")


def test_unknown_security_list_results_in_failed_download(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    response = client.post(
        "/api/downloads",
        json=_composite_request(security_list_id="missing-list"),
    )

    assert response.status_code == 202
    download_id = response.json()["download_id"]
    snap = _wait_for_download(client, download_id)
    assert snap["state"] == "failed"
    assert "missing-list" in str(snap["error_message"])


def test_multi_provider_download_creates_one_composite_dataset_version(tmp_path):
    _write_provider_credentials(tmp_path)
    provider = ProviderStub()
    app = create_app(workspace_root=tmp_path, provider_fetch_json=provider)
    app.state.provider_wait = lambda _: None
    client = TestClient(app)

    response = client.post("/api/downloads", json=_composite_request())

    assert response.status_code == 202
    download_id = response.json()["download_id"]
    assert response.json()["status_url"] == f"/api/downloads/{download_id}"

    snap = _wait_for_download(client, download_id)
    assert snap["state"] == "succeeded"
    dataset_version_id = snap["dataset_version_id"]
    assert dataset_version_id is not None
    assert snap["security_list_id"] == "dow-30"

    # Test /api/downloads/latest routing
    latest = client.get("/api/downloads/latest")
    assert latest.status_code == 200
    assert latest.json()["download_id"] == download_id
    assert latest.json()["dataset_version_id"] == dataset_version_id

    catalogue = client.get("/api/datasets")
    assert catalogue.status_code == 200
    assert [item["id"] for item in catalogue.json()] == [dataset_version_id]

    coverage = client.get(f"/api/datasets/{dataset_version_id}/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["security_list_id"] == "dow-30"
    assert {part["dataset_type"] for part in coverage.json()["parts"]} == {
        "daily_bars",
        "minute_bars",
        "fundamentals",
    }


def test_failed_composite_download_does_not_create_a_dataset_version(tmp_path):
    _write_provider_credentials(tmp_path)
    provider = ProviderStub(failing_provider="sec_edgar")
    app = create_app(workspace_root=tmp_path, provider_fetch_json=provider)
    app.state.provider_wait = lambda _: None
    client = TestClient(app)

    response = client.post("/api/downloads", json=_composite_request())

    assert response.status_code == 202
    download_id = response.json()["download_id"]
    snap = _wait_for_download(client, download_id)
    assert snap["state"] == "failed"
    assert "sec edgar" in str(snap["error_message"]).lower()
    assert client.get("/api/datasets").json() == []


def test_free_massive_download_waits_between_each_security_request(tmp_path):
    _write_provider_credentials(tmp_path)
    provider = ProviderStub()
    app = create_app(workspace_root=tmp_path, provider_fetch_json=provider)
    waits: list[float] = []
    app.state.provider_wait = waits.append
    client = TestClient(app)

    response = client.post(
        "/api/downloads",
        json=_composite_request(
            security_list_id=ETF_SECURITY_LIST_ID,
            downloads=[{"provider": "massive", "data_types": ["minute_bars"]}],
        ),
    )

    assert response.status_code == 202
    download_id = response.json()["download_id"]
    snap = _wait_for_download(client, download_id, timeout_seconds=10.0)
    assert snap["state"] == "succeeded"
    assert len(provider.calls) == len(ETF_SYMBOLS)
    assert len(waits) == len(ETF_SYMBOLS) - 1
    assert all(w >= 11.5 for w in waits)
