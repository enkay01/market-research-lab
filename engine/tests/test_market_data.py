import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
import pandas as pd
import pytest

from market_research_lab.market_data import IngestionRequest, MarketDataStore


def test_import_csv_validates_and_creates_dataset_version():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        csv_path = workspace / "test.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume\n"
            "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000\n"
            "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000\n"
            "INVALID,bad_date,1,2,3,4,5\n",
            encoding="utf-8",
        )

        retrieval_time = datetime.now(UTC).isoformat()
        request = IngestionRequest(
            source="test_source", file_path=csv_path, retrieval_time=retrieval_time
        )

        version = store.ingest(request)

        assert version.source == "test_source"
        assert len(version.files) == 1
        assert version.files[0].endswith(".parquet")

        coverage = store.coverage(version.id)
        assert coverage.row_count == 2
        assert coverage.rejected_count == 1
        assert coverage.warnings[0].startswith("Rejected row")
        assert "symbol" in coverage.missing_fields

        # Check point-in-time provenance in Parquet output
        parquet_path = store.datasets_dir / version.files[0]
        df_parquet = pd.read_parquet(parquet_path)
        assert "retrieval_time" in df_parquet.columns
        assert "available_at" in df_parquet.columns
        assert "units" in df_parquet.columns
        assert df_parquet["retrieval_time"].iloc[0] == retrieval_time
        assert df_parquet["available_at"].iloc[0] == "2023-01-01T16:00:00Z"


def test_import_json_and_parquet_formats():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        # JSON file
        json_path = workspace / "data.json"
        data = [
            {"symbol": "MSFT", "date": "2023-01-01", "open": 240, "high": 245, "low": 239, "close": 244, "volume": 500000}
        ]
        json_path.write_text(json.dumps(data), encoding="utf-8")

        req_json = IngestionRequest(
            source="json_src", file_path=json_path, retrieval_time="2026-01-01T00:00:00Z"
        )
        ver_json = store.ingest(req_json)
        assert ver_json.source == "json_src"
        assert store.coverage(ver_json.id).row_count == 1

        # Parquet file
        df_pq = pd.DataFrame(
            [
                {
                    "symbol": "GOOGL",
                    "date": "2023-01-01",
                    "open": 90,
                    "high": 92,
                    "low": 89,
                    "close": 91,
                    "volume": 800000,
                }
            ]
        )
        pq_path = workspace / "data.parquet"
        df_pq.to_parquet(pq_path, index=False)

        req_pq = IngestionRequest(
            source="pq_src", file_path=pq_path, retrieval_time="2026-01-01T00:00:00Z"
        )
        ver_pq = store.ingest(req_pq)
        assert ver_pq.source == "pq_src"
        assert store.coverage(ver_pq.id).row_count == 1


def test_all_rows_invalid_rejects_dataset_persistence_core_008():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        csv_path = workspace / "bad.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume\n,bad_date,abc,def,ghi,jkl,mno\n",
            encoding="utf-8",
        )

        request = IngestionRequest(
            source="bad_src", file_path=csv_path, retrieval_time="2026-01-01T00:00:00Z"
        )
        with pytest.raises(ValueError, match="Import failed: 0 valid rows"):
            store.ingest(request)
