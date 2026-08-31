"""Market data ingestion, storage, and queries."""

from __future__ import annotations

import ast
import contextlib
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import duckdb
import pandas as pd

from .json_types import JsonValue

SECURITY_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class InvalidSecurityIdError(ValueError):
    """Raised when a security_id contains invalid characters or path traversal sequences."""


def validate_security_id(security_id: str) -> str:
    """Validate security_id as a safe, canonical identifier."""
    cleaned = security_id.strip()
    if not cleaned or not SECURITY_ID_REGEX.fullmatch(cleaned):
        raise InvalidSecurityIdError(
            f"Security ID '{security_id}' is invalid. "
            "Allowed: alphanumeric, underscores, hyphens (1-64 chars)."
        )
    return cleaned


class InsufficientTimestampError(ValueError):
    """Raised when market observations lack required point-in-time eligibility timestamps."""


class DatasetVersionNotFoundError(ValueError):
    """Raised when a requested Dataset Version does not exist."""


TEMPORAL_PROVENANCE_ERROR_MESSAGE = (
    "Market observations lack required point-in-time eligibility timestamps "
    "('available_at') for historical use."
)

DATASET_TYPE_DAILY_BARS = "daily_bars"
DATASET_TYPE_CORPORATE_ACTIONS = "corporate_actions"
DATASET_TYPE_FUNDAMENTALS = "fundamentals"
DATASET_TYPE_OPTIONS = "options"


@dataclass(frozen=True)
class IngestionRequest:
    source: str
    retrieval_time: str
    file_path: Path | None = None


@dataclass(frozen=True)
class Security:
    security_id: str
    symbol: str
    name: str
    exchange: str | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class SecuritySummary:
    security: Security
    daily_bars_count: int = 0
    daily_bars_start: str | None = None
    daily_bars_end: str | None = None
    latest_close: float | None = None
    daily_bars_dataset_versions: list[str] = dc_field(default_factory=list)
    corporate_actions_count: int = 0
    corporate_actions_dataset_versions: list[str] = dc_field(default_factory=list)
    fundamentals_count: int = 0
    fundamentals_fiscal_periods: list[str] = dc_field(default_factory=list)
    fundamentals_dataset_versions: list[str] = dc_field(default_factory=list)
    covering_dataset_versions: list[str] = dc_field(default_factory=list)


@dataclass(frozen=True)
class DailyBar:
    security_id: str
    session_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    retrieval_time: str = ""
    available_at: str | None = None
    eligibility_provenance: str | None = None
    units: str = "USD"
    adjusted_open: float | None = None
    adjusted_high: float | None = None
    adjusted_low: float | None = None
    adjusted_close: float | None = None

    def price_for_field(self, price_field: str) -> float:
        """Return one OHLC price field from this bar."""
        if price_field == "open":
            return self.open
        if price_field == "high":
            return self.high
        if price_field == "low":
            return self.low
        return self.close


@dataclass(frozen=True)
class CorporateAction:
    security_id: str
    type: str
    effective_date: str
    value: float
    source: str
    retrieval_time: str = ""
    available_at: str | None = None
    eligibility_provenance: str | None = None
    units: str = "USD"


@dataclass(frozen=True)
class OptionContract:
    """One listed option contract with point-in-time identity metadata."""

    contract_id: str
    security_id: str
    expiration: str
    strike: float
    right: Literal["put", "call"]
    multiplier: float = 100.0
    contract_symbol: str | None = None
    exercise_style: str = "american"
    settlement_type: str = "physical"
    available_at: str | None = None
    inactivated_at: str | None = None
    source: str = ""
    retrieval_time: str = ""

    @property
    def option_type(self) -> Literal["put", "call"]:
        return self.right


@dataclass(frozen=True)
class OptionTrade:
    """One completed option trade. Historical data has no bid or ask quote."""

    contract_id: str
    timestamp: str
    price: float
    size: float = 0.0
    available_at: str | None = None
    source: str = ""
    retrieval_time: str = ""
    underlying_price: float | None = None
    risk_free_rate: float = 0.0
    dividend_yield: float = 0.0

    @property
    def trade_time(self) -> str:
        return self.timestamp


@dataclass(frozen=True)
class UnderlyingMinuteBar:
    """One point-in-time eligible underlying minute bar."""

    security_id: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    available_at: str | None = None
    source: str = ""
    retrieval_time: str = ""


@dataclass(frozen=True)
class EarningsEvent:
    """An earnings event known at the recorded eligibility time."""

    security_id: str
    event_date: str
    timing: Literal["before_open", "after_close", "unknown"] = "unknown"
    available_at: str | None = None
    source: str = ""


@dataclass(frozen=True, init=False)
class OptionMarketData:
    """The named, typed inputs used by an options Backtest Run."""

    contracts: tuple[OptionContract, ...]
    option_trades: tuple[OptionTrade, ...]
    underlying_bars: tuple[UnderlyingMinuteBar, ...]
    daily_bars: tuple[DailyBar, ...]
    earnings: tuple[EarningsEvent, ...]
    dataset_version_id: str
    provider: str

    def __init__(
        self,
        contracts: Sequence[OptionContract] = (),
        option_trades: Sequence[OptionTrade] = (),
        underlying_bars: Sequence[UnderlyingMinuteBar] = (),
        daily_bars: Sequence[DailyBar] = (),
        earnings: Sequence[EarningsEvent] = (),
        dataset_version_id: str = "",
        provider: str = "alpaca",
        *,
        trades: Sequence[OptionTrade] | None = None,
    ) -> None:
        object.__setattr__(self, "contracts", tuple(contracts))
        object.__setattr__(
            self, "option_trades", tuple(trades if trades is not None else option_trades)
        )
        object.__setattr__(
            self,
            "underlying_bars",
            tuple(underlying_bars),
        )
        object.__setattr__(self, "daily_bars", tuple(daily_bars))
        object.__setattr__(self, "earnings", tuple(earnings))
        object.__setattr__(self, "dataset_version_id", dataset_version_id)
        object.__setattr__(self, "provider", provider)

    @property
    def trades(self) -> tuple[OptionTrade, ...]:
        return self.option_trades


