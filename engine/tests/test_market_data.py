import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from market_research_lab.market_data import (
    CorporateAction,
    DailyBar,
    FundamentalFact,
    InadequateTemporalProvenanceError,
    IngestionRequest,
    MarketDataStore,
    Security,
)


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
        assert coverage.has_temporal_provenance is False

        # Check point-in-time provenance in Parquet output
        parquet_path = store.datasets_dir / version.files[0]
        df_parquet = pd.read_parquet(parquet_path)
        assert "retrieval_time" in df_parquet.columns
        assert "available_at" in df_parquet.columns
        assert "units" in df_parquet.columns
        assert df_parquet["retrieval_time"].iloc[0] == retrieval_time
        assert df_parquet["available_at"].iloc[0] is None


def test_row_level_missing_available_at_rejected_from_historical_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        csv_path = workspace / "data_mixed_pit.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume,available_at\n"
            "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
            "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,\n",
            encoding="utf-8",
        )

        request = IngestionRequest(
            source="mixed_pit_src", file_path=csv_path, retrieval_time="2023-01-03T00:00:00Z"
        )
        version = store.ingest(request)

        # One row is missing available_at
        with pytest.raises(
            InadequateTemporalProvenanceError,
            match="Market observations lack required point-in-time eligibility timestamps",
        ):
            store.history(version.id, as_of="2023-01-02T18:00:00Z")


def test_invalid_available_at_is_inadequate_for_historical_use():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        csv_path = workspace / "data_invalid_pit.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume,available_at\n"
            "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,not-a-timestamp\n",
            encoding="utf-8",
        )

        version = store.ingest(
            IngestionRequest(
                source="invalid_pit_src",
                file_path=csv_path,
                retrieval_time="2023-01-03T00:00:00Z",
            )
        )

        assert store.coverage(version.id).has_temporal_provenance is False
        with pytest.raises(InadequateTemporalProvenanceError):
            store.history(version.id, as_of="2023-01-02T18:00:00Z")


def test_import_json_and_parquet_formats():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        # JSON file
        json_path = workspace / "data.json"
        data = [
            {
                "symbol": "MSFT",
                "date": "2023-01-01",
                "open": 240,
                "high": 245,
                "low": 239,
                "close": 244,
                "volume": 500000,
            }
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


def test_canonical_records():
    sec = Security(
        security_id="AAPL", symbol="AAPL", name="Apple Inc.", exchange="NASDAQ", currency="USD"
    )
    assert sec.security_id == "AAPL"
    assert sec.symbol == "AAPL"
    assert sec.name == "Apple Inc."
    assert sec.exchange == "NASDAQ"
    assert sec.currency == "USD"

    bar = DailyBar(
        security_id="AAPL",
        session_date="2023-01-01",
        open=150.0,
        high=155.0,
        low=149.0,
        close=154.0,
        volume=1000000.0,
        source="test",
        retrieval_time="2023-01-01T20:00:00Z",
        available_at="2023-01-01T16:00:00Z",
        units="USD",
    )
    assert bar.security_id == "AAPL"
    assert bar.close == 154.0
    assert bar.available_at == "2023-01-01T16:00:00Z"

    corp = CorporateAction(
        security_id="AAPL",
        type="split",
        effective_date="2023-01-01",
        value=2.0,
        source="test",
        retrieval_time="2023-01-01T20:00:00Z",
        available_at="2023-01-01T16:00:00Z",
    )
    assert corp.type == "split"
    assert corp.value == 2.0

    fact = FundamentalFact(
        security_id="AAPL",
        field="net_income",
        fiscal_period="2022Q4",
        value=30000000000.0,
        unit="USD",
        filed_at="2023-01-15T00:00:00Z",
        available_at="2023-01-16T09:00:00Z",
        source="sec_edgar",
        retrieval_time="2023-01-16T10:00:00Z",
    )
    assert fact.field == "net_income"
    assert fact.value == 30000000000.0
    assert fact.available_at == "2023-01-16T09:00:00Z"


def test_as_of_query_excludes_future_observations():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        csv_path = workspace / "data_with_pit.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume,available_at\n"
            "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,2023-01-01T16:00:00Z\n"
            "AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,2023-01-02T16:00:00Z\n"
            "AAPL,2023-01-03,157.0,160.0,156.0,159.0,1100000,2023-01-03T16:00:00Z\n",
            encoding="utf-8",
        )

        request = IngestionRequest(
            source="test_src", file_path=csv_path, retrieval_time="2023-01-04T00:00:00Z"
        )
        version = store.ingest(request)
        assert store.coverage(version.id).has_temporal_provenance is True

        # The later-eligible bar must not appear in the earlier as-of query.
        bars = store.history(version.id, as_of="2023-01-02T18:00:00Z")
        assert len(bars) == 2
        dates = [b.session_date for b in bars]
        assert dates == ["2023-01-01", "2023-01-02"]

        # Query as-of 2023-01-01T12:00:00Z should return 0 bars
        bars_early = store.history(version.id, as_of="2023-01-01T12:00:00Z")
        assert len(bars_early) == 0


