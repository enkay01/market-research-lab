"""Market data ingestion, storage, and queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
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
    validation_summary: dict[str, int]


@dataclass(frozen=True)
class CoverageReport:
    id: str
    source: str
    coverage_start: str | None
    coverage_end: str | None
    row_count: int
    rejected_count: int
    warnings: list[str]
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

    def ingest(self, request: IngestionRequest) -> DatasetVersion:
        # For this implementation, we read CSV, validate, write Parquet
        # and record in DuckDB

        # Read all as strings to catch errors gracefully
        try:
            df_raw = pd.read_csv(request.file_path, dtype=str)
        except Exception as e:
            raise ValueError(f"Failed to read CSV: {e}")

        # Required columns for simple daily bars
        required = {"symbol", "date", "open", "high", "low", "close", "volume"}
        missing = required - set(df_raw.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        warnings = []
        valid_rows = []

        for i, row in df_raw.iterrows():
            try:
                # Basic validation
                symbol = str(row["symbol"]).strip()
                date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
                open_px = float(row["open"])
                high_px = float(row["high"])
                low_px = float(row["low"])
                close_px = float(row["close"])
                volume = float(row["volume"])

                if not symbol or pd.isna(symbol):
                    raise ValueError("Symbol is missing")

                valid_rows.append(
                    {
                        "security_id": symbol,
                        "session_date": date,
                        "open": open_px,
                        "high": high_px,
                        "low": low_px,
                        "close": close_px,
                        "volume": volume,
                        "source": request.source,
                        "available_at": request.retrieval_time,
                    }
                )
            except Exception as e:
                warnings.append(f"Rejected row {i}: {e}")

        rejected_count = len(df_raw) - len(valid_rows)

        version_id = str(uuid4())
        files = []
        coverage_start = None
        coverage_end = None

        if valid_rows:
            df_valid = pd.DataFrame(valid_rows)
            coverage_start = df_valid["session_date"].min()
            coverage_end = df_valid["session_date"].max()

            # Write to parquet
            parquet_name = f"{version_id}.parquet"
            parquet_path = self.datasets_dir / parquet_name
            df_valid.to_parquet(parquet_path, engine="pyarrow", index=False)
            files.append(parquet_name)

        summary = {
            "row_count": len(valid_rows),
            "rejected_count": rejected_count,
            "warnings": warnings[:100],  # Cap warnings to avoid huge JSON
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

        # Save to duckdb
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
            res = con.execute(
                "SELECT * FROM dataset_versions WHERE id = ?", (dataset_version_id,)
            ).fetchone()
            if not res:
                raise ValueError(f"DatasetVersion {dataset_version_id} not found")

            # id, source, retrieval, start, end, files, summary
            summary = json.loads(res[6])

            return CoverageReport(
                id=res[0],
                source=res[1],
                coverage_start=res[3],
                coverage_end=res[4],
                row_count=summary.get("row_count", 0),
                rejected_count=summary.get("rejected_count", 0),
                warnings=summary.get("warnings", []),
                files=json.loads(res[5]),
            )
