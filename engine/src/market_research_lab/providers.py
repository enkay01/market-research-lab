"""Small, validated adapters for the initial public Market Dataset sources."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Literal, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
class TiingoDownloadSpec:
    symbols: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None
    provider: Literal["tiingo"] = field(init=False, default="tiingo")


@dataclass(frozen=True)
class SecEdgarDownloadSpec:
    ciks: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None
    provider: Literal["sec_edgar"] = field(init=False, default="sec_edgar")


@dataclass(frozen=True)
class ProviderCredentials:
    tiingo_api_token: str | None = None
    sec_edgar_user_agent: str | None = None


@dataclass
class ProviderDownload:
    securities: list[Security] = field(default_factory=list)
    daily_bars: list[dict[str, JsonValue]] = field(default_factory=list)
    corporate_actions: list[dict[str, JsonValue]] = field(default_factory=list)
    fundamental_facts: list[dict[str, JsonValue]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
