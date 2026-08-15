"""Market data ingestion, storage, and queries."""

from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from .json_types import JsonValue


class InadequateTemporalProvenanceError(ValueError):
    """Raised when market observations lack required point-in-time eligibility timestamps."""


TEMPORAL_PROVENANCE_ERROR_MESSAGE = (
    "Market observations lack required point-in-time eligibility timestamps "
    "('available_at') for historical use."
)

DATASET_TYPE_DAILY_BARS = "daily_bars"
DATASET_TYPE_CORPORATE_ACTIONS = "corporate_actions"
DATASET_TYPE_FUNDAMENTALS = "fundamentals"


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


def _parse_incomplete_fields(raw: object) -> tuple[str, ...] | None:
    """Normalize the incomplete_fields marker from a provider or file row.

    Provider JSON rows are read back with ``dtype=str``, so a list column
    arrives as its Python repr (e.g. "['fy', 'frame']"). Accept the list
    directly when present and parse the repr otherwise.
    """
    if isinstance(raw, (list, tuple)):
        return tuple(str(name) for name in raw)
    if isinstance(raw, str) and raw.strip().startswith("["):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return None
        if isinstance(parsed, (list, tuple)):
            return tuple(str(name) for name in parsed)
    return None


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
            raise InadequateTemporalProvenanceError(TEMPORAL_PROVENANCE_ERROR_MESSAGE)

        return pd.to_datetime(self._eligibility_values(df, dataset_type), utc=True, errors="raise")

    def ingest(self, request: IngestionRequest) -> DatasetVersion:
        if request.file_path is None:
            raise ValueError("File imports require a file path.")
        return self._publish_dataframe(request, self._read_dataframe(request.file_path))

    def _publish_dataframe(
        self, request: IngestionRequest, df_raw: pd.DataFrame
    ) -> DatasetVersion:
        """Validate and persist one canonical Market Dataset."""

        # Detect one canonical record family from the supplied columns.
        is_fundamental = {"field", "fiscal_period", "value"}.issubset(set(df_raw.columns))
        is_corporate_action = {"effective_date", "value"}.issubset(set(df_raw.columns)) and (
            "type" in df_raw.columns or "action_type" in df_raw.columns
        )
        is_daily_bar = {"open", "high", "low", "close", "volume"}.issubset(set(df_raw.columns))

        if is_corporate_action:
            dataset_type = DATASET_TYPE_CORPORATE_ACTIONS
        elif is_fundamental:
            dataset_type = DATASET_TYPE_FUNDAMENTALS
        elif is_daily_bar:
            dataset_type = DATASET_TYPE_DAILY_BARS
        else:
            required = {"symbol", "date", "open", "high", "low", "close", "volume"}
            missing_cols = required - set(df_raw.columns)
            raise ValueError(f"Missing required columns: {sorted(missing_cols)}")

        warnings: list[str] = []
        valid_rows: list[dict[str, JsonValue]] = []
        missing_fields: dict[str, int] = {}

        if dataset_type == DATASET_TYPE_FUNDAMENTALS:
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
                    missing_count = int(df_raw[col].isna().sum() + (df_raw[col] == "").sum())
                    missing_fields[col] = missing_count

            for i, row in df_raw.iterrows():
                row_num = i + 1
                try:
                    sec_id = self._security_id(row)

                    field = self._required_text(row, "field")

                    fiscal_period = self._required_text(row, "fiscal_period")

                    raw_val = row["value"]
                    if self._is_missing(raw_val):
                        raise ValueError("value is missing")

                    try:
                        val: float | str = float(raw_val)
                    except (ValueError, TypeError):
                        val = str(raw_val).strip()
                    else:
                        if not math.isfinite(val):
                            raise ValueError("value must be finite")

                    unit = self._optional_text(row, "unit", "units", default="USD") or "USD"
                    filed_at = self._optional_text(row, "filed_at")
                    available_at = self._optional_text(row, "available_at")
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
                            "period_start": self._optional_text(row, "period_start"),
                            "period_end": self._optional_text(row, "period_end"),
                            "eligibility_provenance": self._optional_text(
                                row, "eligibility_provenance"
                            ),
                            "source": request.source,
                            "retrieval_time": request.retrieval_time,
                            "incomplete_fields": incomplete_fields,
                        }
                    )
                except Exception as e:
                    warnings.append(f"Rejected row {row_num}: {e}")

        elif dataset_type == DATASET_TYPE_CORPORATE_ACTIONS:
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
                    missing_fields[col] = int(df_raw[col].map(self._is_missing).sum())

            for i, row in df_raw.iterrows():
                row_num = i + 1
                try:
                    valid_rows.append(
                        {
                            "security_id": self._security_id(row),
                            "type": self._required_text_from_fields(row, "type", "action_type"),
                            "effective_date": self._canonical_date(
                                self._required_text(row, "effective_date")
                            ),
                            "value": self._required_number(row, "value"),
                            "units": self._optional_text(row, "units", "unit", default="USD")
                            or "USD",
                            "source": request.source,
                            "retrieval_time": request.retrieval_time,
                            "available_at": self._optional_text(row, "available_at"),
                            "eligibility_provenance": self._optional_text(
                                row, "eligibility_provenance"
                            ),
                        }
                    )
                except Exception as e:
                    warnings.append(f"Rejected row {row_num}: {e}")

        else:
            required = {"open", "high", "low", "close", "volume"}
            for col in list(required) + ["symbol", "date", "session_date"]:
                if col in df_raw.columns:
                    missing_fields[col] = int(df_raw[col].map(self._is_missing).sum())

            for i, row in df_raw.iterrows():
                row_num = i + 1
                try:
                    sec_id = self._security_id(row)
                    date_str = self._required_text_from_fields(row, "date", "session_date")
                    date = self._canonical_date(date_str)

                    open_px = self._required_number(row, "open")
                    high_px = self._required_number(row, "high")
                    low_px = self._required_number(row, "low")
                    close_px = self._required_number(row, "close")
                    volume = self._required_number(row, "volume")

                    units = self._optional_text(row, "units", "unit", default="USD") or "USD"
                    available_at = self._optional_text(row, "available_at")

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
                            "eligibility_provenance": self._optional_text(
                                row, "eligibility_provenance"
                            ),
                            "adjusted_open": self._optional_number(
                                row, "adjusted_open", "adj_open"
                            ),
                            "adjusted_high": self._optional_number(
                                row, "adjusted_high", "adj_high"
                            ),
                            "adjusted_low": self._optional_number(row, "adjusted_low", "adj_low"),
                            "adjusted_close": self._optional_number(
                                row, "adjusted_close", "adj_close"
                            ),
                        }
                    )
                except Exception as e:
                    warnings.append(f"Rejected row {row_num}: {e}")

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
        if "session_date" in df_valid.columns:
            coverage_start = df_valid["session_date"].min()
            coverage_end = df_valid["session_date"].max()
        elif "effective_date" in df_valid.columns:
            coverage_start = df_valid["effective_date"].min()
            coverage_end = df_valid["effective_date"].max()
        elif ("period_start" in df_valid.columns and df_valid["period_start"].notna().any()) or (
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
            coverage_start = starts.min() if not starts.empty else ends.min()
            coverage_end = ends.max() if not ends.empty else starts.max()
        elif "fiscal_period" in df_valid.columns:
            coverage_start = df_valid["fiscal_period"].min()
            coverage_end = df_valid["fiscal_period"].max()
        else:
            coverage_start = None
            coverage_end = None

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

    def list_securities(self) -> list[Security]:
        with duckdb.connect(str(self.db_path)) as con:
            rows = con.execute(
                "SELECT security_id, symbol, name, exchange, currency "
                "FROM securities ORDER BY symbol"
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

    def discard_dataset_version(self, version: DatasetVersion) -> None:
        """Remove a partially persisted provider version during rollback."""
        with duckdb.connect(str(self.db_path)) as con:
            con.execute("DELETE FROM dataset_versions WHERE id = ?", (version.id,))
        for file_name in version.files:
            path = self.datasets_dir / file_name
            if path.exists():
                path.unlink()

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
                raise ValueError(f"DatasetVersion {dataset_version_id} not found")
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

        if as_dataframe:
            return df.reset_index(drop=True)

        facts: list[FundamentalFact] = []
        for _, row in df.iterrows():
            raw_val = row["value"]
            try:
                val: float | str = float(raw_val)
            except (ValueError, TypeError):
                val = str(raw_val)

            raw_incomplete = row.get("incomplete_fields")
            incomplete_fields: tuple[str, ...] | None = None
            if raw_incomplete is not None and not (
                isinstance(raw_incomplete, float) and pd.isna(raw_incomplete)
            ):
                if isinstance(raw_incomplete, (list, tuple)) or hasattr(raw_incomplete, "tolist"):
                    incomplete_fields = tuple(str(name) for name in raw_incomplete)
                else:
                    incomplete_fields = (str(raw_incomplete),)

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
