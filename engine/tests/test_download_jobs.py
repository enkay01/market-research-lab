"""Contract and unit tests for download lifecycle, progress service, and concurrency."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from market_research_lab.download_jobs import (
    ActiveDownloadConflictError,
    CancellationToken,
    DownloadCannotBeCancelledError,
    DownloadPhase,
    DownloadState,
    MarketDataDownloadService,
    ProgressRecorder,
)


def test_progress_recorder_write_budget_and_forced_writes(tmp_path: Path):
    run_dir = tmp_path / "test-run"
    recorder = ProgressRecorder(
        download_id="test-run",
        storage_dir=run_dir,
        min_write_interval_seconds=0.25,
    )

    # 1. Phase transition forces write
    recorder.transition_phase(DownloadPhase.FETCHING, message="Starting fetch")
    assert (run_dir / "status.json").exists()
    status1 = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status1["phase"] == "fetching"

    # 2. Rapid progress events within 250ms write budget
    # Modify mtime to track writes
    initial_write_count = recorder.disk_write_count
    for i in range(10):
        recorder.record_progress(completed_requests=i, message=f"Fetched item {i}")

    # Should not write to disk 10 times
    assert recorder.disk_write_count <= initial_write_count + 1

    # 3. Terminal state forces write immediately
    recorder.finish_success(message="Completed successfully")
    status_final = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status_final["state"] == "succeeded"
    assert status_final["phase"] == "complete"

    # 4. Check events.jsonl
    events_file = run_dir / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 12


def test_progress_recorder_event_buffer_capped_at_200(tmp_path: Path):
    run_dir = tmp_path / "test-buffer"
    recorder = ProgressRecorder(download_id="test-buffer", storage_dir=run_dir)

    for i in range(250):
        recorder.record_progress(completed_requests=i, message=f"Item {i}")

    snapshot = recorder.snapshot()
    assert len(snapshot.recent_events) == 200
    assert snapshot.recent_events[-1].message == "Item 249"
    assert snapshot.recent_events[0].message == "Item 50"


def test_startup_recovery_marks_incomplete_runs_failed(tmp_path: Path):
    runs_dir = tmp_path / "download-runs"
    runs_dir.mkdir(parents=True)

    # Incomplete run 1: running
    run1 = runs_dir / "run-1"
    run1.mkdir()
    (run1 / "status.json").write_text(
        json.dumps(
            {
                "download_id": "run-1",
                "state": "running",
                "phase": "fetching",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "total_logical_units": 10,
                "completed_logical_units": 2,
            }
        ),
        encoding="utf-8",
    )

    # Incomplete run 2: queued
    run2 = runs_dir / "run-2"
    run2.mkdir()
    (run2 / "status.json").write_text(
        json.dumps(
            {
                "download_id": "run-2",
                "state": "queued",
                "phase": "planning",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    # Complete run 3: succeeded
    run3 = runs_dir / "run-3"
    run3.mkdir()
    (run3 / "status.json").write_text(
        json.dumps(
            {
                "download_id": "run-3",
                "state": "succeeded",
                "phase": "complete",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:05:00Z",
            }
        ),
        encoding="utf-8",
    )

    service = MarketDataDownloadService(workspace_root=tmp_path)

    # Startup recovery should have converted run-1 and run-2 to failed
    snap1 = service.get("run-1")
    assert snap1.state == DownloadState.FAILED
    assert snap1.error_message is not None

    snap2 = service.get("run-2")
    assert snap2.state == DownloadState.FAILED

    snap3 = service.get("run-3")
    assert snap3.state == DownloadState.SUCCEEDED
    service.shutdown()


def test_service_enforces_single_active_download(tmp_path: Path):
    service = MarketDataDownloadService(workspace_root=tmp_path)

    # Mock runner that hangs until released
    unblock = CancellationToken()

    def dummy_runner(spec: Any, recorder: ProgressRecorder, token: CancellationToken):
        recorder.transition_phase(DownloadPhase.FETCHING)
        while not unblock.is_cancelled and not token.is_cancelled:
            time.sleep(0.01)

    service._execute_job = dummy_runner  # type: ignore

    mock_spec = MagicMock()
    service.start(mock_spec)

    # Second start while first is active should raise conflict
    with pytest.raises(ActiveDownloadConflictError):
        service.start(mock_spec)

    unblock.cancel()
    service.shutdown()


def test_service_cancellation_flow(tmp_path: Path):
    service = MarketDataDownloadService(workspace_root=tmp_path)

    started = CancellationToken()
    unblock = CancellationToken()

    def dummy_runner(spec: Any, recorder: ProgressRecorder, token: CancellationToken):
        recorder.transition_phase(DownloadPhase.FETCHING)
        started.cancel()
        while not unblock.is_cancelled and not token.is_cancelled:
            time.sleep(0.01)
        if token.is_cancelled:
            recorder.finish_cancelled(message="Cancelled by user")
        else:
            recorder.finish_success()

    service._execute_job = dummy_runner  # type: ignore
    mock_spec = MagicMock()
    download_id = service.start(mock_spec)

    # Wait until running
    while not started.is_cancelled:
        time.sleep(0.01)

    snap = service.cancel(download_id)
    assert snap.state in (DownloadState.CANCELLING, DownloadState.CANCELLED)

    unblock.cancel()
    service.shutdown()


def test_service_cannot_cancel_during_publishing(tmp_path: Path):
    service = MarketDataDownloadService(workspace_root=tmp_path)

    def dummy_runner(spec: Any, recorder: ProgressRecorder, token: CancellationToken):
        recorder.transition_phase(DownloadPhase.PUBLISHING)
        time.sleep(0.05)
        recorder.finish_success()

    service._execute_job = dummy_runner  # type: ignore
    mock_spec = MagicMock()
    download_id = service.start(mock_spec)

    # Wait for publishing phase
    for _ in range(50):
        snap = service.get(download_id)
        if snap.phase == DownloadPhase.PUBLISHING:
            break
        time.sleep(0.01)

    with pytest.raises(DownloadCannotBeCancelledError):
        service.cancel(download_id)

    service.shutdown()


def test_service_shutdown_cancels_active_jobs(tmp_path: Path):
    service = MarketDataDownloadService(workspace_root=tmp_path)

    cancelled_event = CancellationToken()

    def dummy_runner(spec: Any, recorder: ProgressRecorder, token: CancellationToken):
        recorder.transition_phase(DownloadPhase.FETCHING)
        while not token.is_cancelled:
            time.sleep(0.01)
        cancelled_event.cancel()
        recorder.finish_cancelled(message="Shutdown requested")

    service._execute_job = dummy_runner  # type: ignore
    mock_spec = MagicMock()
    download_id = service.start(mock_spec)

    time.sleep(0.05)
    service.shutdown(wait=True, timeout=2.0)

    assert cancelled_event.is_cancelled
    snap = service.get(download_id)
    assert snap.state == DownloadState.CANCELLED
