from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from market_research_lab.json_types import JsonValue
from market_research_lab.providers import (
    MassiveCredentials,
    ProviderDownloadError,
    SecEdgarDownloadSpec,
    TiingoDownloadSpec,
    download_sec_edgar,
    download_tiingo,
)


def test_tiingo_payload_maps_prices_and_corporate_actions():
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
        TiingoDownloadSpec(
            symbols=("AAPL",),
            start_date=date(2023, 6, 1),
            end_date=date(2023, 6, 30),
        ),
        token="secret-token",
        retrieval_time="2023-07-01T00:00:00Z",
        fetch_json=fetch_json,
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


def test_tiingo_uses_injected_fetcher():
    calls: list[str] = []

    def fetch_json(url: str, _headers: dict[str, str]) -> JsonValue:
        calls.append(url)
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

    result = download_tiingo(
        TiingoDownloadSpec(symbols=("AAPL",)),
        token="secret-token",
        retrieval_time="2023-07-01T00:00:00Z",
        fetch_json=fetch_json,
    )

    assert len(calls) == 2
    assert "/prices" in calls[1]
    assert result.daily_bars[0]["close"] == 104


def test_sec_companyfacts_maps_facts_to_filing_eligibility():

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
        SecEdgarDownloadSpec(ciks=("0000320193",)),
        user_agent="Market Research Lab test@example.com",
        retrieval_time="2023-05-01T00:00:00Z",
        fetch_json=fetch_json,
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


def test_provider_requires_local_credentials():
    with pytest.raises(ProviderDownloadError, match="TIINGO_API_TOKEN"):
        download_tiingo(
            TiingoDownloadSpec(symbols=("AAPL",)),
            token=None,
            retrieval_time="2023-07-01T00:00:00Z",
            fetch_json=lambda _url, _headers: [],
        )


def test_sec_missing_acceptance_time_is_preserved_as_ineligible():
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
        SecEdgarDownloadSpec(ciks=("0000000001",)),
        user_agent="Market Research Lab test@example.com",
        retrieval_time="2023-05-01T00:00:00Z",
        fetch_json=fetch_json,
    )

    fact = result.fundamental_facts[0]
    assert fact["available_at"] is None
    assert fact["eligibility_provenance"] == "missing_acceptance_time"
    assert result.warnings


def test_sec_defaulted_observation_fields_are_flagged_and_warned():
    def fetch_json(url: str, _headers: dict[str, str]) -> JsonValue:
        if "/submissions/" in url:
            return {
                "name": "Example Corp",
                "tickers": ["EXMP"],
                "exchanges": ["NASDAQ"],
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000000000-23-000001"],
                        "acceptanceDateTime": ["2023-04-20T13:30:00.000Z"],
                    }
                },
            }
        # The observation omits start, frame, and accn: those fields fall back
        # to their model defaults and must be flagged for downstream handling.
        return {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [
                                {
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
        SecEdgarDownloadSpec(ciks=("0000000001",)),
        user_agent="Market Research Lab test@example.com",
        retrieval_time="2023-05-01T00:00:00Z",
        fetch_json=fetch_json,
    )

    fact = result.fundamental_facts[0]
    assert fact["incomplete_fields"] == ["accn", "frame", "start"]
    assert any("defaulted" in warning for warning in result.warnings)


def test_sec_complete_observation_has_no_defaulted_fields():
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
                                    "start": "2022-01-01",
                                    "end": "2022-12-31",
                                    "val": 100,
                                    "frame": "FY2023",
                                }
                            ]
                        }
                    }
                }
            }
        }

    result = download_sec_edgar(
        SecEdgarDownloadSpec(ciks=("0000000001",)),
        user_agent="Market Research Lab test@example.com",
        retrieval_time="2023-05-01T00:00:00Z",
        fetch_json=fetch_json,
    )

    fact = result.fundamental_facts[0]
    assert fact["incomplete_fields"] is None
    assert not any("defaulted" in warning for warning in result.warnings)


def test_fetch_massive_grouped_daily_preserves_symbol_order():
    """Spec P2: grouped daily must strictly preserve Security List order."""
    from market_research_lab.providers import fetch_massive_grouped_daily

    def mock_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        # Return results in arbitrary provider order (XLK first, then SPY, then QQQ)
        return {
            "status": "OK",
            "resultsCount": 3,
            "results": [
                {
                    "T": "XLK",
                    "v": 1000,
                    "o": 150.0,
                    "c": 152.0,
                    "h": 153.0,
                    "l": 149.0,
                    "t": 1704200000000,
                },
                {
                    "T": "SPY",
                    "v": 5000,
                    "o": 470.0,
                    "c": 472.0,
                    "h": 473.0,
                    "l": 469.0,
                    "t": 1704200000000,
                },
                {
                    "T": "QQQ",
                    "v": 3000,
                    "o": 380.0,
                    "c": 382.0,
                    "h": 383.0,
                    "l": 379.0,
                    "t": 1704200000000,
                },
            ],
        }

    # Request in specific security list order: SPY, QQQ, XLK
    requested_order = ["SPY", "QQQ", "XLK"]
    result = fetch_massive_grouped_daily(
        date(2024, 1, 2),
        selected_symbols=requested_order,
        credentials=MassiveCredentials(api_key="test-key"),
        retrieval_time="2024-01-02T22:00:00Z",
        fetch_json=mock_fetch,
    )

    result_symbols = [s.symbol for s in result.securities]
    assert result_symbols == ["SPY", "QQQ", "XLK"]

    bar_symbols = [b["security_id"] for b in result.daily_bars]
    assert bar_symbols == ["SPY", "QQQ", "XLK"]


def test_download_massive_options_fails_on_malformed_aggs():
    """Spec P1: corrupted option contract responses must fail the download."""
    from market_research_lab.providers import MassiveDownloadSpec, download_massive

    def mock_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        if "reference/options/contracts" in url:
            return {
                "status": "OK",
                "results": [
                    {
                        "ticker": "O:SPY240119P00450000",
                        "underlying_ticker": "SPY",
                        "expiration_date": "2024-01-19",
                        "strike_price": 450.0,
                        "contract_type": "put",
                        "shares_per_contract": 100,
                        "exercise_style": "american",
                    }
                ],
            }
        elif "aggs/ticker/SPY/range/1/minute" in url:
            return {
                "status": "OK",
                "results": [
                    {
                        "t": 1704200000000,
                        "o": 470.0,
                        "h": 471.0,
                        "l": 469.0,
                        "c": 470.5,
                        "v": 100,
                    }
                ],
            }
        elif "O:SPY240119P00450000" in url:
            # Malformed aggregates payload (missing mandatory 't' timestamp)
            return {
                "status": "OK",
                "results": [{"invalid_key": 123}],
            }
        return {"status": "OK", "results": []}

    with pytest.raises(ProviderDownloadError, match="invalid option trade minute bars"):
        download_massive(
            MassiveDownloadSpec(
                symbol="SPY",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 3),
                data_type="options",
            ),
            credentials=MassiveCredentials(api_key="test-key"),
            retrieval_time="2024-01-03T22:00:00Z",
            fetch_json=mock_fetch,
        )

