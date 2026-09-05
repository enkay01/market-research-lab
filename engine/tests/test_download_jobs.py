"""Unit tests for ProgressRecorder and MarketDataDownloadService."""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from market_research_lab.download_jobs import (
    ActiveDownloadConflictError,
    CancellationToken,
    DatasetDownloadSpec,
    DownloadCannotBeCancelledError,
    DownloadPhase,
    DownloadState,
    MarketDataDownloadService,
    ProgressRecorder,
)
from market_research_lab.providers import (
    AlpacaCredentials,
    MassiveCredentials,
    ProviderCredentials,
)


def _dummy_credentials() -> ProviderCredentials:
    return ProviderCredentials(
        tiingo_api_token="test-tiingo",
        sec_edgar_user_agent="Test user@example.com",
        alpaca=AlpacaCredentials(api_key="test-alpaca-key", api_secret="test-alpaca-secret"),
        massive=MassiveCredentials(api_key="test-massive"),
    )


def _dummy_spec() -> DatasetDownloadSpec:
    return DatasetDownloadSpec(
        security_list_id="us-sector-index-etfs",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        downloads=(),
    )


def test_progress_recorder_write_budget_and_forced_writes(tmp_path: Path):
    run_dir = tmp_path / "test-run"
    recorder = ProgressRecorder(
        download_id="test-run",
        storage_dir=run_dir,
        security_list_id="us-sector-index-etfs",
        write_interval_seconds=0.25,
    )

    # Initial write was forced on instantiation
    assert recorder.disk_write_count == 1

    # Rapid non-forced updates within 0.25s budget should be throttled
    now = time.monotonic()
    recorder.clock = lambda: now + 0.05
    recorder.record_progress(completed_logical_units=1)
    recorder.record_progress(completed_logical_units=2)
    recorder.record_progress(completed_logical_units=3)
    assert recorder.disk_write_count == 1

    # An update after interval has elapsed triggers 1 disk write
    recorder.clock = lambda: now + 0.30
    recorder.record_progress(completed_logical_units=4)
    assert recorder.disk_write_count == 2

    # Phase transition forces immediate disk write
    recorder.transition_phase(DownloadPhase.FETCHING, message="Starting fetch")
    assert recorder.disk_write_count == 3

    # Finish success forces immediate disk write
    recorder.finish_success(dataset_version_id="version-123")
    assert recorder.disk_write_count == 4

    # Verify persisted status.json matches snapshot
    snap = ProgressRecorder.read_snapshot(run_dir)
    assert snap.state == DownloadState.SUCCEEDED
    assert snap.phase == DownloadPhase.COMPLETE
    assert snap.dataset_version_id == "version-123"
    assert snap.completed_logical_units == 4


def test_persisted_snapshot_validation_rejects_corrupted_json(tmp_path: Path):
    """CORE-003: Validation at the file boundary."""
    run_dir = tmp_path / "corrupt-run"
    run_dir.mkdir()
    payload = '{"download_id": "run-x", "state": "invalid_state"}'
    (run_dir / "status.json").write_text(payload, encoding="utf-8")

    with pytest.raises(ValidationError):
        ProgressRecorder.read_snapshot(run_dir)


def test_service_recovery_on_startup(tmp_path: Path):
    runs_dir = tmp_path / "download-runs"
    runs_dir.mkdir()

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
                "updated_at": "2024-01-01T00:00:00Z",
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

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
    )

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
    unblock = CancellationToken()

    def dummy_runner(
        spec: DatasetDownloadSpec, recorder: ProgressRecorder, token: CancellationToken
    ) -> None:
        recorder.transition_phase(DownloadPhase.FETCHING)
        while not unblock.is_cancelled and not token.is_cancelled:
            time.sleep(0.01)

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
        job_executor=dummy_runner,
    )

    spec = _dummy_spec()
    service.start(spec)

    # Second start while first is active should raise conflict
    with pytest.raises(ActiveDownloadConflictError):
        service.start(spec)

    unblock.cancel()
    service.shutdown()