@dataclass(frozen=True)
class FundamentalFact:
    security_id: str
    field: str
    fiscal_period: str
    value: float | str
    unit: str = "USD"
    filed_at: str | None = None
    available_at: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    eligibility_provenance: str | None = None
    source: str = ""
    retrieval_time: str = ""
    incomplete_fields: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ValidationSummary:
    """Typed validation metadata persisted with a Dataset Version."""

    row_count: int
    rejected_count: int
    missing_fields: dict[str, int]
    total_warnings: int
    warnings: list[str]
    has_temporal_provenance: bool
    is_fundamentals: bool
    is_corporate_actions: bool
    dataset_type: str

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "row_count": self.row_count,
            "rejected_count": self.rejected_count,
            "missing_fields": self.missing_fields,
            "total_warnings": self.total_warnings,
            "warnings": self.warnings,
            "has_temporal_provenance": self.has_temporal_provenance,
            "is_fundamentals": self.is_fundamentals,
            "is_corporate_actions": self.is_corporate_actions,
            "dataset_type": self.dataset_type,
        }

    def with_warnings(self, warnings: list[str]) -> "ValidationSummary":
        if not warnings:
            return self
        return ValidationSummary(
            row_count=self.row_count,
            rejected_count=self.rejected_count,
            missing_fields=self.missing_fields,
            total_warnings=self.total_warnings + len(warnings),
            warnings=(self.warnings + warnings)[:100],
            has_temporal_provenance=self.has_temporal_provenance,
            is_fundamentals=self.is_fundamentals,
            is_corporate_actions=self.is_corporate_actions,
            dataset_type=self.dataset_type,
        )

    @classmethod
    def from_json(cls, raw: str) -> "ValidationSummary":
        payload = json.loads(raw)
        return cls(
            row_count=int(payload["row_count"]),
            rejected_count=int(payload["rejected_count"]),
            missing_fields={
                str(field): int(count) for field, count in payload["missing_fields"].items()
            },
            total_warnings=int(payload["total_warnings"]),
            warnings=[str(warning) for warning in payload["warnings"]],
            has_temporal_provenance=bool(payload.get("has_temporal_provenance", False)),
            is_fundamentals=bool(payload.get("is_fundamentals", False)),
            is_corporate_actions=bool(payload.get("is_corporate_actions", False)),
            dataset_type=str(payload.get("dataset_type", DATASET_TYPE_DAILY_BARS)),
        )


@dataclass(frozen=True)
class DatasetVersion:
    id: str
    source: str
    retrieval_time: str
    coverage_start: str | None
    coverage_end: str | None
    files: list[str]
    validation_summary: ValidationSummary
    dataset_type: str = DATASET_TYPE_DAILY_BARS


@dataclass(frozen=True)
class LoadedDataset:
    dataframe: pd.DataFrame
    has_provenance: bool
    dataset_type: str


@dataclass(frozen=True)
class CoverageReport:
    id: str
    source: str
    retrieval_time: str
    coverage_start: str | None
    coverage_end: str | None
    row_count: int
    rejected_count: int
    missing_fields: dict[str, int]
    warnings: list[str]
    total_warnings: int
    files: list[str]
    has_temporal_provenance: bool = False
    is_fundamentals: bool = False
    is_corporate_actions: bool = False
    dataset_type: str = DATASET_TYPE_DAILY_BARS


