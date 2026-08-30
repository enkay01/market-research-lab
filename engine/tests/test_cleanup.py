"""Deletion checks for Project Runs and shared Dataset Versions."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_research_lab.market_data import (
    DatasetVersionNotFoundError,
    IngestionRequest,
    MarketDataStore,
)
from market_research_lab.projects import ProjectStore, RunNotFoundError


def _ingest_daily_bars(store: MarketDataStore, workspace: Path) -> tuple[str, Path]:
    source_file = workspace / "bars.csv"
    source_file.write_text(
        "symbol,date,open,high,low,close,volume\n"
        "AAPL,2024-01-02,100,101,99,100.5,1000\n",
        encoding="utf-8",
    )
    version = store.ingest(
        IngestionRequest(
            source="cleanup-test",
            file_path=source_file,
            retrieval_time="2024-01-03T00:00:00Z",
        )
    )
    parquet_file = store.datasets_dir / version.files[0]
    return version.id, parquet_file


def test_project_run_can_be_listed_and_deleted(tmp_path: Path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Cleanup test")
    run_id = store.create_run(project.id, dataset_version_ids=["dataset-v1"])

    summaries = store.list_run_summaries(project.id)

    assert summaries[0].id == run_id
    assert summaries[0].status == "pending"
    assert summaries[0].dataset_version_ids == ["dataset-v1"]

    run_directory = tmp_path / "projects" / project.id / "runs" / run_id
    (run_directory / "artifacts" / "generated.json").write_text("{}", encoding="utf-8")
    store.delete_run(project.id, run_id)

    assert not run_directory.exists()
    assert store.list_run_summaries(project.id) == []
    with pytest.raises(RunNotFoundError):
        store.delete_run(project.id, run_id)


def test_project_store_finds_run_dataset_references(tmp_path: Path):
    store = ProjectStore(tmp_path)
    first = store.create_project("First project")
    second = store.create_project("Second project")
    first_run = store.create_run(first.id, dataset_version_ids=["dataset-v1"])
    store.create_run(second.id, dataset_version_ids=["dataset-v2"])

    references = store.find_runs_referencing_dataset("dataset-v1")

    assert references == [
        {
            "project_id": first.id,
            "project_name": first.name,
            "run_id": first_run,
            "kind": "unknown",
            "status": "pending",
        }
    ]


def test_dataset_version_deletion_removes_catalogue_record_and_file(tmp_path: Path):
    store = MarketDataStore(tmp_path)
    dataset_version_id, parquet_file = _ingest_daily_bars(store, tmp_path)

    store.delete_dataset_version(dataset_version_id)

    assert store.list_dataset_versions() == []
    assert not parquet_file.exists()
    with pytest.raises(DatasetVersionNotFoundError):
        store.delete_dataset_version(dataset_version_id)


def test_bulk_delete_datasets_and_runs(tmp_path: Path):
    market_store = MarketDataStore(tmp_path)
    project_store = ProjectStore(tmp_path)

    v1, p1 = _ingest_daily_bars(market_store, tmp_path)
    # create second file
    f2 = tmp_path / "bars2.csv"
    f2.write_text("symbol,date,open,high,low,close,volume\nMSFT,2024-01-02,200,201,199,200.5,1000\n", encoding="utf-8")
    v2_obj = market_store.ingest(IngestionRequest(source="cleanup-test-2", file_path=f2, retrieval_time="2024-01-03T00:00:00Z"))
    v2 = v2_obj.id
    p2 = market_store.datasets_dir / v2_obj.files[0]

    assert p1.exists() and p2.exists()
    assert len(market_store.list_dataset_versions()) == 2

    deleted_versions = market_store.bulk_delete_dataset_versions([v1, v2])
    assert set(deleted_versions) == {v1, v2}
    assert market_store.list_dataset_versions() == []
    assert not p1.exists()
    assert not p2.exists()

    # Test bulk delete runs
    project = project_store.create_project("Bulk Runs Test")
    r1 = project_store.create_run(project.id, dataset_version_ids=["v1"])
    r2 = project_store.create_run(project.id, dataset_version_ids=["v2"])
    assert len(project_store.list_run_summaries(project.id)) == 2

    deleted_runs = project_store.bulk_delete_runs(project.id, [r1, r2])
    assert set(deleted_runs) == {r1, r2}
    assert project_store.list_run_summaries(project.id) == []