def test_service_cancellation_flow(tmp_path: Path):
    started = CancellationToken()
    unblock = CancellationToken()

    def dummy_runner(
        spec: DatasetDownloadSpec, recorder: ProgressRecorder, token: CancellationToken
    ) -> None:
        recorder.transition_phase(DownloadPhase.FETCHING)
        started.cancel()
        while not unblock.is_cancelled and not token.is_cancelled:
            time.sleep(0.01)
        if token.is_cancelled:
            recorder.finish_cancelled(message="Cancelled by user")
        else:
            recorder.finish_success()

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
        job_executor=dummy_runner,
    )

    spec = _dummy_spec()
    download_id = service.start(spec)

    # Wait until running
    while not started.is_cancelled:
        time.sleep(0.01)

    snap = service.cancel(download_id)
    assert snap.state in (DownloadState.CANCELLING, DownloadState.CANCELLED)

    unblock.cancel()
    service.shutdown()


def test_service_cannot_cancel_during_publishing(tmp_path: Path):
    def dummy_runner(
        spec: DatasetDownloadSpec, recorder: ProgressRecorder, token: CancellationToken
    ) -> None:
        recorder.transition_phase(DownloadPhase.PUBLISHING)
        time.sleep(0.05)
        recorder.finish_success()

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
        job_executor=dummy_runner,
    )

    spec = _dummy_spec()
    download_id = service.start(spec)

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
    cancelled_event = CancellationToken()

    def dummy_runner(
        spec: DatasetDownloadSpec, recorder: ProgressRecorder, token: CancellationToken
    ) -> None:
        recorder.transition_phase(DownloadPhase.FETCHING)
        while not token.is_cancelled:
            time.sleep(0.01)
        cancelled_event.cancel()
        recorder.finish_cancelled(message="Shutdown requested")

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
        job_executor=dummy_runner,
    )

    spec = _dummy_spec()
    download_id = service.start(spec)

    time.sleep(0.05)
    service.shutdown(wait=True, timeout=2.0)

    assert cancelled_event.is_cancelled
    snap = service.get(download_id)
    assert snap.state == DownloadState.CANCELLED


def test_service_preserves_error_traceback_on_failure(tmp_path: Path):
    """CORE-008: Preservation of error and traceback on unexpected failure."""
    def faulty_runner(
        spec: DatasetDownloadSpec, recorder: ProgressRecorder, token: CancellationToken
    ) -> None:
        raise RuntimeError("Unexpected simulated database explosion!")

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
        job_executor=faulty_runner,
    )

    spec = _dummy_spec()
    download_id = service.start(spec)

    time.sleep(0.05)
    service.shutdown(wait=True, timeout=2.0)

    snap = service.get(download_id)
    assert snap.state == DownloadState.FAILED
    assert "simulated database explosion" in (snap.error_message or "")
    
    # Check that traceback was preserved in event details
    assert len(snap.recent_events) > 0
    failure_event = [e for e in snap.recent_events if "traceback" in e.details]
    assert len(failure_event) == 1
    assert "faulty_runner" in str(failure_event[0].details["traceback"])


def test_service_shutdown_timeout_does_not_hang(tmp_path: Path):
    """Spec P1: shutdown timeout enforcement."""
    unblock = CancellationToken()

    def hanging_runner(
        spec: DatasetDownloadSpec, recorder: ProgressRecorder, token: CancellationToken
    ) -> None:
        # Ignore cancellation and simulate a stuck network call
        while not unblock.is_cancelled:
            time.sleep(0.02)

    mock_store = MagicMock()
    service = MarketDataDownloadService(
        workspace_root=tmp_path,
        market_store=mock_store,
        credentials=_dummy_credentials(),
        job_executor=hanging_runner,
    )

    try:
        spec = _dummy_spec()
        service.start(spec)
        time.sleep(0.05)

        start_time = time.monotonic()
        # Should enforce timeout=0.1s rather than blocking indefinitely
        service.shutdown(wait=True, timeout=0.1)
        elapsed = time.monotonic() - start_time

        assert elapsed < 1.0, f"Shutdown took too long: {elapsed:.2f}s"
    finally:
        unblock.cancel()
