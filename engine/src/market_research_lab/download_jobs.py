"""Download job lifecycle, bounded progress persistence, and background execution service."""

from __future__ import annotations

import json
import logging
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from .json_types import JsonValue
from .market_data import MarketDataStore
from .providers import ProviderCredentials
from .request_control import FileRequestResultCache
from .transport import JsonFetcherProtocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderDownloadChoice:
    provider: Literal["tiingo", "massive", "sec_edgar", "alpaca"]
    data_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetDownloadSpec:
    """Frozen parameter object for one composite dataset download operation."""

    security_list_id: str
    start_date: date
    end_date: date
    downloads: tuple[ProviderDownloadChoice, ...]


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
    """Thread-safe cancellation token backed by threading.Event."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._publication_started = False

    def cancel(self) -> bool:
        with self._lock:
            if self._publication_started:
                return False
            self._event.set()
            return True

    def begin_publication(self) -> bool:
        with self._lock:
            if self._event.is_set():
                return False
            self._publication_started = True
            return True

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait until cancelled or timeout expires. Returns True if cancelled."""
        return self._event.wait(timeout)


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


class PersistedDownloadEvent(BaseModel):
    timestamp: str
    phase: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class PersistedDownloadSnapshot(BaseModel):
    """Pydantic boundary model validating status files from disk."""

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
    recent_events: list[PersistedDownloadEvent] = Field(default_factory=list)

    def to_domain(self) -> DownloadSnapshot:
        return DownloadSnapshot(
            download_id=self.download_id,
            state=self.state,
            phase=self.phase,
            started_at=self.started_at,
            updated_at=self.updated_at,
            dataset_version_id=self.dataset_version_id,
            security_list_id=self.security_list_id,
            error_message=self.error_message,
            total_logical_units=self.total_logical_units,
            completed_logical_units=self.completed_logical_units,
            total_requests=self.total_requests,
            completed_requests=self.completed_requests,
            active_provider=self.active_provider,
            active_operation=self.active_operation,
            rate_limit_wait_seconds=self.rate_limit_wait_seconds,
            recent_events=[
                DownloadEvent(
                    timestamp=e.timestamp,
                    phase=e.phase,
                    message=e.message,
                    details=e.details,
                )
                for e in self.recent_events
            ],
        )