def _parse_incomplete_fields(raw: str | Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalize the incomplete_fields marker from a provider or file row."""
    if raw is None:
        return None
    match raw:
        case list() | tuple():
            return tuple(str(name) for name in raw)
        case str():
            trimmed = raw.strip()
            if not trimmed or trimmed.lower() in ("nan", "none", "null"):
                return None
            if trimmed.startswith("[") and trimmed.endswith("]"):
                with contextlib.suppress(ValueError, SyntaxError):
                    parsed = ast.literal_eval(trimmed)
                    match parsed:
                        case list() | tuple():
                            return tuple(str(name) for name in parsed)
            return (trimmed,)
        case float():
            return None if math.isnan(raw) else (str(raw),)
        case _:
            if hasattr(raw, "tolist"):
                return tuple(str(name) for name in raw.tolist())
            return (str(raw),)



@dataclass(frozen=True)
class IngestionValidationResult:
    valid_rows: list[dict[str, JsonValue]]
    warnings: list[str]
    missing_fields: dict[str, int]


@dataclass(frozen=True)
class DatasetCoverageRange:
    coverage_start: str | None
    coverage_end: str | None


def _calculate_dataset_coverage_range(df_valid: pd.DataFrame) -> DatasetCoverageRange:
    if "session_date" in df_valid.columns:
        return DatasetCoverageRange(
            coverage_start=df_valid["session_date"].min(),
            coverage_end=df_valid["session_date"].max(),
        )
    if "effective_date" in df_valid.columns:
        return DatasetCoverageRange(
            coverage_start=df_valid["effective_date"].min(),
            coverage_end=df_valid["effective_date"].max(),
        )
    if "timestamp" in df_valid.columns:
        return DatasetCoverageRange(
            coverage_start=df_valid["timestamp"].min(),
            coverage_end=df_valid["timestamp"].max(),
        )
    if ("period_start" in df_valid.columns and df_valid["period_start"].notna().any()) or (
        "period_end" in df_valid.columns and df_valid["period_end"].notna().any()
    ):
        starts = (
            df_valid["period_start"].dropna()
            if "period_start" in df_valid.columns
            else pd.Series(dtype="object")
        )
        ends = (
            df_valid["period_end"].dropna()
            if "period_end" in df_valid.columns
            else pd.Series(dtype="object")
        )
        c_start = starts.min() if not starts.empty else ends.min()
        c_end = ends.max() if not ends.empty else starts.max()
        return DatasetCoverageRange(coverage_start=c_start, coverage_end=c_end)
    if "fiscal_period" in df_valid.columns:
        return DatasetCoverageRange(
            coverage_start=df_valid["fiscal_period"].min(),
            coverage_end=df_valid["fiscal_period"].max(),
        )
    return DatasetCoverageRange(coverage_start=None, coverage_end=None)


def _detect_dataset_type(df_raw: pd.DataFrame) -> str:
    is_fundamental = {"field", "fiscal_period", "value"}.issubset(set(df_raw.columns))
    is_corporate_action = {"effective_date", "value"}.issubset(set(df_raw.columns)) and (
        "type" in df_raw.columns or "action_type" in df_raw.columns
    )
    is_daily_bar = {"open", "high", "low", "close", "volume"}.issubset(set(df_raw.columns))
    option_markers = {"contract_id", "expiration", "option_type", "right", "trade_time"}
    is_options = bool(option_markers.intersection(set(df_raw.columns))) and (
        "contract_id" in df_raw.columns or "expiration" in df_raw.columns
    )

    if is_options:
        return DATASET_TYPE_OPTIONS
    if is_corporate_action:
        return DATASET_TYPE_CORPORATE_ACTIONS
    if is_fundamental:
        return DATASET_TYPE_FUNDAMENTALS
    if is_daily_bar:
        return DATASET_TYPE_DAILY_BARS

    required = {"symbol", "date", "open", "high", "low", "close", "volume"}
    missing_cols = required - set(df_raw.columns)
    raise ValueError(f"Missing required columns: {sorted(missing_cols)}")


def _parse_option_contract_record(
    store: MarketDataStore, raw: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    for field_name in ("contract_id", "security_id", "expiration", "strike", "right"):
        if raw.get(field_name) is None:
            raise ValueError(f"{field_name} is missing")
    raw["strike"] = store._finite_raw_number(raw.get("strike"), "strike")
    right = str(raw.get("right") or raw.get("option_type") or "").lower()
    if right not in {"put", "call"}:
        raise ValueError("right must be put or call")
    raw["right"] = right
    return raw


def _parse_option_trade_record(
    store: MarketDataStore, raw: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    for field_name in ("contract_id", "timestamp", "price"):
        if raw.get(field_name) is None and not (
            field_name == "timestamp" and raw.get("trade_time") is not None
        ):
            raise ValueError(f"{field_name} is missing")
    raw["timestamp"] = raw.get("timestamp") or raw.get("trade_time")
    raw["price"] = store._finite_raw_number(raw.get("price"), "price")
    if raw.get("size") is not None:
        raw["size"] = store._finite_raw_number(raw["size"], "size")
    return raw


def _parse_underlying_bar_record(
    store: MarketDataStore, raw: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    for field_name in ("security_id", "timestamp", "open", "high", "low", "close"):
        if raw.get(field_name) is None:
            raise ValueError(f"{field_name} is missing")
    for field_name in ("open", "high", "low", "close", "volume"):
        if raw.get(field_name) is not None:
            raw[field_name] = store._finite_raw_number(raw[field_name], field_name)
    return raw


def _parse_daily_bar_record(
    store: MarketDataStore, raw: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    for field_name in ("security_id", "date", "open", "high", "low", "close"):
        if raw.get(field_name) is None:
            raise ValueError(f"{field_name} is missing")
    for field_name in ("open", "high", "low", "close", "volume"):
        if raw.get(field_name) is not None:
            raw[field_name] = store._finite_raw_number(raw[field_name], field_name)
    return raw


def _parse_earnings_record(
    store: MarketDataStore, raw: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    for field_name in ("security_id", "event_date", "timing"):
        if raw.get(field_name) is None:
            raise ValueError(f"{field_name} is missing")
    if str(raw["timing"]).lower() not in {"before_open", "after_close", "unknown"}:
        raise ValueError("timing must be before_open, after_close, or unknown")
    return raw


_OPTION_RECORD_PARSERS: dict[
    str,
    Callable[[MarketDataStore, dict[str, JsonValue]], dict[str, JsonValue]],
] = {
    "contract": _parse_option_contract_record,
    "trade": _parse_option_trade_record,
    "underlying_bar": _parse_underlying_bar_record,
    "daily_bar": _parse_daily_bar_record,
    "earnings": _parse_earnings_record,
}


def _validate_options_dataset(
    store: MarketDataStore, df_raw: pd.DataFrame, request: IngestionRequest
) -> IngestionValidationResult:
    warnings: list[str] = []
    valid_rows: list[dict[str, JsonValue]] = []
    missing_fields: dict[str, int] = {}

    check_cols = [
        "record_type",
        "contract_id",
        "security_id",
        "symbol",
        "expiration",
        "strike",
        "right",
        "timestamp",
        "trade_time",
        "price",
        "available_at",
    ]
    for col in check_cols:
        if col in df_raw.columns:
            missing_fields[col] = int(df_raw[col].map(store._is_missing).sum())

    for i, row in df_raw.iterrows():
        row_num = i + 1
        try:
            raw = {
                str(key): (None if store._is_missing(value) else value)
                for key, value in row.to_dict().items()
            }
            record_type = str(raw.get("record_type") or "").lower()
            if not record_type:
                record_type = (
                    "trade"
                    if raw.get("price") is not None and raw.get("timestamp") is not None
                    else "contract"
                )

            parser = _OPTION_RECORD_PARSERS.get(record_type)
            if parser is None:
                raise ValueError(
                    "record_type must be contract, trade, underlying_bar, daily_bar, or earnings"
                )

            parsed_raw = parser(store, raw)
            parsed_raw["record_type"] = record_type
            parsed_raw["source"] = request.source
            parsed_raw["retrieval_time"] = request.retrieval_time
            valid_rows.append(parsed_raw)
        except Exception as error:
            warnings.append(f"Rejected row {row_num}: {error}")

    return IngestionValidationResult(
        valid_rows=valid_rows, warnings=warnings, missing_fields=missing_fields
    )


def _validate_fundamentals_dataset(
    store: MarketDataStore, df_raw: pd.DataFrame, request: IngestionRequest
) -> IngestionValidationResult:
    warnings: list[str] = []
    valid_rows: list[dict[str, JsonValue]] = []
    missing_fields: dict[str, int] = {}

    check_cols = [
        "security_id",
        "symbol",
        "field",
        "fiscal_period",
        "value",
        "unit",
        "filed_at",
        "available_at",
        "period_start",
        "period_end",
        "eligibility_provenance",
    ]
    for col in check_cols:
        if col in df_raw.columns:
            missing_fields[col] = int(df_raw[col].isna().sum() + (df_raw[col] == "").sum())

    for i, row in df_raw.iterrows():
        row_num = i + 1
        try:
            sec_id = store._security_id(row)
            field = store._required_text(row, "field")
            fiscal_period = store._required_text(row, "fiscal_period")

            raw_val = row["value"]
            if store._is_missing(raw_val):
                raise ValueError("value is missing")

            val: float | str = str(raw_val).strip()
            with contextlib.suppress(ValueError, TypeError):
                numeric_val = float(raw_val)
                if not math.isfinite(numeric_val):
                    raise ValueError("value must be finite")
                val = numeric_val

            unit = store._optional_text(row, "unit", "units", default="USD") or "USD"
            filed_at = store._optional_text(row, "filed_at")
            available_at = store._optional_text(row, "available_at")
            raw_incomplete = row.get("incomplete_fields")
            incomplete_fields = _parse_incomplete_fields(raw_incomplete)

            valid_rows.append(
                {
                    "security_id": sec_id,
                    "field": field,
                    "fiscal_period": fiscal_period,
                    "value": val,
                    "unit": unit,
                    "filed_at": filed_at,
                    "available_at": available_at,
                    "period_start": store._optional_text(row, "period_start"),
                    "period_end": store._optional_text(row, "period_end"),
                    "eligibility_provenance": store._optional_text(row, "eligibility_provenance"),
                    "source": request.source,
                    "retrieval_time": request.retrieval_time,
                    "incomplete_fields": incomplete_fields,
                }
            )
        except Exception as e:
            warnings.append(f"Rejected row {row_num}: {e}")

    return IngestionValidationResult(
        valid_rows=valid_rows, warnings=warnings, missing_fields=missing_fields
    )


def _validate_corporate_actions_dataset(
    store: MarketDataStore, df_raw: pd.DataFrame, request: IngestionRequest
) -> IngestionValidationResult:
    warnings: list[str] = []
    valid_rows: list[dict[str, JsonValue]] = []
    missing_fields: dict[str, int] = {}

    check_cols = [
        "security_id",
        "symbol",
        "type",
        "action_type",
        "effective_date",
        "value",
        "unit",
        "units",
        "available_at",
        "eligibility_provenance",
    ]
    for col in check_cols:
        if col in df_raw.columns:
            missing_fields[col] = int(df_raw[col].map(store._is_missing).sum())

    for i, row in df_raw.iterrows():
        row_num = i + 1
        try:
            valid_rows.append(
                {
                    "security_id": store._security_id(row),
                    "type": store._required_text_from_fields(row, "type", "action_type"),
                    "effective_date": store._canonical_date(
                        store._required_text(row, "effective_date")
                    ),
                    "value": store._required_number(row, "value"),
                    "units": store._optional_text(row, "units", "unit", default="USD") or "USD",
                    "source": request.source,
                    "retrieval_time": request.retrieval_time,
                    "available_at": store._optional_text(row, "available_at"),
                    "eligibility_provenance": store._optional_text(row, "eligibility_provenance"),
                }
            )
        except Exception as e:
            warnings.append(f"Rejected row {row_num}: {e}")

    return IngestionValidationResult(
        valid_rows=valid_rows, warnings=warnings, missing_fields=missing_fields
    )


def _validate_daily_bars_dataset(
    store: MarketDataStore, df_raw: pd.DataFrame, request: IngestionRequest
) -> IngestionValidationResult:
    warnings: list[str] = []
    valid_rows: list[dict[str, JsonValue]] = []
    missing_fields: dict[str, int] = {}

    required = {"open", "high", "low", "close", "volume"}
    for col in list(required) + ["symbol", "date", "session_date"]:
        if col in df_raw.columns:
            missing_fields[col] = int(df_raw[col].map(store._is_missing).sum())

    for i, row in df_raw.iterrows():
        row_num = i + 1
        try:
            sec_id = store._security_id(row)
            date_str = store._required_text_from_fields(row, "date", "session_date")
            date = store._canonical_date(date_str)

            open_px = store._required_number(row, "open")
            high_px = store._required_number(row, "high")
            low_px = store._required_number(row, "low")
            close_px = store._required_number(row, "close")
            volume = store._required_number(row, "volume")

            units = store._optional_text(row, "units", "unit", default="USD") or "USD"
            available_at = store._optional_text(row, "available_at")

            valid_rows.append(
                {
                    "security_id": sec_id,
                    "session_date": date,
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close_px,
                    "volume": volume,
                    "units": units,
                    "source": request.source,
                    "retrieval_time": request.retrieval_time,
                    "available_at": available_at,
                    "eligibility_provenance": store._optional_text(row, "eligibility_provenance"),
                    "adjusted_open": store._optional_number(row, "adjusted_open", "adj_open"),
                    "adjusted_high": store._optional_number(row, "adjusted_high", "adj_high"),
                    "adjusted_low": store._optional_number(row, "adjusted_low", "adj_low"),
                    "adjusted_close": store._optional_number(row, "adjusted_close", "adj_close"),
                }
            )
        except Exception as e:
            warnings.append(f"Rejected row {row_num}: {e}")

    return IngestionValidationResult(
        valid_rows=valid_rows, warnings=warnings, missing_fields=missing_fields
    )


_INGESTION_VALIDATORS: dict[
    str,
    Callable[[MarketDataStore, pd.DataFrame, IngestionRequest], IngestionValidationResult],
] = {
    DATASET_TYPE_OPTIONS: _validate_options_dataset,
    DATASET_TYPE_FUNDAMENTALS: _validate_fundamentals_dataset,
    DATASET_TYPE_CORPORATE_ACTIONS: _validate_corporate_actions_dataset,
    DATASET_TYPE_DAILY_BARS: _validate_daily_bars_dataset,
}


class MarketDataStore:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.datasets_dir = workspace_root / "datasets"
        self.datasets_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = workspace_root / "catalogue.duckdb"
        self._init_db()
        self._init_securities_db()

    def _init_db(self) -> None:
        with duckdb.connect(str(self.db_path)) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    id VARCHAR PRIMARY KEY,
                    source VARCHAR,
                    retrieval_time VARCHAR,
                    coverage_start VARCHAR,
                    coverage_end VARCHAR,
                    files JSON,
                    validation_summary JSON
                )
            """)

    def _init_securities_db(self) -> None:
        with duckdb.connect(str(self.db_path)) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS securities (
                    security_id VARCHAR PRIMARY KEY,
                    symbol VARCHAR,
                    name VARCHAR,
                    exchange VARCHAR,
                    currency VARCHAR,
                    source VARCHAR,
                    retrieval_time VARCHAR
                )
            """)

    def _read_dataframe(self, file_path: Path) -> pd.DataFrame:
        suffix = file_path.suffix.lower()
        if suffix not in (".csv", ".json", ".parquet", ".pq"):
            raise ValueError(
                f"Unsupported file extension '{suffix}'. Supported formats: .csv, .json, .parquet"
            )

        try:
            if suffix == ".csv":
                return pd.read_csv(file_path, dtype=str)
            if suffix == ".json":
                return pd.read_json(file_path, dtype=str)
            return pd.read_parquet(file_path).astype(str)
        except Exception as error:
            format_name = suffix.removeprefix(".").upper()
            raise ValueError(f"Failed to parse {format_name} file: {error}") from error

    @staticmethod
    def _is_missing(value: str | float | int | bool | None) -> bool:
        if bool(pd.isna(value)):
            return True
        return str(value).strip().lower() in {"", "nan", "nat", "none"}

    @classmethod
    def _required_text(cls, row: pd.Series, field: str) -> str:
        value = row[field]
        if cls._is_missing(value):
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is missing")
        return str(value).strip()

    @classmethod
    def _required_number(cls, row: pd.Series, field: str) -> float:
        value = row[field]
        if cls._is_missing(value):
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is missing")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be finite")
        return number

    @classmethod
    def _security_id(cls, row: pd.Series) -> str:
        for field in ("security_id", "symbol"):
            if field in row and not cls._is_missing(row[field]):
                return str(row[field]).strip()
        raise ValueError("security_id / symbol is missing")

    @classmethod
    def _required_text_from_fields(cls, row: pd.Series, *fields: str) -> str:
        for field in fields:
            if field in row and not cls._is_missing(row[field]):
                return str(row[field]).strip()
        label = " / ".join(fields)
        raise ValueError(f"{label.replace('_', ' ').capitalize()} is missing")

    @classmethod
    def _optional_text(cls, row: pd.Series, *fields: str, default: str | None = None) -> str | None:
        for field in fields:
            if field in row and not cls._is_missing(row[field]):
                return str(row[field]).strip()
        return default

    @classmethod
    def _finite_raw_number(cls, value: str | int | float | bool | None, field: str) -> float:
        if cls._is_missing(value):
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is missing")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be finite")
        return number

    @classmethod
    def _optional_number(cls, row: pd.Series, *fields: str) -> float | None:
        for field in fields:
            if field in row and not cls._is_missing(row[field]):
                return cls._required_number(row, field)
        return None

    @staticmethod
    def _canonical_date(value: str) -> str:
        return pd.to_datetime(value, errors="raise").strftime("%Y-%m-%d")

    @classmethod
    def _eligibility_values(cls, df: pd.DataFrame, dataset_type: str) -> pd.Series:
        if df.empty:
            return pd.Series(index=df.index, dtype="object")

        eligibility = pd.Series(pd.NA, index=df.index, dtype="object")
        blocked_fallback = pd.Series(False, index=df.index)
        if dataset_type == DATASET_TYPE_FUNDAMENTALS and "eligibility_provenance" in df.columns:
            blocked_fallback = df["eligibility_provenance"].eq("missing_acceptance_time")

        for field in ["available_at"]:
            if field not in df.columns:
                continue
            missing = eligibility.map(cls._is_missing)
            eligibility.loc[missing] = df.loc[missing, field]

        if dataset_type == DATASET_TYPE_FUNDAMENTALS and "filed_at" in df.columns:
            missing = eligibility.map(cls._is_missing) & ~blocked_fallback
            eligibility.loc[missing] = df.loc[missing, "filed_at"]

        return eligibility

    @classmethod
    def _has_complete_temporal_provenance(
        cls, df: pd.DataFrame, dataset_type: str = DATASET_TYPE_DAILY_BARS
    ) -> bool:
        if df.empty:
            return False

        eligibility = cls._eligibility_values(df, dataset_type)
        if eligibility.map(cls._is_missing).any():
            return False

        try:
            pd.to_datetime(eligibility, utc=True, errors="raise")
        except (TypeError, ValueError):
            return False

        return True

    def _eligible_timestamps_for_historical_use(
        self,
        df: pd.DataFrame,
        *,
        has_provenance: bool,
        dataset_type: str = DATASET_TYPE_DAILY_BARS,
    ) -> pd.Series:
        if not has_provenance or not self._has_complete_temporal_provenance(df, dataset_type):
            raise InsufficientTimestampError(TEMPORAL_PROVENANCE_ERROR_MESSAGE)

        return pd.to_datetime(self._eligibility_values(df, dataset_type), utc=True, errors="raise")

    def ingest(self, request: IngestionRequest) -> DatasetVersion:
        if request.file_path is None:
            raise ValueError("File imports require a file path.")
        return self._publish_dataframe(request, self._read_dataframe(request.file_path))

    def _publish_dataframe(self, request: IngestionRequest, df_raw: pd.DataFrame) -> DatasetVersion:
        """Validate and persist one canonical Market Dataset."""
        dataset_type = _detect_dataset_type(df_raw)
        validator = _INGESTION_VALIDATORS.get(dataset_type)
        if validator is None:
            raise ValueError(f"Unsupported dataset type: {dataset_type}")

        validation = validator(self, df_raw, request)
        valid_rows = validation.valid_rows
        warnings = validation.warnings
        missing_fields = validation.missing_fields
        if not valid_rows:
            error_preview = "; ".join(warnings[:5]) if warnings else "No valid records present."
            raise ValueError(
                f"Import failed: 0 valid rows out of {len(df_raw)}. Errors: {error_preview}"
            )

        rejected_count = len(df_raw) - len(valid_rows)
        version_id = str(uuid4())
        files = []

        df_valid = pd.DataFrame(valid_rows)
        has_temporal_provenance = self._has_complete_temporal_provenance(df_valid, dataset_type)
        cov = _calculate_dataset_coverage_range(df_valid)
        coverage_start = cov.coverage_start
        coverage_end = cov.coverage_end

        # Arrow cannot store a mixed numeric/string object column. Preserve the
        # canonical value semantics by serializing mixed fundamentals as text;
        # query conversion restores numeric values when possible.
        if dataset_type == DATASET_TYPE_FUNDAMENTALS:
            numeric_values = pd.to_numeric(df_valid["value"], errors="coerce")
            if not numeric_values.notna().all():
                df_valid["value"] = df_valid["value"].astype(str)

        parquet_name = f"{version_id}.parquet"
        parquet_path = self.datasets_dir / parquet_name
        try:
            df_valid.to_parquet(parquet_path, engine="pyarrow", index=False)
            files.append(parquet_name)
        except Exception:
            if parquet_path.exists():
                parquet_path.unlink()
            raise

        summary = ValidationSummary(
            row_count=len(valid_rows),
            rejected_count=rejected_count,
            missing_fields=missing_fields,
            total_warnings=len(warnings),
            warnings=warnings[:100],
            has_temporal_provenance=has_temporal_provenance,
            is_fundamentals=dataset_type == DATASET_TYPE_FUNDAMENTALS,
            is_corporate_actions=dataset_type == DATASET_TYPE_CORPORATE_ACTIONS,
            dataset_type=dataset_type,
        )

        version = DatasetVersion(
            id=version_id,
            source=request.source,
            retrieval_time=request.retrieval_time,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            files=files,
            validation_summary=summary,
            dataset_type=dataset_type,
        )

        try:
            with duckdb.connect(str(self.db_path)) as con:
                con.execute(
                    """
                    INSERT INTO dataset_versions
                    (
                        id, source, retrieval_time, coverage_start, coverage_end,
                        files, validation_summary
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        version.id,
                        version.source,
                        version.retrieval_time,
                        version.coverage_start,
                        version.coverage_end,
                        json.dumps(version.files),
                        json.dumps(version.validation_summary.to_json()),
                    ),
                )

            distinct_securities: dict[str, Security] = {}
            for _, raw_row in df_raw.iterrows():
                try:
                    sec_id = self._security_id(raw_row)
                except Exception:
                    continue
                existing = self.get_security(sec_id)
                symbol = (
                    existing.symbol
                    if existing
                    else (self._optional_text(raw_row, "symbol") or sec_id)
                )
                name = (
                    existing.name
                    if existing
                    else (self._optional_text(raw_row, "name", "company_name") or symbol)
                )
                exchange = (
                    existing.exchange if existing else self._optional_text(raw_row, "exchange")
                )
                currency = (
                    existing.currency
                    if existing
                    else (self._optional_text(raw_row, "currency", default="USD") or "USD")
                )
                if sec_id not in distinct_securities:
                    distinct_securities[sec_id] = Security(
                        security_id=sec_id,
                        symbol=symbol,
                        name=name,
                        exchange=exchange,
                        currency=currency,
                    )
            if distinct_securities:
                self.upsert_securities(
                    list(distinct_securities.values()),
                    source=request.source,
                    retrieval_time=request.retrieval_time,
                )

        except Exception:
            if parquet_path.exists():
                parquet_path.unlink()
            raise

        return version

    def ingest_records(
        self,
        request: IngestionRequest,
        rows: list[dict[str, JsonValue]],
        *,
        warnings: list[str] | None = None,
    ) -> DatasetVersion:
        """Run provider records through the same validation as file imports."""
        if not rows:
            raise ValueError("Import failed: 0 provider records were returned.")

        version = self._publish_dataframe(request, pd.DataFrame(rows))
        try:
            return self.add_validation_warnings(version, warnings or [])
        except Exception:
            self.discard_dataset_version(version)
            raise

    def add_validation_warnings(
        self, version: DatasetVersion, warnings: list[str]
    ) -> DatasetVersion:
        """Persist provider warnings alongside the Dataset Version summary."""
        if not warnings:
            return version

        summary = version.validation_summary.with_warnings(warnings)
        with duckdb.connect(str(self.db_path)) as con:
            con.execute(
                "UPDATE dataset_versions SET validation_summary = ? WHERE id = ?",
                (json.dumps(summary.to_json()), version.id),
            )
        return DatasetVersion(
            id=version.id,
            source=version.source,
            retrieval_time=version.retrieval_time,
            coverage_start=version.coverage_start,
            coverage_end=version.coverage_end,
            files=version.files,
            validation_summary=summary,
            dataset_type=version.dataset_type,
        )

    def upsert_securities(
        self, securities: list[Security], *, source: str, retrieval_time: str
    ) -> None:
        """Persist provider-native Security identities in one transaction."""
        if not securities:
            return
        with duckdb.connect(str(self.db_path)) as con:
            for security in securities:
                con.execute(
                    """
                    INSERT INTO securities (
                        security_id, symbol, name, exchange, currency, source, retrieval_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (security_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        name = excluded.name,
                        exchange = excluded.exchange,
                        currency = excluded.currency,
                        source = excluded.source,
                        retrieval_time = excluded.retrieval_time
                    """,
                    (
                        security.security_id,
                        security.symbol,
                        security.name,
                        security.exchange,
                        security.currency,
                        source,
                        retrieval_time,
                    ),
                )

    def get_security(self, security_id: str) -> Security | None:
        try:
            valid_id = validate_security_id(security_id)
        except Exception:
            return None

        with duckdb.connect(str(self.db_path)) as con:
            row = con.execute(
                "SELECT security_id, symbol, name, exchange, currency FROM securities "
                "WHERE security_id = ? OR UPPER(symbol) = UPPER(?) LIMIT 1",
                (valid_id, valid_id),
            ).fetchone()
        if not row:
            return None
        return Security(
            security_id=row[0],
            symbol=row[1],
            name=row[2],
            exchange=row[3],
            currency=row[4],
        )

    def search_securities(self, query: str | None = None, limit: int = 50) -> list[Security]:
        with duckdb.connect(str(self.db_path)) as con:
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                rows = con.execute(
                    "SELECT security_id, symbol, name, exchange, currency FROM securities "
                    "WHERE symbol ILIKE ? OR name ILIKE ? ORDER BY symbol LIMIT ?",
                    (pattern, pattern, limit),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT security_id, symbol, name, exchange, currency FROM securities "
                    "ORDER BY symbol LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            Security(
                security_id=row[0],
                symbol=row[1],
                name=row[2],
                exchange=row[3],
                currency=row[4],
            )
            for row in rows
        ]

    def list_securities(self) -> list[Security]:
        return self.search_securities(limit=1000)

    def get_security_summary(self, security_id: str) -> SecuritySummary | None:
        security = self.get_security(security_id)
        if not security:
            return None

        with duckdb.connect(str(self.db_path)) as con:
            versions = con.execute(
                "SELECT id, files, validation_summary FROM dataset_versions"
            ).fetchall()

        daily_bars_count = 0
        daily_bars_start: str | None = None
        daily_bars_end: str | None = None
        latest_close: float | None = None
        latest_session_date: str | None = None
        daily_bars_dataset_versions: list[str] = []

        corporate_actions_count = 0
        corporate_actions_dataset_versions: list[str] = []

        fundamentals_count = 0
        fundamentals_periods: set[str] = set()
        fundamentals_dataset_versions: list[str] = []

        target_ids = {security.security_id, security.symbol, security.symbol.upper()}

        for v_id, raw_files, raw_summary in versions:
            summary = ValidationSummary.from_json(raw_summary)
            files = [str(f) for f in json.loads(raw_files)]
            dfs = []
            for file_name in files:
                path = self.datasets_dir / file_name
                if path.exists():
                    dfs.append(pd.read_parquet(path))
            if not dfs:
                continue
            df = pd.concat(dfs, ignore_index=True)
            if df.empty:
                continue

            sec_col = (
                "security_id"
                if "security_id" in df.columns
                else ("symbol" if "symbol" in df.columns else None)
            )
            if not sec_col:
                continue

            matched_df = df[df[sec_col].astype(str).isin(target_ids)]
            if matched_df.empty:
                continue

            if summary.dataset_type == DATASET_TYPE_DAILY_BARS or (
                not summary.is_fundamentals and not summary.is_corporate_actions
            ):
                if v_id not in daily_bars_dataset_versions:
                    daily_bars_dataset_versions.append(v_id)
                daily_bars_count += len(matched_df)
                if "session_date" in matched_df.columns:
                    dates = matched_df["session_date"].dropna().astype(str).tolist()
                    if dates:
                        min_d = min(dates)
                        max_d = max(dates)
                        daily_bars_start = (
                            min_d if daily_bars_start is None else min(daily_bars_start, min_d)
                        )
                        daily_bars_end = (
                            max_d if daily_bars_end is None else max(daily_bars_end, max_d)
                        )
                        if "close" in matched_df.columns:
                            sorted_df = matched_df.sort_values(by="session_date", ascending=False)
                            newest_row = sorted_df.iloc[0]
                            newest_date = str(newest_row["session_date"])
                            if latest_session_date is None or newest_date >= latest_session_date:
                                latest_session_date = newest_date
                                if pd.notna(newest_row["close"]):
                                    latest_close = float(newest_row["close"])

            elif (
                summary.dataset_type == DATASET_TYPE_CORPORATE_ACTIONS
                or summary.is_corporate_actions
            ):
                if v_id not in corporate_actions_dataset_versions:
                    corporate_actions_dataset_versions.append(v_id)
                corporate_actions_count += len(matched_df)

            elif summary.dataset_type == DATASET_TYPE_FUNDAMENTALS or summary.is_fundamentals:
                if v_id not in fundamentals_dataset_versions:
                    fundamentals_dataset_versions.append(v_id)
                fundamentals_count += len(matched_df)
                if "fiscal_period" in matched_df.columns:
                    for period in matched_df["fiscal_period"].dropna():
                        fundamentals_periods.add(str(period))

        covering = sorted(
            list(
                set(
                    daily_bars_dataset_versions
                    + corporate_actions_dataset_versions
                    + fundamentals_dataset_versions
                )
            )
        )

        return SecuritySummary(
            security=security,
            daily_bars_count=daily_bars_count,
            daily_bars_start=daily_bars_start,
            daily_bars_end=daily_bars_end,
            latest_close=latest_close,
            daily_bars_dataset_versions=daily_bars_dataset_versions,
            corporate_actions_count=corporate_actions_count,
            corporate_actions_dataset_versions=corporate_actions_dataset_versions,
            fundamentals_count=fundamentals_count,
            fundamentals_fiscal_periods=sorted(list(fundamentals_periods)),
            fundamentals_dataset_versions=fundamentals_dataset_versions,
            covering_dataset_versions=covering,
        )

    def discard_dataset_version(self, version: DatasetVersion) -> None:
        """Remove a partially persisted provider version during rollback."""
        with duckdb.connect(str(self.db_path)) as con:
            con.execute("DELETE FROM dataset_versions WHERE id = ?", (version.id,))
        for file_name in version.files:
            path = self.datasets_dir / file_name
            if path.exists():
                path.unlink()

    def delete_dataset_version(self, dataset_version_id: str) -> None:
        """Delete one Dataset Version and the Parquet files that it owns."""
        datasets_root = self.datasets_dir.resolve()
        with duckdb.connect(str(self.db_path)) as con:
            row = con.execute(
                "SELECT files FROM dataset_versions WHERE id = ?",
                (dataset_version_id,),
            ).fetchone()
            if not row:
                raise DatasetVersionNotFoundError(
                    f"Dataset Version '{dataset_version_id}' does not exist."
                )
            raw_files = row[0]
            files = json.loads(raw_files) if isinstance(raw_files, str) else raw_files
            file_names = [str(file_name) for file_name in files] if isinstance(files, list) else []
            paths = [(self.datasets_dir / file_name).resolve() for file_name in file_names]
            if any(path.parent != datasets_root for path in paths):
                raise ValueError("Dataset Version contains an unsafe file path.")
            con.execute("DELETE FROM dataset_versions WHERE id = ?", (dataset_version_id,))

        for path in paths:
            if path.is_file():
                path.unlink()

    def bulk_delete_dataset_versions(self, dataset_version_ids: list[str]) -> list[str]:
        """Delete multiple Dataset Versions and all Parquet files that they own."""
        if not dataset_version_ids:
            return []
        deleted_ids: list[str] = []
        datasets_root = self.datasets_dir.resolve()
        with duckdb.connect(str(self.db_path)) as con:
            for version_id in dataset_version_ids:
                row = con.execute(
                    "SELECT files FROM dataset_versions WHERE id = ?",
                    (version_id,),
                ).fetchone()
                if not row:
                    continue
                raw_files = row[0]
                files = json.loads(raw_files) if isinstance(raw_files, str) else raw_files
                file_names = [str(file_name) for file_name in files] if isinstance(files, list) else []
                paths = [(self.datasets_dir / file_name).resolve() for file_name in file_names]
                if any(path.parent != datasets_root for path in paths):
                    raise ValueError("Dataset Version contains an unsafe file path.")
                con.execute("DELETE FROM dataset_versions WHERE id = ?", (version_id,))
                for path in paths:
                    if path.is_file():
                        path.unlink()
                deleted_ids.append(version_id)
        return deleted_ids

    @staticmethod
    def _coverage_from_row(row: tuple) -> CoverageReport:
        (
            version_id,
            source,
            retrieval_time,
            coverage_start,
            coverage_end,
            raw_files,
            raw_summary,
        ) = row
        summary = ValidationSummary.from_json(raw_summary)
        files = [str(file_name) for file_name in json.loads(raw_files)]
        return CoverageReport(
            id=version_id,
            source=source,
            retrieval_time=retrieval_time,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            row_count=summary.row_count,
            rejected_count=summary.rejected_count,
            missing_fields=summary.missing_fields,
            warnings=summary.warnings,
            total_warnings=summary.total_warnings,
            files=files,
            has_temporal_provenance=summary.has_temporal_provenance,
            is_fundamentals=summary.is_fundamentals,
            is_corporate_actions=summary.is_corporate_actions,
            dataset_type=summary.dataset_type,
        )

    def coverage(self, dataset_version_id: str) -> CoverageReport:
        with duckdb.connect(str(self.db_path)) as con:
            con.execute(
                """
                SELECT id, source, retrieval_time, coverage_start, coverage_end,
                       files, validation_summary
                FROM dataset_versions WHERE id = ?
                """,
                (dataset_version_id,),
            )
            row = con.fetchone()
            if not row:
                raise DatasetVersionNotFoundError(
                    f"Dataset Version '{dataset_version_id}' does not exist."
                )
            return self._coverage_from_row(row)

    def list_dataset_versions(self) -> list[CoverageReport]:
        """Return every Dataset Version as the same coverage summary used by ``coverage``."""
        with duckdb.connect(str(self.db_path)) as con:
            rows = con.execute(
                """
                SELECT id, source, retrieval_time, coverage_start, coverage_end,
                       files, validation_summary
                FROM dataset_versions
                ORDER BY retrieval_time DESC, source, id
                """
            ).fetchall()
        return [self._coverage_from_row(row) for row in rows]

    def preview(self, dataset_version_id: str, limit: int = 50) -> list[dict[str, JsonValue]]:
        loaded = self._load_dataset_df(dataset_version_id)
        return loaded.dataframe.head(limit).to_dict(orient="records")

    def _load_dataset_df(self, dataset_version_id: str) -> LoadedDataset:
        with duckdb.connect(str(self.db_path)) as con:
            con.execute(
                "SELECT files, validation_summary FROM dataset_versions WHERE id = ?",
                (dataset_version_id,),
            )
            row = con.fetchone()
            if not row:
                raise ValueError(f"DatasetVersion {dataset_version_id} not found")

            raw_files, raw_summary = row
            summary = ValidationSummary.from_json(raw_summary)
            files = [str(file_name) for file_name in json.loads(raw_files)]

        dfs = []
        for file_name in files:
            path = self.datasets_dir / file_name
            if path.exists():
                dfs.append(pd.read_parquet(path))

        dataframe = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        return LoadedDataset(
            dataframe=dataframe,
            has_provenance=summary.has_temporal_provenance,
            dataset_type=summary.dataset_type,
        )

    def _filter_by_as_of_and_symbol(
        self,
        loaded: LoadedDataset,
        *,
        symbol: str | None,
        as_of: datetime | str | None,
    ) -> pd.DataFrame:
        dataframe = loaded.dataframe
        if as_of is not None:
            as_of_utc = pd.to_datetime(as_of, utc=True)
            available_at_utc = self._eligible_timestamps_for_historical_use(
                dataframe,
                has_provenance=loaded.has_provenance,
                dataset_type=loaded.dataset_type,
            )
            dataframe = dataframe[available_at_utc <= as_of_utc]

        if symbol is not None and not dataframe.empty:
            if "security_id" in dataframe.columns:
                dataframe = dataframe[dataframe["security_id"] == symbol]
            elif "symbol" in dataframe.columns:
                dataframe = dataframe[dataframe["symbol"] == symbol]

        return dataframe

    def ensure_historical_eligibility(self, dataset_version_id: str) -> None:
        loaded = self._load_dataset_df(dataset_version_id)
        self._eligible_timestamps_for_historical_use(
            loaded.dataframe,
            has_provenance=loaded.has_provenance,
            dataset_type=loaded.dataset_type,
        )

    def history(
        self,
        dataset_version_id: str,
        *,
        symbol: str | None = None,
        as_of: str | datetime | None = None,
        as_dataframe: bool = False,
    ) -> list[DailyBar] | pd.DataFrame:
        loaded = self._load_dataset_df(dataset_version_id)
        df = self._filter_by_as_of_and_symbol(loaded, symbol=symbol, as_of=as_of)

        if as_dataframe:
            return df.reset_index(drop=True)

        bars: list[DailyBar] = []
        for _, row in df.iterrows():
            bars.append(
                DailyBar(
                    security_id=str(row["security_id"]),
                    session_date=str(row["session_date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    source=str(row.get("source", "")),
                    retrieval_time=str(row.get("retrieval_time", "")),
                    available_at=str(row["available_at"])
                    if pd.notna(row.get("available_at"))
                    and str(row.get("available_at")).strip() != ""
                    else None,
                    eligibility_provenance=str(row["eligibility_provenance"])
                    if pd.notna(row.get("eligibility_provenance"))
                    and str(row.get("eligibility_provenance")).strip() != ""
                    else None,
                    units=str(row.get("units", "USD")),
                    adjusted_open=self._optional_number(row, "adjusted_open", "adj_open"),
                    adjusted_high=self._optional_number(row, "adjusted_high", "adj_high"),
                    adjusted_low=self._optional_number(row, "adjusted_low", "adj_low"),
                    adjusted_close=self._optional_number(row, "adjusted_close", "adj_close"),
                )
            )
        return bars

    def fundamentals(
        self,
        dataset_version_id: str,
        *,
        symbol: str | None = None,
        as_of: str | datetime | None = None,
        as_dataframe: bool = False,
    ) -> list[FundamentalFact] | pd.DataFrame:
        loaded = self._load_dataset_df(dataset_version_id)
        df = self._filter_by_as_of_and_symbol(loaded, symbol=symbol, as_of=as_of)

        if "field" not in df.columns or "fiscal_period" not in df.columns:
            if as_dataframe:
                return pd.DataFrame()
            return []

        if as_dataframe:
            return df.reset_index(drop=True)

        facts: list[FundamentalFact] = []
        for _, row in df.iterrows():
            raw_val = row["value"]
            val: float | str = str(raw_val).strip()
            with contextlib.suppress(ValueError, TypeError):
                numeric_val = float(raw_val)
                if math.isfinite(numeric_val):
                    val = numeric_val

            raw_incomplete = row.get("incomplete_fields")
            incomplete_fields = _parse_incomplete_fields(raw_incomplete)

            facts.append(
                FundamentalFact(
                    security_id=str(row["security_id"]),
                    field=str(row["field"]),
                    fiscal_period=str(row["fiscal_period"]),
                    value=val,
                    unit=str(row.get("unit", "USD")),
                    filed_at=str(row["filed_at"])
                    if pd.notna(row.get("filed_at")) and str(row.get("filed_at")).strip() != ""
                    else None,
                    available_at=str(row["available_at"])
                    if pd.notna(row.get("available_at"))
                    and str(row.get("available_at")).strip() != ""
                    else None,
                    period_start=str(row["period_start"])
                    if pd.notna(row.get("period_start"))
                    and str(row.get("period_start")).strip() != ""
                    else None,
                    period_end=str(row["period_end"])
                    if pd.notna(row.get("period_end")) and str(row.get("period_end")).strip() != ""
                    else None,
                    eligibility_provenance=str(row["eligibility_provenance"])
                    if pd.notna(row.get("eligibility_provenance"))
                    and str(row.get("eligibility_provenance")).strip() != ""
                    else None,
                    source=str(row.get("source", "")),
                    retrieval_time=str(row.get("retrieval_time", "")),
                    incomplete_fields=incomplete_fields,
                )
            )
        return facts

    def corporate_actions(
        self,
        dataset_version_id: str,
        *,
        symbol: str | None = None,
        as_of: str | datetime | None = None,
        as_dataframe: bool = False,
    ) -> list[CorporateAction] | pd.DataFrame:
        loaded = self._load_dataset_df(dataset_version_id)
        df = self._filter_by_as_of_and_symbol(loaded, symbol=symbol, as_of=as_of)

        if "type" not in df.columns or "effective_date" not in df.columns:
            if as_dataframe:
                return pd.DataFrame()
            return []

        if as_dataframe:
            return df.reset_index(drop=True)

        actions: list[CorporateAction] = []
        for _, row in df.iterrows():
            actions.append(
                CorporateAction(
                    security_id=str(row["security_id"]),
                    type=str(row["type"]),
                    effective_date=str(row["effective_date"]),
                    value=float(row["value"]),
                    source=str(row.get("source", "")),
                    retrieval_time=str(row.get("retrieval_time", "")),
                    available_at=str(row["available_at"])
                    if pd.notna(row.get("available_at"))
                    and str(row.get("available_at")).strip() != ""
                    else None,
                    eligibility_provenance=str(row["eligibility_provenance"])
                    if pd.notna(row.get("eligibility_provenance"))
                    and str(row.get("eligibility_provenance")).strip() != ""
                    else None,
                    units=str(row.get("units", "USD")),
                )
            )
        return actions

    def option_market_data(
        self, dataset_version_id: str, *, as_of: str | datetime | None = None
    ) -> OptionMarketData:
        """Load one named options Dataset Version with point-in-time filtering."""
        loaded = self._load_dataset_df(dataset_version_id)
        if loaded.dataset_type != DATASET_TYPE_OPTIONS:
            raise ValueError(
                f"Dataset Version '{dataset_version_id}' is not an options Dataset Version."
            )
        dataframe = self._filter_by_as_of_and_symbol(loaded, symbol=None, as_of=as_of)

        def text(row: pd.Series, *names: str) -> str | None:
            for name in names:
                value = row.get(name)
                if value is not None and not self._is_missing(value):
                    return str(value)
            return None

        def number(row: pd.Series, *names: str, default: float | None = None) -> float | None:
            value = text(row, *names)
            return default if value is None else float(value)

        contracts: list[OptionContract] = []
        trades: list[OptionTrade] = []
        underlying_bars: list[UnderlyingMinuteBar] = []
        daily_bars: list[DailyBar] = []
        earnings: list[EarningsEvent] = []
        for _, row in dataframe.iterrows():
            record_type = (text(row, "record_type") or "").lower()
            if record_type == "contract":
                right = (text(row, "right", "option_type") or "").lower()
                contracts.append(
                    OptionContract(
                        contract_id=text(row, "contract_id") or "",
                        security_id=text(row, "security_id", "symbol") or "",
                        expiration=text(row, "expiration") or "",
                        strike=number(row, "strike", default=0.0) or 0.0,
                        right=right if right in {"put", "call"} else "put",
                        multiplier=number(row, "multiplier", "contract_size", default=100.0)
                        or 100.0,
                        contract_symbol=text(row, "contract_symbol", "option_symbol"),
                        exercise_style=text(row, "exercise_style") or "american",
                        settlement_type=text(row, "settlement_type") or "physical",
                        available_at=text(row, "available_at"),
                        inactivated_at=text(row, "inactivated_at"),
                        source=text(row, "source") or "",
                        retrieval_time=text(row, "retrieval_time") or "",
                    )
                )
            elif record_type == "trade":
                trades.append(
                    OptionTrade(
                        contract_id=text(row, "contract_id") or "",
                        timestamp=text(row, "timestamp", "trade_time") or "",
                        price=number(row, "price", default=0.0) or 0.0,
                        size=number(row, "size", default=0.0) or 0.0,
                        available_at=text(row, "available_at"),
                        source=text(row, "source") or "",
                        retrieval_time=text(row, "retrieval_time") or "",
                        underlying_price=number(row, "underlying_price", "stock_price"),
                        risk_free_rate=number(row, "risk_free_rate", default=0.0) or 0.0,
                        dividend_yield=number(row, "dividend_yield", default=0.0) or 0.0,
                    )
                )
            elif record_type == "underlying_bar":
                underlying_bars.append(
                    UnderlyingMinuteBar(
                        security_id=text(row, "security_id", "symbol") or "",
                        timestamp=text(row, "timestamp") or "",
                        open=number(row, "open", default=0.0) or 0.0,
                        high=number(row, "high", default=0.0) or 0.0,
                        low=number(row, "low", default=0.0) or 0.0,
                        close=number(row, "close", default=0.0) or 0.0,
                        volume=number(row, "volume", default=0.0) or 0.0,
                        available_at=text(row, "available_at"),
                        source=text(row, "source") or "",
                        retrieval_time=text(row, "retrieval_time") or "",
                    )
                )
            elif record_type == "daily_bar":
                daily_bars.append(
                    DailyBar(
                        security_id=text(row, "security_id", "symbol") or "",
                        session_date=text(row, "date", "session_date") or "",
                        open=number(row, "open", default=0.0) or 0.0,
                        high=number(row, "high", default=0.0) or 0.0,
                        low=number(row, "low", default=0.0) or 0.0,
                        close=number(row, "close", default=0.0) or 0.0,
                        volume=number(row, "volume", default=0.0) or 0.0,
                        source=text(row, "source") or "",
                        retrieval_time=text(row, "retrieval_time") or "",
                        available_at=text(row, "available_at"),
                    )
                )
            elif record_type == "earnings":
                timing = (text(row, "timing") or "unknown").lower()
                earnings.append(
                    EarningsEvent(
                        security_id=text(row, "security_id", "symbol") or "",
                        event_date=text(row, "event_date") or "",
                        timing=timing
                        if timing in {"before_open", "after_close", "unknown"}
                        else "unknown",
                        available_at=text(row, "available_at"),
                        source=text(row, "source") or "",
                    )
                )
        return OptionMarketData(
            contracts=contracts,
            option_trades=trades,
            underlying_bars=underlying_bars,
            daily_bars=daily_bars,
            earnings=earnings,
            dataset_version_id=dataset_version_id,
        )
