import tempfile
from datetime import UTC, datetime
from pathlib import Path

from market_research_lab.market_data import IngestionRequest, MarketDataStore


def test_import_csv_validates_and_creates_dataset_version():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        # Create a test CSV
        csv_path = workspace / "test.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume\n"
            "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000\n"
            "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000\n"
            "INVALID,bad_date,1,2,3,4,5\n",
            encoding="utf-8",
        )

        request = IngestionRequest(
            source="test_source", file_path=csv_path, retrieval_time=datetime.now(UTC).isoformat()
        )

        version = store.ingest(request)

        assert version.source == "test_source"
        assert len(version.files) == 1
        assert version.files[0].endswith(".parquet")

        coverage = store.coverage(version.id)
        assert coverage.row_count == 2
        assert coverage.rejected_count == 1
        assert coverage.warnings[0].startswith("Rejected row")