class ProgressRecorder:
    """Thread-safe recorder managing bounded disk persistence and in-memory progress."""

    def __init__(
        self,
        download_id: str,
        storage_dir: Path,
        security_list_id: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        write_interval_seconds: float = 0.25,  # <= 4 writes/second
    ) -> None:
        self.download_id = download_id
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.write_interval_seconds = write_interval_seconds

        self._lock = threading.Lock()
        self._state = DownloadState.QUEUED
        self._phase = DownloadPhase.PLANNING
        now_iso = datetime.now(UTC).isoformat()
        self._started_at = now_iso
        self._updated_at = now_iso
        self._dataset_version_id: str | None = None
        self._security_list_id: str | None = security_list_id
        self._error_message: str | None = None

        self._total_logical_units: int = 0
        self._completed_logical_units: int = 0
        self._total_requests: int = 0
        self._completed_requests: int = 0
        self._active_provider: str | None = None
        self._active_operation: str | None = None
        self._rate_limit_wait_seconds: float = 0.0

        self._events: deque[DownloadEvent] = deque(maxlen=200)
        self._last_disk_write_time: float = 0.0
        self.disk_write_count: int = 0

        # Initial forced write for queued state
        self._append_event_unlocked(
            self._phase.value,
            f"Download queued for security list: {security_list_id or 'unknown'}",
        )
        self._persist_unlocked(force=True)

    def _append_event_unlocked(
        self,
        phase: str,
        message: str,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        evt = DownloadEvent(
            timestamp=datetime.now(UTC).isoformat(),
            phase=phase,
            message=message,
            details=details or {},
        )
        self._events.append(evt)
        self._updated_at = evt.timestamp

    def _persist_unlocked(self, force: bool = False) -> None:
        now = self.clock()
        if not force and (now - self._last_disk_write_time < self.write_interval_seconds):
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
            "recent_events": [e.to_dict() for e in self._events],
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
            self._dataset_version_id = dataset_version_id
            self._phase = DownloadPhase.COMPLETE
            self._append_event_unlocked(self._phase.value, message)
            self._persist_unlocked(force=True)

    def finish_failed(
        self,
        error_message: str,
        message: str = "Download failed.",
        traceback: str | None = None,
    ) -> None:
        with self._lock:
            self._state = DownloadState.FAILED
            self._error_message = error_message
            self._phase = DownloadPhase.COMPLETE
            details: dict[str, JsonValue] = {"error": error_message}
            if traceback:
                details["traceback"] = traceback
            self._append_event_unlocked(self._phase.value, message, details)
            self._persist_unlocked(force=True)

    def finish_cancelled(self, message: str = "Download cancelled by user.") -> None:
        with self._lock:
            self._state = DownloadState.CANCELLED
            self._phase = DownloadPhase.COMPLETE
            self._append_event_unlocked(self._phase.value, message)
            self._persist_unlocked(force=True)

    def set_cancelling(self, message: str = "Cancellation requested.") -> None:
        with self._lock:
            if not self._state.is_terminal:
                self._state = DownloadState.CANCELLING
                self._append_event_unlocked(self._phase.value, message)
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

    @classmethod
    def read_snapshot(cls, run_dir: Path) -> DownloadSnapshot:
        """Validate and construct DownloadSnapshot from status.json (CORE-003)."""
        status_file = run_dir / "status.json"
        if not status_file.exists():
            raise FileNotFoundError(f"Status file not found in {run_dir}")
        raw_text = status_file.read_text(encoding="utf-8")
        persisted = PersistedDownloadSnapshot.model_validate_json(raw_text)
        return persisted.to_domain()


class MarketDataDownloadService:
    """Service managing background download worker threads and progress persistence."""

    def __init__(
        self,
        workspace_root: Path,
        market_store: MarketDataStore,
        credentials: ProviderCredentials,
        fetch_json: (
            JsonFetcherProtocol | Callable[[str, Mapping[str, str]], JsonValue] | None
        ) = None,
        wait: Callable[[float], None] = time.sleep,
        executor: ThreadPoolExecutor | None = None,
        job_executor: (
            Callable[[DatasetDownloadSpec, ProgressRecorder, CancellationToken], None] | None
        ) = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.market_store = market_store
        self.credentials = credentials
        self.fetch_json = fetch_json
        self.wait = wait
        self._job_executor = job_executor
        self.runs_dir = workspace_root / "download-runs"
        self.request_cache = FileRequestResultCache(workspace_root / "download-cache")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="download-worker"
        )
        self._lock = threading.Lock()
        self._active_job: (
            tuple[str, ProgressRecorder, CancellationToken, Future[None]] | None
        ) = None

        self._recover_incomplete_runs()

    def _recover_incomplete_runs(self) -> None:
        """Startup check: validate status files and mark non-terminal runs as failed (CORE-003)."""
        if not self.runs_dir.exists():
            return
        for run_dir in self.runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            status_file = run_dir / "status.json"
            if not status_file.exists():
                continue
            try:
                raw_text = status_file.read_text(encoding="utf-8")
                persisted = PersistedDownloadSnapshot.model_validate_json(raw_text)
                if not persisted.state.is_terminal:
                    updated = persisted.model_copy(
                        update={
                            "state": DownloadState.FAILED,
                            "error_message": (
                                "Process was terminated unexpectedly before completion."
                            ),
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    tmp_file = run_dir / f"status.{uuid4().hex}.tmp"
                    with tmp_file.open("w", encoding="utf-8") as f:
                        f.write(updated.model_dump_json(indent=2))
                    tmp_file.replace(status_file)
            except (ValidationError, json.JSONDecodeError, OSError) as err:
                logger.warning("Failed to recover run status for %s: %s", run_dir.name, err)

    def start(self, spec: DatasetDownloadSpec) -> str:
        """Start a new background download job."""
        with self._lock:
            if self._active_job is not None:
                _, _, _, future = self._active_job
                if not future.done():
                    raise ActiveDownloadConflictError(self._active_job[0])

            download_id = f"dl-{uuid4().hex[:12]}"
            run_dir = self.runs_dir / download_id
            recorder = ProgressRecorder(
                download_id=download_id,
                storage_dir=run_dir,
                security_list_id=spec.security_list_id,
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
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder,
        token: CancellationToken,
    ) -> None:
        try:
            if self._job_executor:
                self._job_executor(spec, recorder, token)
            else:
                self._execute_job(spec, recorder, token)
        except Exception as error:
            tb_str = traceback.format_exc()
            logger.exception("Download job %s failed unexpectedly: %s", download_id, error)
            if token.is_cancelled:
                recorder.finish_cancelled(f"Download cancelled: {error}")
            else:
                recorder.finish_failed(str(error), traceback=tb_str)

    def _execute_job(
        self,
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder,
        token: CancellationToken,
    ) -> None:
        """Hook method executing download_composite."""
        from .downloads import CompositeDownloadContext, download_composite

        context = CompositeDownloadContext(
            credentials=self.credentials,
            fetch_json=self.fetch_json,
            wait=self.wait,
            recorder=recorder,
            token=token,
            cache=self.request_cache,
        )
        download_composite(self.market_store, spec, context)

    def get(self, download_id: str) -> DownloadSnapshot:
        """Retrieve the current or historical snapshot for a download ID."""
        with self._lock:
            if self._active_job and self._active_job[0] == download_id:
                return self._active_job[1].snapshot()

        run_dir = self.runs_dir / download_id
        if not run_dir.exists():
            raise DownloadNotFoundError(download_id)

        try:
            return ProgressRecorder.read_snapshot(run_dir)
        except (FileNotFoundError, ValidationError) as err:
            raise DownloadNotFoundError(download_id) from err

    def get_latest(self) -> DownloadSnapshot:
        """Retrieve the most recent download snapshot."""
        with self._lock:
            if self._active_job is not None:
                return self._active_job[1].snapshot()

        if not self.runs_dir.exists():
            raise DownloadNotFoundError("latest")

        candidate_dirs = [d for d in self.runs_dir.iterdir() if d.is_dir()]
        if not candidate_dirs:
            raise DownloadNotFoundError("latest")

        candidate_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for run_dir in candidate_dirs:
            try:
                return ProgressRecorder.read_snapshot(run_dir)
            except (FileNotFoundError, ValidationError):
                continue

        raise DownloadNotFoundError("latest")

    latest = get_latest

    def cancel(self, download_id: str) -> DownloadSnapshot:
        """Cooperative cancellation of an active download job."""
        with self._lock:
            if not self._active_job or self._active_job[0] != download_id:
                active = False
            else:
                active = True

        if not active:
            snap = self.get(download_id)
            if snap.state.is_terminal:
                raise DownloadCannotBeCancelledError("Download has already finished.")
            raise DownloadCannotBeCancelledError(
                "Download is not currently active in memory to cancel."
            )

        with self._lock:
            if not self._active_job or self._active_job[0] != download_id:
                raise DownloadCannotBeCancelledError("Download is no longer active.")
            _, recorder, token, future = self._active_job
            snap = recorder.snapshot()
            if snap.phase == DownloadPhase.PUBLISHING:
                raise DownloadCannotBeCancelledError(
                    "Download is publishing to dataset storage and cannot be cancelled."
                )
            if snap.state.is_terminal:
                raise DownloadCannotBeCancelledError("Download has already finished.")

            if not token.cancel():
                raise DownloadCannotBeCancelledError(
                    "Download is publishing to dataset storage and cannot be cancelled."
                )
            recorder.set_cancelling()
            return recorder.snapshot()

    def shutdown(self, wait: bool = True, timeout: float = 5.0) -> None:
        """Gracefully shut down background workers and signal cancellation."""
        timed_out = False
        with self._lock:
            if self._active_job:
                _, recorder, token, future = self._active_job
                token.cancel()
                if not future.done():
                    recorder.set_cancelling()
                    if wait:
                        try:
                            future.result(timeout=timeout)
                        except (TimeoutError, Exception) as err:
                            timed_out = True
                            logger.warning(
                                "Active download did not terminate within %.1fs timeout: %s",
                                timeout,
                                err,
                            )

        executor_wait = wait and not timed_out
        self._executor.shutdown(wait=executor_wait, cancel_futures=True)