def test_data_lacking_temporal_provenance_rejected_from_historical_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        # CSV without available_at column
        csv_path = workspace / "data_no_pit.csv"
        csv_path.write_text(
            "symbol,date,open,high,low,close,volume\n"
            "AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000\n",
            encoding="utf-8",
        )

        request = IngestionRequest(
            source="no_pit_src", file_path=csv_path, retrieval_time="2023-01-02T00:00:00Z"
        )
        version = store.ingest(request)
        assert store.coverage(version.id).has_temporal_provenance is False

        # Querying with as_of specified must raise InadequateTemporalProvenanceError
        with pytest.raises(
            InadequateTemporalProvenanceError,
            match="Market observations lack required point-in-time eligibility timestamps",
        ):
            store.history(version.id, as_of="2023-01-01T18:00:00Z")

        # Querying with as_of=None should succeed (for current research per DATA-009)
        bars_all = store.history(version.id, as_of=None)
        assert len(bars_all) == 1
        assert bars_all[0].security_id == "AAPL"


def test_synthetic_dataset_later_observations_do_not_alter_earlier_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        t1 = "2023-01-01T16:00:00Z"
        t2 = "2023-01-02T16:00:00Z"

        # Version 1 (T1 data)
        csv_v1 = workspace / "v1.csv"
        csv_v1.write_text(
            "symbol,date,open,high,low,close,volume,available_at\n"
            f"AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,{t1}\n",
            encoding="utf-8",
        )
        req_v1 = IngestionRequest(source="src", file_path=csv_v1, retrieval_time=t1)
        v1 = store.ingest(req_v1)

        query_v1_at_t1 = store.history(v1.id, as_of=t1)

        # Version 2 (T1 + T2 data)
        csv_v2 = workspace / "v2.csv"
        csv_v2.write_text(
            "symbol,date,open,high,low,close,volume,available_at\n"
            f"AAPL,2023-01-01,150.0,155.0,149.0,154.0,1000000,{t1}\n"
            f"AAPL,2023-01-02,154.0,158.0,153.0,157.0,1200000,{t2}\n",
            encoding="utf-8",
        )
        req_v2 = IngestionRequest(source="src", file_path=csv_v2, retrieval_time=t1)
        v2 = store.ingest(req_v2)

        query_v2_at_t1 = store.history(v2.id, as_of=t1)

        assert query_v1_at_t1 == query_v2_at_t1


def test_fundamentals_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = MarketDataStore(workspace)

        csv_path = workspace / "fundamentals.csv"
        csv_path.write_text(
            "security_id,field,fiscal_period,value,unit,filed_at,available_at\n"
            "AAPL,net_income,2022Q4,30000000000,USD,2023-01-15T00:00:00Z,2023-01-16T09:00:00Z\n"
            "AAPL,net_income,2023Q1,24000000000,USD,2023-04-15T00:00:00Z,2023-04-16T09:00:00Z\n",
            encoding="utf-8",
        )

        request = IngestionRequest(
            source="sec_edgar", file_path=csv_path, retrieval_time="2023-04-16T10:00:00Z"
        )
        version = store.ingest(request)
        assert store.coverage(version.id).has_temporal_provenance is True

        # Query as-of 2023-02-01 should return Q4 2022 only
        facts = store.fundamentals(version.id, as_of="2023-02-01T00:00:00Z")
        assert len(facts) == 1
        assert facts[0].fiscal_period == "2022Q4"
        assert facts[0].value == 30000000000.0

        # Query as-of None should return both
        all_facts = store.fundamentals(version.id, as_of=None)
        assert len(all_facts) == 2
