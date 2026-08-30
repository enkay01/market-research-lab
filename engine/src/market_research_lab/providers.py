"""Small, validated adapters for the initial public Market Dataset sources."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
)

from .json_types import JsonValue
from .market_data import Security


class ProviderDownloadError(ValueError):
    """Raised when a remote provider cannot return a usable response."""


JsonFetcher = Callable[[str, Mapping[str, str]], JsonValue]


class TiingoPriceResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_open: float | None = Field(default=None, alias="adjOpen")
    adjusted_high: float | None = Field(default=None, alias="adjHigh")
    adjusted_low: float | None = Field(default=None, alias="adjLow")
    adjusted_close: float | None = Field(default=None, alias="adjClose")
    dividend_cash: float = Field(default=0, alias="divCash")
    split_factor: float = Field(default=1, alias="splitFactor")


class AlpacaUnderlyingBarResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    timestamp: str = Field(alias="t")
    open: float = Field(alias="o")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    close: float = Field(alias="c")
    volume: float = Field(alias="v")


class AlpacaOptionTradeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    timestamp: str = Field(alias="t")
    price: float = Field(alias="p")
    size: float = Field(alias="s")


class AlpacaOptionContractResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    contract_id: str | None = Field(default=None, alias="id")
    contract_symbol: str = Field(alias="symbol")
    underlying_symbol: str = Field(alias="underlying_symbol")
    expiration: str = Field(alias="expiration_date")
    strike: float = Field(alias="strike_price")
    right: str = Field(alias="type")
    exercise_style: str = Field(default="american", alias="style")
    multiplier: float = Field(default=100.0, alias="size")


class AlpacaUnderlyingBarsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bars: list[AlpacaUnderlyingBarResponse] = Field(default_factory=list)
    next_page_token: str | None = None


class AlpacaOptionTradesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    trades: list[AlpacaOptionTradeResponse] | dict[str, list[AlpacaOptionTradeResponse]] = Field(
        default_factory=list
    )
    next_page_token: str | None = None


class AlpacaOptionContractsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    option_contracts: list[AlpacaOptionContractResponse] = Field(default_factory=list)
    next_page_token: str | None = None


class TiingoMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ticker: str
    name: str
    exchange_code: str | None = Field(default=None, alias="exchangeCode")


class SecObservation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    accn: str = ""
    fy: int = 0
    fp: str = ""
    form: str
    filed: str
    start: str = ""
    end: str = ""
    val: float | str
    frame: str = ""


def _sec_observation_defaulted_fields(obs: SecObservation) -> frozenset[str]:
    """Names of SecObservation fields still holding their model defaults.

    SEC EDGAR Company Facts payloads are sparse: when a key is absent, the
    ``extra="ignore"`` config silently fills the model default (e.g. ``fy=0``,
    ``fp=""``) instead of failing. The row then flows downstream looking like
    data even though the source said nothing. This reports exactly which fields
    were defaulted so the caller can mark the observation for downstream
    handling (or reject it).

    Required fields (``form``, ``filed``, ``val``) are not reported: validation
    would have failed if they were absent, and a zero ``val`` is legitimate
    source data, not a default.
    """
    defaulted: set[str] = set()
    if not obs.accn:
        defaulted.add("accn")
    if obs.fy == 0:
        defaulted.add("fy")
    if not obs.fp:
        defaulted.add("fp")
    if not obs.start:
        defaulted.add("start")
    if not obs.end:
        defaulted.add("end")
    if not obs.frame:
        defaulted.add("frame")
    return frozenset(defaulted)


class SecFactDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    units: dict[str, list[SecObservation]]


class SecCompanyFacts(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    entity_name: str | None = Field(default=None, alias="entityName")
    facts: dict[str, dict[str, SecFactDefinition]]


class SecRecentFilings(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    accession_numbers: list[str | None] = Field(default_factory=list, alias="accessionNumber")
    acceptance_times: list[str | None] = Field(default_factory=list, alias="acceptanceDateTime")


class SecSubmissionFile(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    filing_from: str | None = Field(default=None, alias="filingFrom")
    filing_to: str | None = Field(default=None, alias="filingTo")


class SecFilings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recent: SecRecentFilings = Field(default_factory=SecRecentFilings)
    files: list[SecSubmissionFile] = Field(default_factory=list)


class SecSubmissions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    tickers: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)
    filings: SecFilings = Field(default_factory=SecFilings)


@dataclass(frozen=True)
class AlpacaCredentials:
    """Alpaca credentials held by the local process, never by the API response."""

    api_key: str | None = None
    api_secret: str | None = None


@dataclass(frozen=True)
class MassiveCredentials:
    """Massive / Polygon credentials held by the local process."""

    api_key: str | None = None


@dataclass(frozen=True)
class TiingoDownloadSpec:
    symbols: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class SecEdgarDownloadSpec:
    ciks: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class AlpacaDownloadSpec:
    symbol: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class MassiveDownloadSpec:
    symbol: str
    start_date: date
    end_date: date
    data_type: Literal["stocks_daily", "stocks_minute", "options"] = "stocks_daily"


@dataclass(frozen=True)
class ProviderCredentials:
    tiingo_api_token: str = ""
    sec_edgar_user_agent: str = ""
    alpaca: AlpacaCredentials = field(default_factory=AlpacaCredentials)
    massive: MassiveCredentials = field(default_factory=MassiveCredentials)


class MassiveAggResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: int = Field(alias="t")
    open: float = Field(alias="o")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    close: float = Field(alias="c")
    volume: float = Field(alias="v")


class MassiveAggsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[MassiveAggResponse] = Field(default_factory=list)
    next_url: str | None = None


class MassiveOptionContractResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    underlying_ticker: str
    strike_price: float
    expiration_date: str
    contract_type: str
    shares_per_contract: float = 100.0
    exercise_style: str = "american"


class MassiveOptionContractsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[MassiveOptionContractResponse] = Field(default_factory=list)
    next_url: str | None = None


@dataclass
class ProviderDownload:
    securities: list[Security] = field(default_factory=list)
    daily_bars: list[dict[str, JsonValue]] = field(default_factory=list)
    corporate_actions: list[dict[str, JsonValue]] = field(default_factory=list)
    fundamental_facts: list[dict[str, JsonValue]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    options_records: list[dict[str, JsonValue]] = field(default_factory=list)


def _fetch_json(url: str, headers: Mapping[str, str]) -> JsonValue:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ProviderDownloadError(f"Provider request failed with HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise ProviderDownloadError(f"Provider request failed ({type(error).__name__}).") from error


def _call(
    fetch_json: JsonFetcher, url: str, headers: Mapping[str, str], provider: str
) -> JsonValue:
    try:
        return fetch_json(url, headers)
    except ProviderDownloadError as error:
        raise ProviderDownloadError(f"{provider} request failed.") from error
    except Exception as error:
        raise ProviderDownloadError(
            f"{provider} request failed ({type(error).__name__})."
        ) from error


def _alpaca_url(path: str, query: Mapping[str, str]) -> str:
    return f"https://{path}?{urlencode(query)}"


def _alpaca_pages(
    fetch: JsonFetcher,
    path: str,
    query: Mapping[str, str],
    headers: Mapping[str, str],
) -> list[JsonValue]:
    """Fetch all pages while keeping the request inside the supplied bounds."""
    pages: list[JsonValue] = []
    page_token: str | None = None
    while True:
        page_query = dict(query)
        if page_token:
            page_query["page_token"] = page_token
        payload = _call(fetch, _alpaca_url(path, page_query), headers, "Alpaca")
        pages.append(payload)
        next_page_token = payload.get("next_page_token") if isinstance(payload, dict) else None
        if not isinstance(next_page_token, str) or not next_page_token:
            return pages
        if next_page_token == page_token:
            raise ProviderDownloadError("Alpaca returned a repeated pagination token.")
        page_token = next_page_token


def _alpaca_available_at(event_time: str, *, daily: bool = False) -> str:
    """Use the completed bar as the earliest usable historical boundary."""
    parsed = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (parsed + timedelta(days=1 if daily else 0, minutes=0 if daily else 1)).isoformat()


def download_alpaca(
    request: AlpacaDownloadSpec,
    *,
    credentials: AlpacaCredentials,
    retrieval_time: str,
    fetch_json: JsonFetcher | None = None,
) -> ProviderDownload:
    """Download one bounded Alpaca options market-data snapshot.

    The contract endpoint is on Alpaca's Trading API. Each returned option
    contract is then used with the documented options trades endpoint.
    """
    fetch = fetch_json or _fetch_json
    local_credentials = credentials
    if not local_credentials.api_key or not local_credentials.api_secret:
        raise ProviderDownloadError(
            "Alpaca credentials are missing: set ALPACA_API_KEY and ALPACA_API_SECRET."
        )

    symbol = request.symbol.strip().upper()
    if not symbol:
        raise ProviderDownloadError("Alpaca requires a non-empty underlying symbol.")
    if request.start_date > request.end_date:
        raise ProviderDownloadError("Alpaca start_date must be on or before end_date.")

    headers = {
        "Accept": "application/json",
        "APCA-API-KEY-ID": local_credentials.api_key,
        "APCA-API-SECRET-KEY": local_credentials.api_secret,
    }
    start = request.start_date.isoformat()
    end = request.end_date.isoformat()
    contract_available_at = f"{start}T00:00:00+00:00"
    result = ProviderDownload(
        securities=[Security(security_id=symbol, symbol=symbol, name=symbol, currency="USD")]
    )

    underlying_query = {
        "timeframe": "1Min",
        "start": start,
        "end": end,
        "limit": "10000",
        "feed": "iex",
        "sort": "asc",
    }
    for payload in _alpaca_pages(
        fetch,
        "data.alpaca.markets/v2/stocks/" + quote(symbol, safe="") + "/bars",
        underlying_query,
        headers,
    ):
        try:
            bars = AlpacaUnderlyingBarsResponse.model_validate(payload).bars
        except ValidationError as error:
            raise ProviderDownloadError("Alpaca returned invalid stock bars.") from error
        for bar in bars:
            result.options_records.append(
                {
                    "record_type": "underlying_bar",
                    "security_id": symbol,
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "available_at": _alpaca_available_at(bar.timestamp),
                    "eligibility_provenance": "completed_minute",
                    "source": "alpaca",
                    "retrieval_time": retrieval_time,
                }
            )

    daily_query = dict(underlying_query)
    daily_query["timeframe"] = "1Day"
    for payload in _alpaca_pages(
        fetch,
        "data.alpaca.markets/v2/stocks/" + quote(symbol, safe="") + "/bars",
        daily_query,
        headers,
    ):
        try:
            bars = AlpacaUnderlyingBarsResponse.model_validate(payload).bars
        except ValidationError as error:
            raise ProviderDownloadError("Alpaca returned invalid daily bars.") from error
        for bar in bars:
            result.options_records.append(
                {
                    "record_type": "daily_bar",
                    "security_id": symbol,
                    "date": bar.timestamp[:10],
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "available_at": _alpaca_available_at(bar.timestamp, daily=True),
                    "eligibility_provenance": "completed_day",
                    "source": "alpaca",
                    "retrieval_time": retrieval_time,
                }
            )

    contract_query = {
        "underlying_symbols": symbol,
        "expiration_date_gte": start,
        "expiration_date_lte": (request.end_date + timedelta(days=45)).isoformat(),
        "limit": "1000",
    }
    contracts: list[AlpacaOptionContractResponse] = []
    for payload in _alpaca_pages(
        fetch, "api.alpaca.markets/v2/options/contracts", contract_query, headers
    ):
        try:
            contracts.extend(AlpacaOptionContractsResponse.model_validate(payload).option_contracts)
        except ValidationError as error:
            raise ProviderDownloadError(
                "Alpaca returned invalid option contract metadata."
            ) from error

    for row_number, contract in enumerate(contracts, start=1):
        right = contract.right.lower()
        if right not in {"put", "call"}:
            result.warnings.append(
                f"Alpaca option contract row {row_number} has an unsupported type; skipped."
            )
            continue
        contract_id = contract.contract_id or contract.contract_symbol
        result.options_records.append(
            {
                "record_type": "contract",
                "contract_id": contract_id,
                "contract_symbol": contract.contract_symbol,
                "security_id": contract.underlying_symbol.upper(),
                "expiration": contract.expiration,
                "strike": contract.strike,
                "right": right,
                "multiplier": contract.multiplier,
                "exercise_style": contract.exercise_style.lower(),
                "settlement_type": "physical",
                "available_at": contract_available_at,
                "eligibility_provenance": "contract_snapshot",
                "source": "alpaca",
                "retrieval_time": retrieval_time,
            }
        )

        trade_query = {
            "start": start,
            "end": end,
            "limit": "10000",
            "feed": "indicative",
            "sort": "asc",
        }
        for payload in _alpaca_pages(
            fetch,
            "data.alpaca.markets/v1beta1/options/"
            + quote(contract.contract_symbol, safe="")
            + "/trades",
            trade_query,
            headers,
        ):
            try:
                trade_payload = AlpacaOptionTradesResponse.model_validate(payload).trades
            except ValidationError as error:
                raise ProviderDownloadError(
                    f"Alpaca returned invalid option trades for {contract.contract_symbol}."
                ) from error
            trades = (
                list(trade_payload.values()) if isinstance(trade_payload, dict) else [trade_payload]
            )
            for trade_page in trades:
                for trade in trade_page:
                    result.options_records.append(
                        {
                            "record_type": "trade",
                            "contract_id": contract_id,
                            "timestamp": trade.timestamp,
                            "price": trade.price,
                            "size": trade.size,
                            "available_at": _alpaca_available_at(trade.timestamp),
                            "eligibility_provenance": "completed_minute",
                            "source": "alpaca",
                            "retrieval_time": retrieval_time,
                        }
                    )

    if not any(row.get("record_type") == "contract" for row in result.options_records):
        raise ProviderDownloadError("Alpaca returned no valid option contract metadata.")
    return result


def _tiingo_available_at(raw_date: str, retrieval_time: str) -> str:
    if not raw_date.strip():
        raise ProviderDownloadError("Tiingo returned a price without a date.")
    try:
        datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProviderDownloadError("Tiingo returned an invalid price date.") from error
    # Tiingo returns a session date, not a publication timestamp. Retrieval
    # time is the conservative eligibility boundary for this snapshot.
    return retrieval_time


def download_tiingo(
    request: TiingoDownloadSpec,
    *,
    token: str | None,
    retrieval_time: str,
    fetch_json: JsonFetcher | None = None,
) -> ProviderDownload:
    """Download Tiingo EOD prices and map its action fields to canonical rows."""
    fetch = fetch_json or _fetch_json

    if not token:
        raise ProviderDownloadError("Tiingo credentials are missing: set TIINGO_API_TOKEN.")

    result = ProviderDownload()
    headers = {"Accept": "application/json", "Authorization": f"Token {token}"}
    for symbol in request.symbols:
        metadata_url = f"https://api.tiingo.com/tiingo/daily/{symbol}"
        metadata_payload = _call(fetch, metadata_url, headers, "Tiingo")
        try:
            metadata = TiingoMetadataResponse.model_validate(metadata_payload)
        except ValidationError as error:
            raise ProviderDownloadError(
                f"Tiingo returned invalid metadata for {symbol}."
            ) from error
        result.securities.append(
            Security(
                security_id=symbol,
                symbol=metadata.ticker.upper(),
                name=metadata.name,
                exchange=metadata.exchange_code,
                currency="USD",
            )
        )
        query: dict[str, str] = {}
        if request.start_date:
            query["startDate"] = request.start_date.isoformat()
        if request.end_date:
            query["endDate"] = request.end_date.isoformat()
        query_string = f"?{urlencode(query)}" if query else ""
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices{query_string}"
        payload = _call(
            fetch,
            url,
            headers,
            "Tiingo",
        )
        try:
            price_payload = TypeAdapter(
                list[dict[str, str | int | float | bool | None]]
            ).validate_python(payload)
        except ValidationError as error:
            raise ProviderDownloadError(
                f"Tiingo returned an invalid price payload for {symbol}."
            ) from error

        for row_number, raw_row in enumerate(price_payload, start=1):
            try:
                row = TiingoPriceResponse.model_validate(raw_row)
            except ValidationError:
                result.warnings.append(f"Tiingo {symbol} row {row_number} failed validation.")
                continue

            available_at = _tiingo_available_at(row.date, retrieval_time)
            result.daily_bars.append(
                {
                    "security_id": symbol,
                    "date": row.date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "adjusted_open": row.adjusted_open,
                    "adjusted_high": row.adjusted_high,
                    "adjusted_low": row.adjusted_low,
                    "adjusted_close": row.adjusted_close,
                    "units": "USD",
                    "available_at": available_at,
                    "eligibility_provenance": "retrieval_time_snapshot",
                    "source": "tiingo",
                    "retrieval_time": retrieval_time,
                }
            )

            if row.dividend_cash != 0:
                result.corporate_actions.append(
                    {
                        "security_id": symbol,
                        "type": "dividend",
                        "effective_date": row.date,
                        "value": row.dividend_cash,
                        "units": "USD/share",
                        "available_at": available_at,
                        "eligibility_provenance": "retrieval_time_snapshot",
                        "source": "tiingo",
                        "retrieval_time": retrieval_time,
                    }
                )

            if row.split_factor != 1:
                result.corporate_actions.append(
                    {
                        "security_id": symbol,
                        "type": "split",
                        "effective_date": row.date,
                        "value": row.split_factor,
                        "units": "ratio",
                        "available_at": available_at,
                        "eligibility_provenance": "retrieval_time_snapshot",
                        "source": "tiingo",
                        "retrieval_time": retrieval_time,
                    }
                )

    if not result.daily_bars:
        raise ProviderDownloadError("Tiingo returned no valid daily prices.")
    return result


def _normalise_timestamp(raw_value: str, label: str) -> str:
    if not raw_value.strip():
        raise ProviderDownloadError(f"SEC EDGAR returned a missing {label}.")
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProviderDownloadError(f"SEC EDGAR returned an invalid {label}.") from error
    if parsed.tzinfo is None:
        raise ProviderDownloadError(f"SEC EDGAR returned an invalid {label}.")
    return raw_value.strip()


def _period_date(raw_date: str, label: str) -> str | None:
    if not raw_date:
        return None
    try:
        date.fromisoformat(raw_date[:10])
    except (TypeError, ValueError) as error:
        raise ProviderDownloadError(f"SEC EDGAR returned an invalid {label}.") from error
    return raw_date


def _date_at_midnight(raw_date: str) -> str:
    if not raw_date.strip():
        raise ProviderDownloadError("SEC EDGAR returned a fact without a filing date.")
    try:
        parsed = date.fromisoformat(raw_date[:10])
    except ValueError as error:
        raise ProviderDownloadError("SEC EDGAR returned an invalid filing date.") from error
    return f"{parsed.isoformat()}T00:00:00Z"


def _in_date_range(raw_date: str, start_date: date | None, end_date: date | None) -> bool:
    try:
        current = date.fromisoformat(raw_date[:10])
    except ValueError as error:
        raise ProviderDownloadError("SEC EDGAR returned an invalid filing date.") from error
    return not ((start_date and current < start_date) or (end_date and current > end_date))


def _parse_submissions(payload: JsonValue) -> SecSubmissions:
    try:
        return SecSubmissions.model_validate(payload)
    except ValidationError as error:
        raise ProviderDownloadError("SEC EDGAR returned invalid filing metadata.") from error


def _acceptance_times(submissions: SecSubmissions) -> dict[str, str]:
    recent = submissions.filings.recent
    result: dict[str, str] = {}
    for accession, timestamp in zip(
        recent.accession_numbers, recent.acceptance_times, strict=False
    ):
        if accession and timestamp:
            result[str(accession)] = _normalise_timestamp(timestamp, "acceptance timestamp")
    return result


def _fiscal_period(observation: SecObservation) -> str:
    if observation.frame:
        return observation.frame
    fiscal_period = (observation.fp or "FY").upper()
    if not observation.fy:
        return f"{observation.start or 'unknown'}/{observation.end or 'unknown'}"
    return f"FY{observation.fy}" if fiscal_period == "FY" else f"{observation.fy}{fiscal_period}"


def download_sec_edgar(
    request: SecEdgarDownloadSpec,
    *,
    user_agent: str | None,
    retrieval_time: str,
    fetch_json: JsonFetcher | None = None,
) -> ProviderDownload:
    """Download SEC filing metadata and Company Facts into canonical facts."""
    fetch = fetch_json or _fetch_json

    if not user_agent:
        raise ProviderDownloadError("SEC EDGAR credentials are missing: set SEC_EDGAR_USER_AGENT.")

    result = ProviderDownload()
    defaulted_observation_fields: dict[str, int] = {}
    headers = {"Accept": "application/json", "User-Agent": user_agent}
    for cik in request.ciks:
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        submissions_payload = _call(fetch, submissions_url, headers, "SEC EDGAR")
        submissions = _parse_submissions(submissions_payload)
        acceptance_times = _acceptance_times(submissions)

        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        payload = _call(fetch, facts_url, headers, "SEC EDGAR")
        try:
            company_facts = SecCompanyFacts.model_validate(payload)
        except ValidationError as error:
            raise ProviderDownloadError(
                f"SEC EDGAR returned an invalid Company Facts payload for {cik}."
            ) from error

        security_symbol = submissions.tickers[0].upper() if submissions.tickers else f"CIK{cik}"
        security_id = f"CIK{cik}"
        result.securities.append(
            Security(
                security_id=security_id,
                symbol=security_symbol,
                name=submissions.name or company_facts.entity_name or f"CIK {cik}",
                exchange=submissions.exchanges[0] if submissions.exchanges else None,
                currency="USD",
            )
        )

        for taxonomy, concepts in company_facts.facts.items():
            for concept, definition in concepts.items():
                for unit, observations in definition.units.items():
                    for observation in observations:
                        if not observation.form.startswith(("10-K", "10-Q", "20-F", "40-F")):
                            continue
                        if not _in_date_range(
                            observation.filed, request.start_date, request.end_date
                        ):
                            continue

                        filed_at = _date_at_midnight(observation.filed)
                        accession = observation.accn or ""
                        available_at = acceptance_times.get(accession)
                        provenance = "sec_acceptance_time"
                        if available_at is None:
                            provenance = "missing_acceptance_time"
                            result.warnings.append(
                                f"SEC EDGAR preserved {accession or 'an observation'} without "
                                "an acceptance timestamp; historical use is not eligible."
                            )

                        period_start = _period_date(observation.start, "period start")
                        period_end = _period_date(observation.end, "period end")
                        if period_start and period_end and period_start[:10] > period_end[:10]:
                            raise ProviderDownloadError(
                                "SEC EDGAR returned a period with reversed dates."
                            )

                        defaulted_fields = _sec_observation_defaulted_fields(observation)
                        for defaulted_field in defaulted_fields:
                            defaulted_observation_fields[defaulted_field] = (
                                defaulted_observation_fields.get(defaulted_field, 0) + 1
                            )

                        result.fundamental_facts.append(
                            {
                                "security_id": security_id,
                                "field": f"{taxonomy}:{concept}",
                                "fiscal_period": _fiscal_period(observation),
                                "period_start": period_start,
                                "period_end": period_end,
                                "value": observation.val,
                                "unit": str(unit),
                                "filed_at": filed_at,
                                "available_at": available_at,
                                "eligibility_provenance": provenance,
                                "source": "sec_edgar",
                                "retrieval_time": retrieval_time,
                                "incomplete_fields": sorted(defaulted_fields) or None,
                            }
                        )

    for defaulted_field, count in sorted(defaulted_observation_fields.items()):
        result.warnings.append(
            f"SEC EDGAR preserved {count} observations with defaulted {defaulted_field}."
        )

    if not result.fundamental_facts:
        raise ProviderDownloadError("SEC EDGAR returned no quarterly or annual facts.")
    return result


def _massive_ms_to_iso(ms: int, *, daily: bool = False) -> str:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    if daily:
        return dt.date().isoformat()
    return dt.isoformat()


def _massive_available_at(ms: int, *, daily: bool = False) -> str:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    if daily:
        return (dt + timedelta(days=1)).isoformat()
    return (dt + timedelta(minutes=1)).isoformat()


def download_massive(
    request: MassiveDownloadSpec,
    *,
    credentials: MassiveCredentials,
    retrieval_time: str,
    fetch_json: JsonFetcher | None = None,
) -> ProviderDownload:
    """Download daily or minute bars, or options chains/trades from Massive / Polygon."""
    fetch = fetch_json or _fetch_json
    if not credentials.api_key:
        raise ProviderDownloadError(
            "Massive credentials are missing: set MASSIVE_API_KEY or POLYGON_API_KEY."
        )

    symbol = request.symbol.strip().upper()
    if not symbol:
        raise ProviderDownloadError("Massive requires a non-empty symbol.")
    if request.start_date > request.end_date:
        raise ProviderDownloadError("Massive start_date must be on or before end_date.")

    headers = {"Authorization": f"Bearer {credentials.api_key}", "Accept": "application/json"}
    start_str = request.start_date.isoformat()
    end_str = request.end_date.isoformat()
    result = ProviderDownload(
        securities=[Security(security_id=symbol, symbol=symbol, name=symbol, currency="USD")]
    )

    if request.data_type in ("stocks_daily", "stocks_minute"):
        timespan = "day" if request.data_type == "stocks_daily" else "minute"
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{quote(symbol, safe='')}/range/1/{timespan}/"
            f"{start_str}/{end_str}?adjusted=true&sort=asc&limit=50000"
        )
        payload = _call(fetch, url, headers, "Massive")
        try:
            aggs = MassiveAggsResponse.model_validate(payload).results
        except ValidationError as error:
            raise ProviderDownloadError(
                f"Massive returned invalid aggregates for {symbol}."
            ) from error

        if not aggs:
            raise ProviderDownloadError(f"Massive returned no data for {symbol}.")

        for agg in aggs:
            if request.data_type == "stocks_daily":
                session_date = _massive_ms_to_iso(agg.timestamp, daily=True)
                available_at = _massive_available_at(agg.timestamp, daily=True)
                result.daily_bars.append(
                    {
                        "security_id": symbol,
                        "date": session_date,
                        "open": agg.open,
                        "high": agg.high,
                        "low": agg.low,
                        "close": agg.close,
                        "volume": agg.volume,
                        "adjusted_open": agg.open,
                        "adjusted_high": agg.high,
                        "adjusted_low": agg.low,
                        "adjusted_close": agg.close,
                        "units": "USD",
                        "available_at": available_at,
                        "eligibility_provenance": "completed_day",
                        "source": "massive",
                        "retrieval_time": retrieval_time,
                    }
                )
            else:
                ts_iso = _massive_ms_to_iso(agg.timestamp, daily=False)
                available_at = _massive_available_at(agg.timestamp, daily=False)
                result.options_records.append(
                    {
                        "record_type": "underlying_bar",
                        "security_id": symbol,
                        "timestamp": ts_iso,
                        "open": agg.open,
                        "high": agg.high,
                        "low": agg.low,
                        "close": agg.close,
                        "volume": agg.volume,
                        "available_at": available_at,
                        "eligibility_provenance": "completed_minute",
                        "source": "massive",
                        "retrieval_time": retrieval_time,
                    }
                )
    elif request.data_type == "options":
        # 1. Underlying minute bars
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{quote(symbol, safe='')}/range/1/minute/"
            f"{start_str}/{end_str}?adjusted=true&sort=asc&limit=50000"
        )
        aggs: list[MassiveAggResponse] = []
        with contextlib.suppress(Exception):
            payload = _call(fetch, url, headers, "Massive")
            aggs = MassiveAggsResponse.model_validate(payload).results

        for agg in aggs:
            ts_iso = _massive_ms_to_iso(agg.timestamp, daily=False)
            available_at = _massive_available_at(agg.timestamp, daily=False)
            result.options_records.append(
                {
                    "record_type": "underlying_bar",
                    "security_id": symbol,
                    "timestamp": ts_iso,
                    "open": agg.open,
                    "high": agg.high,
                    "low": agg.low,
                    "close": agg.close,
                    "volume": agg.volume,
                    "available_at": available_at,
                    "eligibility_provenance": "completed_minute",
                    "source": "massive",
                    "retrieval_time": retrieval_time,
                }
            )
            result.options_records.append(
                {
                    "record_type": "daily_bar",
                    "security_id": symbol,
                    "date": ts_iso[:10],
                    "open": agg.open,
                    "high": agg.high,
                    "low": agg.low,
                    "close": agg.close,
                    "volume": agg.volume,
                    "available_at": _massive_available_at(agg.timestamp, daily=True),
                    "eligibility_provenance": "completed_day",
                    "source": "massive",
                    "retrieval_time": retrieval_time,
                }
            )

        # 2. Put contracts
        contract_url = (
            f"https://api.polygon.io/v3/reference/options/contracts?"
            f"underlying_ticker={quote(symbol, safe='')}&contract_type=put&"
            f"expiration_date.gte={start_str}&"
            f"expiration_date.lte={(request.end_date + timedelta(days=45)).isoformat()}&limit=1000"
        )
        payload = _call(fetch, contract_url, headers, "Massive")
        try:
            contracts = MassiveOptionContractsResponse.model_validate(payload).results
        except ValidationError as error:
            raise ProviderDownloadError(
                "Massive returned invalid option contracts."
            ) from error

        contract_available_at = f"{start_str}T00:00:00+00:00"
        for contract in contracts:
            contract_ticker = contract.ticker.replace("O:", "")
            result.options_records.append(
                {
                    "record_type": "contract",
                    "contract_id": contract_ticker,
                    "contract_symbol": contract_ticker,
                    "security_id": symbol,
                    "expiration": contract.expiration_date,
                    "strike": contract.strike_price,
                    "right": contract.contract_type.lower(),
                    "multiplier": contract.shares_per_contract,
                    "exercise_style": contract.exercise_style.lower(),
                    "settlement_type": "physical",
                    "available_at": contract_available_at,
                    "eligibility_provenance": "contract_snapshot",
                    "source": "massive",
                    "retrieval_time": retrieval_time,
                }
            )
            # Minute bars for option contract
            trade_url = (
                f"https://api.polygon.io/v2/aggs/ticker/O:{quote(contract_ticker, safe='')}/range/1/minute/"
                f"{start_str}/{end_str}?sort=asc&limit=50000"
            )
            try:
                opt_payload = _call(fetch, trade_url, headers, "Massive")
                opt_aggs = MassiveAggsResponse.model_validate(opt_payload).results
                for opt_agg in opt_aggs:
                    ts_iso = _massive_ms_to_iso(opt_agg.timestamp, daily=False)
                    result.options_records.append(
                        {
                            "record_type": "trade",
                            "contract_id": contract_ticker,
                            "timestamp": ts_iso,
                            "price": opt_agg.close,
                            "size": opt_agg.volume,
                            "available_at": _massive_available_at(opt_agg.timestamp, daily=False),
                            "eligibility_provenance": "completed_minute",
                            "source": "massive",
                            "retrieval_time": retrieval_time,
                        }
                    )
            except Exception:
                continue

    return result

