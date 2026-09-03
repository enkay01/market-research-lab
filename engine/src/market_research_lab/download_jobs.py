"""Download job lifecycle, bounded progress persistence, and background execution service."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from .json_types import JsonValue

logger = logging.getLogger(__name__)


class DownloadState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (
            DownloadState.SUCCEEDED,
            DownloadState.FAILED,
            DownloadState.CANCELLED,
        )


class DownloadPhase(str, Enum):
    PLANNING = "planning"
    FETCHING = "fetching"
    VALIDATING = "validating"
    STAGING = "staging"
    PUBLISHING = "publishing"
    COMPLETE = "complete"


class ActiveDownloadConflictError(Exception):
    """Raised when a download is started while another download is already in progress."""

    def __init__(self, active_download_id: str) -> None:
        super().__init__(f"Download '{active_download_id}' is currently running.")
        self.active_download_id = active_download_id


class DownloadNotFoundError(Exception):
    """Raised when a requested download_id does not exist."""

    def __init__(self, download_id: str) -> None:
        super().__init__(f"Download '{download_id}' was not found.")
        self.download_id = download_id


class DownloadCannotBeCancelledError(Exception):
    """Raised when a download cannot be cancelled because it is publishing or already complete."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CancellationToken:
    """Thread-safe cancellation token."""

    def __init__(self) -> None:
        self._is_cancelled = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled


@dataclass(frozen=True)
class DownloadEvent:
    timestamp: str
    phase: str
    message: str
    details: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "timestamp": self.timestamp,
            "phase": self.phase,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class DownloadSnapshot:
    download_id: str
    state: DownloadState
    phase: DownloadPhase
    started_at: str
    updated_at: str
    dataset_version_id: str | None = None
    security_list_id: str | None = None
    error_message: str | None = None
    total_logical_units: int = 0
    completed_logical_units: int = 0
    total_requests: int = 0
    completed_requests: int = 0
    active_provider: str | None = None
    active_operation: str | None = None
    rate_limit_wait_seconds: float = 0.0
    recent_events: list[DownloadEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "download_id": self.download_id,
            "state": self.state.value,
            "phase": self.phase.value,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "dataset_version_id": self.dataset_version_id,
            "security_list_id": self.security_list_id,
            "error_message": self.error_message,
            "total_logical_units": self.total_logical_units,
            "completed_logical_units": self.completed_logical_units,
            "total_requests": self.total_requests,
            "completed_requests": self.completed_requests,
            "active_provider": self.active_provider,
            "active_operation": self.active_operation,
            "rate_limit_wait_seconds": self.rate_limit_wait_seconds,
            "recent_events": [e.to_dict() for e in self.recent_events],
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], events: list[DownloadEvent] | None = None
    ) -> DownloadSnapshot:
        raw_events = events or [
            DownloadEvent(
                timestamp=e["timestamp"],
                phase=e["phase"],
                message=e["message"],
                details=e.get("details", {}),
            )
            for e in data.get("recent_events", [])
        ]
        return cls(
            download_id=data["download_id"],
            state=DownloadState(data["state"]),
            phase=DownloadPhase(data["phase"]),
            started_at=data["started_at"],
            updated_at=data["updated_at"],
            dataset_version_id=data.get("dataset_version_id"),
            security_list_id=data.get("security_list_id"),
            error_message=data.get("error_message"),
            total_logical_units=data.get("total_logical_units", 0),
            completed_logical_units=data.get("completed_logical_units", 0),
            total_requests=data.get("total_requests", 0),
            completed_requests=data.get("completed_requests", 0),
            active_provider=data.get("active_provider"),
            active_operation=data.get("active_operation"),
            rate_limit_wait_seconds=data.get("rate_limit_wait_seconds", 0.0),
            recent_events=raw_events,
        )


