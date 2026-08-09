"""Market data ingestion, storage, and queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd


class InadequateTemporalProvenanceError(ValueError):
    """Raised when market observations lack required point-in-time eligibility timestamps."""

    pass


@dataclass(frozen=True)
class IngestionRequest:
    source: str
    file_path: Path
    retrieval_time: str


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
    units: str = "USD"


@dataclass(frozen=True)
class CorporateAction:
    security_id: str
    type: str
    effective_date: str
    value: float
    source: str
    retrieval_time: str = ""
    available_at: str | None = None


@dataclass(frozen=True)
class FundamentalFact:
    security_id: str
    field: str
    fiscal_period: str
    value: float | str
    unit: str = "USD"
    filed_at: str | None = None
    available_at: str | None = None
    source: str = ""
    retrieval_time: str = ""


@dataclass(frozen=True)
class DatasetVersion:
    id: str
    source: str
    retrieval_time: str
    coverage_start: str | None
    coverage_end: str | None
    files: list[str]
    validation_summary: dict[str, Any]


@dataclass(frozen=True)
class CoverageReport:
    id: str
    source: str
    coverage_start: str | None
    coverage_end: str | None
    row_count: int
    rejected_count: int
    missing_fields: dict[str, int]
    warnings: list[str]
    total_warnings: int
    files: list[str]
    has_temporal_provenance: bool = False


class MarketDataStore:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.datasets_dir = workspace_root / "datasets"
        self.datasets_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = workspace_root / "catalogue.duckdb"
        self._init_db()

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

    def _read_dataframe(self, file_path: Path) -> pd.DataFrame:
        suffix = file_path.suffix.lower()
        try:
            if suffix == ".csv":
                return pd.read_csv(file_path, dtype=str)
            elif suffix == ".json":
                return pd.read_json(file_path, dtype=str)
            elif suffix in (".parquet", ".pq"):
                df = pd.read_parquet(file_path)
                return df.astype(str)
            else:
                raise ValueError(
                    f"Unsupported file extension '{suffix}'. Supported formats: .csv, .json, .parquet"
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to parse {suffix.upper()} file: {e}")

    def ingest(self, request: IngestionRequest) -> DatasetVersion:
        df_raw = self._read_dataframe(request.file_path)

        has_available_at_col = "available_at" in df_raw.columns
        has_temporal_provenance = False
        if has_available_at_col:
            non_empty = df_raw["available_at"].dropna().astype(str).str.strip()
            if not non_empty.empty and (non_empty != "").any():
                has_temporal_provenance = True

        # Check format: Fundamental facts or Daily bars
        is_fundamental = {"field", "fiscal_period", "value"}.issubset(set(df_raw.columns))
        is_daily_bar = {"open", "high", "low", "close", "volume"}.issubset(set(df_raw.columns))

        if not is_fundamental and not is_daily_bar:
            required = {"symbol", "date", "open", "high", "low", "close", "volume"}
            missing_cols = required - set(df_raw.columns)
            raise ValueError(f"Missing required columns: {sorted(missing_cols)}")

        warnings: list[str] = []
        valid_rows: list[dict[str, Any]] = []
        missing_fields: dict[str, int] = {}

        if is_fundamental:
            check_cols = ["security_id", "symbol", "field", "fiscal_period", "value", "unit", "filed_at", "available_at"]
            for col in check_cols:
                if col in df_raw.columns:
                    missing_count = int(df_raw[col].isna().sum() + (df_raw[col] == "").sum())
                    missing_fields[col] = missing_count

            for i, row in df_raw.iterrows():
                row_num = i + 1
                try:
                    sec_id = str(row.get("security_id", row.get("symbol", ""))).strip()
                    if not sec_id or sec_id == "nan":
                        raise ValueError("security_id / symbol is missing")

                    field = str(row["field"]).strip()
                    if not field or field == "nan":
                        raise ValueError("field is missing")

                    fiscal_period = str(row["fiscal_period"]).strip()
                    if not fiscal_period or fiscal_period == "nan":
                        raise ValueError("fiscal_period is missing")

                    raw_val = row["value"]
                    if pd.isna(raw_val) or str(raw_val).strip() == "":
                        raise ValueError("value is missing")

                    try:
                        val: float | str = float(raw_val)
                    except (ValueError, TypeError):
                        val = str(raw_val).strip()

                    unit = str(row.get("unit", row.get("units", "USD"))).strip() if pd.notna(row.get("unit", row.get("units"))) else "USD"
                    filed_at = str(row["filed_at"]).strip() if "filed_at" in row and pd.notna(row["filed_at"]) and str(row["filed_at"]).strip() != "" else None

                    if has_available_at_col and pd.notna(row["available_at"]) and str(row["available_at"]).strip() != "":
                        available_at = str(row["available_at"]).strip()
                    else:
                        available_at = None

                    valid_rows.append(
                        {
                            "security_id": sec_id,
                            "field": field,
                            "fiscal_period": fiscal_period,
                            "value": val,
                            "unit": unit,
                            "filed_at": filed_at,
                            "available_at": available_at,
                            "source": request.source,
                            "retrieval_time": request.retrieval_time,
                        }
                    )
                except Exception as e:
                    warnings.append(f"Rejected row {row_num}: {e}")

        else:
            required = {"open", "high", "low", "close", "volume"}
            for col in list(required) + ["symbol", "date", "session_date"]:
                if col in df_raw.columns:
                    missing_count = int(df_raw[col].isna().sum() + (df_raw[col] == "").sum())
                    missing_fields[col] = missing_count

            for i, row in df_raw.iterrows():
                row_num = i + 1
                try:
                    sec_id = str(row.get("symbol", row.get("security_id", ""))).strip()
                    if not sec_id or sec_id == "nan":
                        raise ValueError("Symbol is missing")

                    raw_date = row.get("date", row.get("session_date", ""))
                    date_str = str(raw_date).strip() if pd.notna(raw_date) else ""
                    if not date_str or date_str == "nan":
                        raise ValueError("Date is missing")
                    date = pd.to_datetime(date_str).strftime("%Y-%m-%d")

                    open_px = float(row["open"])
                    high_px = float(row["high"])
                    low_px = float(row["low"])
                    close_px = float(row["close"])
                    volume = float(row["volume"])

                    units = str(row.get("units", row.get("unit", "USD"))).strip() if pd.notna(row.get("units", row.get("unit"))) else "USD"

                    if has_available_at_col and pd.notna(row.get("available_at")) and str(row["available_at"]).strip() != "":
                        available_at = str(row["available_at"]).strip()
                    else:
                        available_at = None

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
                        }
                    )
                except Exception as e:
                    warnings.append(f"Rejected row {row_num}: {e}")

        if not valid_rows:
            error_preview = "; ".join(warnings[:5]) if warnings else "No valid records present."
            raise ValueError(f"Import failed: 0 valid rows out of {len(df_raw)}. Errors: {error_preview}")

        rejected_count = len(df_raw) - len(valid_rows)
        version_id = str(uuid4())
        files = []

        df_valid = pd.DataFrame(valid_rows)
        if "session_date" in df_valid.columns:
            coverage_start = df_valid["session_date"].min()
            coverage_end = df_valid["session_date"].max()
        elif "fiscal_period" in df_valid.columns:
            coverage_start = df_valid["fiscal_period"].min()
            coverage_end = df_valid["fiscal_period"].max()
        else:
            coverage_start = None
            coverage_end = None

        parquet_name = f"{version_id}.parquet"
        parquet_path = self.datasets_dir / parquet_name
        df_valid.to_parquet(parquet_path, engine="pyarrow", index=False)
        files.append(parquet_name)

        summary = {
            "row_count": len(valid_rows),
            "rejected_count": rejected_count,
            "missing_fields": missing_fields,
            "total_warnings": len(warnings),
            "warnings": warnings[:100],
            "has_temporal_provenance": has_temporal_provenance,
        }

        version = DatasetVersion(
            id=version_id,
            source=request.source,
            retrieval_time=request.retrieval_time,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            files=files,
            validation_summary=summary,
        )

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
                    json.dumps(version.validation_summary),
                ),
            )

        return version

    def coverage(self, dataset_version_id: str) -> CoverageReport:
        with duckdb.connect(str(self.db_path)) as con:
            con.execute(
                """
                SELECT id, source, retrieval_time, coverage_start, coverage_end, files, validation_summary 
                FROM dataset_versions WHERE id = ?
                """,
                (dataset_version_id,),
            )
            row = con.fetchone()
            if not row:
                raise ValueError(f"DatasetVersion {dataset_version_id} not found")

            version_id, source, _retrieval_time, coverage_start, coverage_end, raw_files, raw_summary = row
            summary = json.loads(raw_summary)
            files = json.loads(raw_files)

            return CoverageReport(
                id=version_id,
                source=source,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                row_count=summary.get("row_count", 0),
                rejected_count=summary.get("rejected_count", 0),
                missing_fields=summary.get("missing_fields", {}),
                warnings=summary.get("warnings", []),
                total_warnings=summary.get("total_warnings", len(summary.get("warnings", []))),
                files=files,
                has_temporal_provenance=summary.get("has_temporal_provenance", False),
            )

    def preview(self, dataset_version_id: str, limit: int = 50) -> list[dict[str, Any]]:
        df, _ = self._load_dataset_df(dataset_version_id)
        return df.head(limit).to_dict(orient="records")

    def _load_dataset_df(self, dataset_version_id: str) -> tuple[pd.DataFrame, bool]:
        with duckdb.connect(str(self.db_path)) as con:
            con.execute(
                "SELECT files, validation_summary FROM dataset_versions WHERE id = ?",
                (dataset_version_id,),
            )
            row = con.fetchone()
            if not row:
                raise ValueError(f"DatasetVersion {dataset_version_id} not found")

            raw_files, raw_summary = row
            summary = json.loads(raw_summary)
            files = json.loads(raw_files)
            has_prov = summary.get("has_temporal_provenance", False)

        dfs = []
        for file_name in files:
            path = self.datasets_dir / file_name
            if path.exists():
                dfs.append(pd.read_parquet(path))

        if not dfs:
            return pd.DataFrame(), has_prov

        df = pd.concat(dfs, ignore_index=True)
        return df, has_prov

    def _filter_by_as_of_and_symbol(
        self,
        df: pd.DataFrame,
        has_provenance: bool,
        as_of: datetime | str | None,
        symbol: str | None,
    ) -> pd.DataFrame:
        if as_of is not None:
            if not has_provenance or "available_at" not in df.columns or df["available_at"].isna().any() or (df["available_at"].astype(str).str.strip() == "").any():
                raise InadequateTemporalProvenanceError(
                    "Market observations lack required point-in-time eligibility timestamps ('available_at') for historical use."
                )

            as_of_utc = pd.to_datetime(as_of, utc=True)
            available_at_utc = pd.to_datetime(df["available_at"], utc=True)
            df = df[available_at_utc <= as_of_utc]

        if symbol is not None and not df.empty:
            if "security_id" in df.columns:
                df = df[df["security_id"] == symbol]
            elif "symbol" in df.columns:
                df = df[df["symbol"] == symbol]

        return df

    def history(
        self,
        dataset_version_id: str,
        *,
        symbol: str | None = None,
        as_of: str | datetime | None = None,
        as_dataframe: bool = False,
    ) -> list[DailyBar] | pd.DataFrame:
        df, has_prov = self._load_dataset_df(dataset_version_id)

        df = self._filter_by_as_of_and_symbol(df, has_prov, as_of, symbol)

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
                    available_at=str(row["available_at"]) if pd.notna(row.get("available_at")) and str(row.get("available_at")).strip() != "" else None,
                    units=str(row.get("units", "USD")),
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
        df, has_prov = self._load_dataset_df(dataset_version_id)

        df = self._filter_by_as_of_and_symbol(df, has_prov, as_of, symbol)

        if as_dataframe:
            return df.reset_index(drop=True)

        facts: list[FundamentalFact] = []
        for _, row in df.iterrows():
            raw_val = row["value"]
            try:
                val: float | str = float(raw_val)
            except (ValueError, TypeError):
                val = str(raw_val)

            facts.append(
                FundamentalFact(
                    security_id=str(row["security_id"]),
                    field=str(row["field"]),
                    fiscal_period=str(row["fiscal_period"]),
                    value=val,
                    unit=str(row.get("unit", "USD")),
                    filed_at=str(row["filed_at"]) if pd.notna(row.get("filed_at")) and str(row.get("filed_at")).strip() != "" else None,
                    available_at=str(row["available_at"]) if pd.notna(row.get("available_at")) and str(row.get("available_at")).strip() != "" else None,
                    source=str(row.get("source", "")),
                    retrieval_time=str(row.get("retrieval_time", "")),
                )
            )
        return facts
