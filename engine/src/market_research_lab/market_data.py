"""Market data ingestion, storage, and queries."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd


@dataclass(frozen=True)
class IngestionRequest:
    source: str
    file_path: Path
    retrieval_time: str


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
        if suffix not in (".csv", ".json", ".parquet", ".pq"):
            raise ValueError(
                f"Unsupported file extension '{suffix}'. Supported formats: .csv, .json, .parquet"
            )

        try:
            if suffix == ".csv":
                return pd.read_csv(file_path)
            if suffix == ".json":
                return pd.read_json(file_path)
            return pd.read_parquet(file_path)
        except Exception as error:
            raise ValueError(f"Failed to parse {suffix.upper()} file.") from error

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())

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

    def ingest(self, request: IngestionRequest) -> DatasetVersion:
        df_raw = self._read_dataframe(request.file_path)

        # Required columns for simple daily bars
        required = {"symbol", "date", "open", "high", "low", "close", "volume"}
        missing_cols = required - set(df_raw.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {sorted(missing_cols)}")

        warnings: list[str] = []
        valid_rows: list[dict[str, Any]] = []

        missing_fields: dict[str, int] = {}
        for col in required:
            if col in df_raw.columns:
                missing_fields[col] = int(df_raw[col].map(self._is_missing).sum())

        for row_num, (_, row) in enumerate(df_raw.iterrows(), start=1):
            try:
                symbol = self._required_text(row, "symbol")

                date_str = self._required_text(row, "date")
                date = pd.to_datetime(date_str).strftime("%Y-%m-%d")

                open_px = self._required_number(row, "open")
                high_px = self._required_number(row, "high")
                low_px = self._required_number(row, "low")
                close_px = self._required_number(row, "close")
                volume = self._required_number(row, "volume")

                units = (
                    str(row["units"]).strip()
                    if "units" in row and not self._is_missing(row["units"])
                    else "USD"
                )

                # Distinguish market eligibility time from system retrieval time (DATA-005)
                if "available_at" in row and not self._is_missing(row["available_at"]):
                    available_at = str(row["available_at"]).strip()
                else:
                    available_at = f"{date}T16:00:00Z"

                valid_rows.append(
                    {
                        "security_id": symbol,
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

        # CORE-008: Preserve error and reject saving partial/empty DatasetVersion if all rows failed
        if not valid_rows:
            error_preview = "; ".join(warnings[:5]) if warnings else "No valid records present."
            raise ValueError(
                f"Import failed: 0 valid rows out of {len(df_raw)}. Errors: {error_preview}"
            )

        rejected_count = len(df_raw) - len(valid_rows)
        version_id = str(uuid4())
        files = []

        df_valid = pd.DataFrame(valid_rows)
        coverage_start = df_valid["session_date"].min()
        coverage_end = df_valid["session_date"].max()

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
                SELECT id, source, retrieval_time, coverage_start, coverage_end, files,
                    validation_summary
                FROM dataset_versions WHERE id = ?
                """,
                (dataset_version_id,),
            )
            row = con.fetchone()
            if not row:
                raise ValueError(f"DatasetVersion {dataset_version_id} not found")

            (
                version_id,
                source,
                _retrieval_time,
                coverage_start,
                coverage_end,
                raw_files,
                raw_summary,
            ) = row
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
            )