class ProgressRecorder:
    """Thread-safe recorder managing bounded persistence writes and recent events."""

    def __init__(
        self,
        download_id: str,
        storage_dir: Path,
        min_write_interval_seconds: float = 0.25,
        security_list_id: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.download_id = download_id
        self.storage_dir = storage_dir
        self.min_write_interval_seconds = min_write_interval_seconds
        self.clock = clock
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        now_iso = datetime.now(UTC).isoformat()
        self._started_at = now_iso
        self._updated_at = now_iso
        self._state = DownloadState.QUEUED
        self._phase = DownloadPhase.PLANNING
        self._dataset_version_id: str | None = None
        self._security_list_id: str | None = security_list_id
        self._error_message: str | None = None
        self._total_logical_units = 0
        self._completed_logical_units = 0
        self._total_requests = 0
        self._completed_requests = 0
        self._active_provider: str | None = None
        self._active_operation: str | None = None
        self._rate_limit_wait_seconds = 0.0

        self._events: deque[DownloadEvent] = deque(maxlen=200)
        self._last_disk_write_time: float = 0.0
        self.disk_write_count: int = 0

        self._append_event_unlocked("queued", "Download queued for execution.")
        self._persist_unlocked(force=True)

    def _append_event_unlocked(
        self, phase: str, message: str, details: dict[str, JsonValue] | None = None
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()
        event = DownloadEvent(
            timestamp=now_iso,
            phase=phase,
            message=message,
            details=details or {},
        )
        self._events.append(event)
        self._updated_at = now_iso
        events_file = self.storage_dir / "events.jsonl"
        with events_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def _persist_unlocked(self, force: bool = False) -> None:
        now = self.clock()
        if not force and (now - self._last_disk_write_time < self.min_write_interval_seconds):
            return

        snapshot_data = {
            "download_id": self.download_id,
            "state": self._state.value,
            "phase": self._phase.value,
            "started_at": self._started_at,
            "updated_at": self._updated_at,
            "dataset_version_id": self._dataset_version_id,
            "security_list_id": self._security_list_id,
            "error_message": self._error_message,
            "total_logical_units": self._total_logical_units,
            "completed_logical_units": self._completed_logical_units,
            "total_requests": self._total_requests,
            "completed_requests": self._completed_requests,
            "active_provider": self._active_provider,
            "active_operation": self._active_operation,
            "rate_limit_wait_seconds": self._rate_limit_wait_seconds,
        }

        status_file = self.storage_dir / "status.json"
        tmp_file = self.storage_dir / f"status.{uuid4().hex}.tmp"
        with tmp_file.open("w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)
        tmp_file.replace(status_file)

        self._last_disk_write_time = now
        self.disk_write_count += 1

    def transition_phase(
        self,
        phase: DownloadPhase,
        message: str | None = None,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        with self._lock:
            self._phase = phase
            if self._state == DownloadState.QUEUED and phase != DownloadPhase.PLANNING:
                self._state = DownloadState.RUNNING
            msg = message or f"Entered {phase.value} phase."
            self._append_event_unlocked(phase.value, msg, details)
            self._persist_unlocked(force=True)

    def record_progress(
        self,
        *,
        total_logical_units: int | None = None,
        completed_logical_units: int | None = None,
        total_requests: int | None = None,
        completed_requests: int | None = None,
        active_provider: str | None = None,
        active_operation: str | None = None,
        rate_limit_wait_seconds: float | None = None,
        message: str | None = None,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        with self._lock:
            if total_logical_units is not None:
                self._total_logical_units = total_logical_units
            if completed_logical_units is not None:
                self._completed_logical_units = completed_logical_units
            if total_requests is not None:
                self._total_requests = total_requests
            if completed_requests is not None:
                self._completed_requests = completed_requests
            if active_provider is not None:
                self._active_provider = active_provider
            if active_operation is not None:
                self._active_operation = active_operation
            if rate_limit_wait_seconds is not None:
                self._rate_limit_wait_seconds = rate_limit_wait_seconds

            if message:
                self._append_event_unlocked(self._phase.value, message, details)
            self._persist_unlocked(force=False)

    def finish_success(
        self,
        dataset_version_id: str | None = None,
        message: str = "Download completed successfully.",
    ) -> None:
        with self._lock:
            self._state = DownloadState.SUCCEEDED
            self._phase = DownloadPhase.COMPLETE
            if dataset_version_id:
                self._dataset_version_id = dataset_version_id
            self._append_event_unlocked(DownloadPhase.COMPLETE.value, message)
            self._persist_unlocked(force=True)

    def finish_failed(self, error_message: str) -> None:
        with self._lock:
            self._state = DownloadState.FAILED
            self._error_message = error_message
            self._append_event_unlocked(
                self._phase.value, f"Download failed: {error_message}"
            )
            self._persist_unlocked(force=True)

    def finish_cancelled(self, message: str = "Download was cancelled.") -> None:
        with self._lock:
            self._state = DownloadState.CANCELLED
            self._append_event_unlocked(self._phase.value, message)
            self._persist_unlocked(force=True)

    def set_cancelling(self) -> None:
        with self._lock:
            self._state = DownloadState.CANCELLING
            self._append_event_unlocked(self._phase.value, "Cancellation requested.")
            self._persist_unlocked(force=True)

    def snapshot(self) -> DownloadSnapshot:
        with self._lock:
            return DownloadSnapshot(
                download_id=self.download_id,
                state=self._state,
                phase=self._phase,
                started_at=self._started_at,
                updated_at=self._updated_at,
                dataset_version_id=self._dataset_version_id,
                security_list_id=self._security_list_id,
                error_message=self._error_message,
                total_logical_units=self._total_logical_units,
                completed_logical_units=self._completed_logical_units,
                total_requests=self._total_requests,
                completed_requests=self._completed_requests,
                active_provider=self._active_provider,
                active_operation=self._active_operation,
                rate_limit_wait_seconds=self._rate_limit_wait_seconds,
                recent_events=list(self._events),
            )


class MarketDataDownloadService:
    """Service managing background download worker threads and progress persistence."""

    def __init__(
        self,
        workspace_root: Path,
        market_store: Any | None = None,
        credentials: Any | None = None,
        fetch_json: Any | None = None,
        wait: Callable[[float], None] | None = None,
        executor: ThreadPoolExecutor | None = None,
        app_state: Any | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.market_store = market_store
        self.credentials = credentials
        self.fetch_json = fetch_json
        self._wait = wait
        self.app_state = app_state
        self.runs_dir = workspace_root / "download-runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="download-worker"
        )
        self._lock = threading.Lock()
        self._active_job: tuple[str, ProgressRecorder, CancellationToken, Future[Any]] | None = None

        self._recover_incomplete_runs()

    @property
    def wait(self) -> Callable[[float], None]:
        if self._wait is not None:
            return self._wait
        if (
            self.app_state is not None
            and getattr(self.app_state, "provider_wait", None) is not None
        ):
            return self.app_state.provider_wait
        return time.sleep

    @wait.setter
    def wait(self, fn: Callable[[float], None] | None) -> None:
        self._wait = fn

    def _recover_incomplete_runs(self) -> None:
        """Startup check: mark any non-terminal runs from previous runs as failed."""
        if not self.runs_dir.exists():
            return
        for run_dir in self.runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            status_file = run_dir / "status.json"
            if not status_file.exists():
                continue
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                state = DownloadState(data["state"])
                if not state.is_terminal:
                    data["state"] = DownloadState.FAILED.value
                    data["error_message"] = (
                        "Process was terminated unexpectedly before completion."
                    )
                    data["updated_at"] = datetime.now(UTC).isoformat()
                    tmp_file = run_dir / f"status.{uuid4().hex}.tmp"
                    with tmp_file.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    tmp_file.replace(status_file)
            except Exception as err:
                logger.warning("Failed to recover run status for %s: %s", run_dir.name, err)

    def start(self, spec: Any) -> str:
        """Start a new background download job."""
        with self._lock:
            if self._active_job is not None:
                _, _, _, future = self._active_job
                if not future.done():
                    raise ActiveDownloadConflictError(self._active_job[0])

            download_id = f"dl-{uuid4().hex[:12]}"
            run_dir = self.runs_dir / download_id
            raw_sec_id = getattr(spec, "security_list_id", None)
            security_list_id = str(raw_sec_id) if isinstance(raw_sec_id, str) else None
            recorder = ProgressRecorder(
                download_id=download_id,
                storage_dir=run_dir,
                security_list_id=security_list_id,
            )
            token = CancellationToken()

            future = self._executor.submit(
                self._run_job_wrapper, download_id, spec, recorder, token
            )
            self._active_job = (download_id, recorder, token, future)
            return download_id

    def _run_job_wrapper(
        self,
        download_id: str,
        spec: Any,
        recorder: ProgressRecorder,
        token: CancellationToken,
    ) -> None:
        try:
            self._execute_job(spec, recorder, token)
        except Exception as error:
            if token.is_cancelled:
                recorder.finish_cancelled(f"Download cancelled: {error}")
            else:
                recorder.finish_failed(str(error))
        finally:
            with self._lock:
                if self._active_job and self._active_job[0] == download_id:
                    pass  # Keep reference so get() / latest() works seamlessly

    def _execute_job(
        self,
        spec: Any,
        recorder: ProgressRecorder,
        token: CancellationToken,
    ) -> None:
        """Hook method executing download_composite."""
        from .downloads import CompositeDownloadContext, download_composite

        if not self.market_store:
            raise NotImplementedError(
                "Job execution hook not provided and market_store is missing."
            )

        creds = self.credentials
        if creds is None:
            from .configuration import load_provider_credentials
            creds = load_provider_credentials()

        context = CompositeDownloadContext(
            credentials=creds,
            fetch_json=self.fetch_json,
            wait=self.wait,
            recorder=recorder,
            token=token,
        )
        download_composite(self.market_store, spec, context)

    def get(self, download_id: str) -> DownloadSnapshot:
        """Retrieve the current or historical snapshot for a download ID."""
        with self._lock:
            if self._active_job and self._active_job[0] == download_id:
                return self._active_job[1].snapshot()

        run_dir = self.runs_dir / download_id
        status_file = run_dir / "status.json"
        if not status_file.exists():
            raise DownloadNotFoundError(download_id)

        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            events: list[DownloadEvent] = []
            events_file = run_dir / "events.jsonl"
            if events_file.exists():
                lines = events_file.read_text(encoding="utf-8").strip().splitlines()
                for line in lines[-200:]:
                    if line.strip():
                        e = json.loads(line)
                        events.append(
                            DownloadEvent(
                                timestamp=e["timestamp"],
                                phase=e["phase"],
                                message=e["message"],
                                details=e.get("details", {}),
                            )
                        )
            return DownloadSnapshot.from_dict(data, events=events)
        except Exception as err:
            raise DownloadNotFoundError(download_id) from err

    def latest(self) -> DownloadSnapshot | None:
        """Retrieve snapshot of active or most recent historical download."""
        with self._lock:
            if self._active_job:
                return self._active_job[1].snapshot()

        if not self.runs_dir.exists():
            return None

        candidates: list[Path] = [
            p for p in self.runs_dir.iterdir() if p.is_dir() and (p / "status.json").exists()
        ]
        if not candidates:
            return None

        # Sort by status.json modification time descending
        candidates.sort(key=lambda p: (p / "status.json").stat().st_mtime, reverse=True)
        return self.get(candidates[0].name)

    def cancel(self, download_id: str) -> DownloadSnapshot:
        """Cancel an in-flight download."""
        with self._lock:
            if not self._active_job or self._active_job[0] != download_id:
                raise DownloadCannotBeCancelledError("Download is not currently active.")

            _, recorder, token, future = self._active_job
            snap = recorder.snapshot()
            if snap.phase == DownloadPhase.PUBLISHING:
                raise DownloadCannotBeCancelledError(
                    "Download is publishing to dataset storage and cannot be cancelled."
                )
            if snap.state.is_terminal:
                raise DownloadCannotBeCancelledError("Download has already finished.")

            token.cancel()
            recorder.set_cancelling()
            return recorder.snapshot()

    def shutdown(self, wait: bool = True, timeout: float = 5.0) -> None:
        """Gracefully shut down background workers and signal cancellation."""
        with self._lock:
            if self._active_job:
                _, recorder, token, future = self._active_job
                token.cancel()
                if not future.done():
                    recorder.set_cancelling()

        self._executor.shutdown(wait=wait, cancel_futures=True)
