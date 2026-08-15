from __future__ import annotations

import pytest

from market_research_lab.json_types import JsonValue
from market_research_lab.providers import (
    ProviderDownloadError,
    SecEdgarDownloadOptions,
    TiingoDownloadOptions,
    download_sec_edgar,
    download_tiingo,
)


def test_tiingo_payload_maps_prices_and_corporate_actions() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fetch_json(url: str, headers: dict[str, str]) -> JsonValue:
        calls.append((url, headers))
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
                "adjOpen": 50,
                "adjHigh": 52.5,
                "adjLow": 49.5,
                "adjClose": 52,
                "divCash": 0.24,
                "splitFactor": 2,
            }
        ]

    result = download_tiingo(
        TiingoDownloadOptions(
            symbols=["aapl"],
            start_date="2023-06-01",
            end_date="2023-06-30",
            retrieval_time="2023-07-01T00:00:00Z",
            token="secret-token",
            fetch_json=fetch_json,
        )
    )

    assert result.securities[0].security_id == "AAPL"
    assert result.securities[0].symbol == "AAPL"
    assert result.daily_bars[0]["security_id"] == "AAPL"
    assert result.daily_bars[0]["close"] == 104
    assert result.daily_bars[0]["adjusted_close"] == 52
    assert result.daily_bars[0]["available_at"] == "2023-07-01T00:00:00Z"
    assert result.daily_bars[0]["eligibility_provenance"] == "retrieval_time_snapshot"
    assert {action["type"] for action in result.corporate_actions} == {"dividend", "split"}
    assert calls[0][1]["Authorization"] == "Token secret-token"
    assert "secret-token" not in calls[0][0]


def test_sec_companyfacts_maps_facts_to_filing_eligibility() -> None:
    def fetch_json(url: str, headers: dict[str, str]) -> JsonValue:
        assert headers["User-Agent"] == "Market Research Lab test@example.com"
        if "/submissions/" in url:
            return {
                "name": "Apple Inc.",
                "tickers": ["AAPL"],
                "exchanges": ["NASDAQ"],
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000320193-23-000001"],
                        "acceptanceDateTime": ["2023-04-20T13:30:00.000Z"],
                    }
                },
            }
        return {
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "units": {
                            "USD": [
                                {
                                    "accn": "0000320193-23-000001",
                                    "fy": 2023,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2023-04-20",
                                    "start": "2023-01-01",
                                    "end": "2023-03-31",
                                    "val": 1000,
                                    "frame": "CY2023Q1",
                                }
                            ]
                        },
                    }
                }
            },
        }

    result = download_sec_edgar(
        SecEdgarDownloadOptions(
            ciks=["320193"],
            retrieval_time="2023-05-01T00:00:00Z",
            user_agent="Market Research Lab test@example.com",
            fetch_json=fetch_json,
        )
    )

    assert result.securities[0].security_id == "CIK0000320193"
    assert result.securities[0].name == "Apple Inc."
    fact = result.fundamental_facts[0]
    assert fact["security_id"] == "CIK0000320193"
    assert fact["field"] == "us-gaap:Revenues"
    assert fact["fiscal_period"] == "CY2023Q1"
    assert fact["unit"] == "USD"
    assert fact["filed_at"] == "2023-04-20T00:00:00Z"
    assert fact["available_at"] == "2023-04-20T13:30:00.000Z"


def test_provider_requires_local_credentials() -> None:
    with pytest.raises(ProviderDownloadError, match="TIINGO_API_TOKEN"):
        download_tiingo(
            TiingoDownloadOptions(
                symbols=["AAPL"],
                start_date=None,
                end_date=None,
                retrieval_time="2023-07-01T00:00:00Z",
                token=None,
                fetch_json=lambda _url, _headers: [],
            )
        )


def test_sec_missing_acceptance_time_is_preserved_as_ineligible() -> None:
    def fetch_json(url: str, _headers: dict[str, str]) -> JsonValue:
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

    result = download_sec_edgar(
        SecEdgarDownloadOptions(
            ciks=["1"],
            retrieval_time="2023-05-01T00:00:00Z",
            user_agent="Market Research Lab test@example.com",
            fetch_json=fetch_json,
        )
    )

    fact = result.fundamental_facts[0]
    assert fact["available_at"] is None
    assert fact["eligibility_provenance"] == "missing_acceptance_time"
    assert result.warnings
