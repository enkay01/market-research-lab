"""Deterministic rate limiting, HTTP 429 coordination, and controlled fetching."""

from __future__ import annotations

import email.utils
import hashlib
import json
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC
from pathlib import Path
from typing import Protocol

from .json_types import JsonValue
from .transport import JsonFetcherProtocol, ProviderHttpError


class RequestResultCache(Protocol):
    def get(self, url: str, headers: Mapping[str, str]) -> JsonValue | None: ...

    def put(self, url: str, headers: Mapping[str, str], result: JsonValue) -> None: ...


def _cache_key(url: str, headers: Mapping[str, str]) -> str:
    safe_headers = {
        name.lower(): value
        for name, value in headers.items()
        if name.lower() not in {"authorization", "api-key", "x-api-key"}
    }
    payload = json.dumps([url, sorted(safe_headers.items())], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FileRequestResultCache:
    """Replay completed JSON responses without persisting provider credentials."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def get(self, url: str, headers: Mapping[str, str]) -> JsonValue | None:
        path = self.directory / f"{_cache_key(url, headers)}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def put(self, url: str, headers: Mapping[str, str], result: JsonValue) -> None:
        path = self.directory / f"{_cache_key(url, headers)}.json"
        temp = self.directory / f"{path.stem}.{threading.get_ident()}.tmp"
        with self._lock:
            temp.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
            temp.replace(path)


class RateGate:
    """Thread-safe rate limiter and backoff coordinator for provider endpoints."""

    def __init__(
        self,
        min_interval_seconds: float = 0.0,
        max_requests_per_window: int | None = None,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
        on_wait: Callable[[float], None] | None = None,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.max_requests_per_window = max_requests_per_window
        self.window_seconds = window_seconds
        self.clock = clock
        self.wall_clock = wall_clock
        self.sleep = sleep
        self.jitter = jitter or (lambda: random.uniform(0.1, 0.5))
        self.on_wait = on_wait

        self._lock = threading.Lock()
        self._next_available_time: float = 0.0
        self._backoff_until: float = 0.0
        self._consecutive_429s: int = 0
        self._window_starts: deque[float] = deque()

    def record_429(self, retry_after: str | int | float | None = None) -> None:
        """Record an HTTP 429 response and schedule backoff."""
        with self._lock:
            now = self.clock()
            self._consecutive_429s += 1
            delay = self._parse_retry_after(retry_after, self.wall_clock())
            if delay is None:
                # Capped exponential backoff (e.g. 2s, 4s, 8s... up to 60s)
                base = min(60.0, 2.0 ** min(self._consecutive_429s, 6))
                delay = base
            jitter_amount = self.jitter()
            self._backoff_until = max(self._backoff_until, now + delay + jitter_amount)

    def _parse_retry_after(
        self, raw: str | int | float | None, wall_clock_now: float
    ) -> float | None:
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        raw_str = str(raw).strip()
        if not raw_str:
            return None
        if raw_str.isdigit():
            return float(raw_str)
        try:
            target_dt = email.utils.parsedate_to_datetime(raw_str)
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=UTC)
            target_ts = target_dt.timestamp()
            return max(0.0, target_ts - wall_clock_now)
        except (TypeError, ValueError):
            return None

    def _clean_window(self, now: float) -> None:
        if self.max_requests_per_window:
            while (
                self._window_starts
                and now - self._window_starts[0] >= self.window_seconds
            ):
                self._window_starts.popleft()

    def _reserve_slot(self, now: float) -> float:
        self._clean_window(now)
        earliest = max(now, self._backoff_until, self._next_available_time)
        if (
            self.max_requests_per_window
            and len(self._window_starts) >= self.max_requests_per_window
        ):
            oldest = self._window_starts[0]
            earliest = max(earliest, oldest + self.window_seconds)

        slot = earliest
        self._next_available_time = slot + self.min_interval_seconds
        if self.max_requests_per_window:
            self._window_starts.append(slot)
        return slot

    def _sleep_interruptibly(
        self, wait_time: float, is_cancelled: Callable[[], bool] | None
    ) -> None:
        if not is_cancelled:
            self.sleep(wait_time)
            return

        end_time = self.clock() + wait_time
        while True:
            if is_cancelled():
                raise TimeoutError("Request cancelled while waiting on rate gate.")
            remaining = end_time - self.clock()
            if remaining <= 0.0:
                break
            chunk = min(remaining, 0.05)
            self.sleep(chunk)

    def acquire(self, is_cancelled: Callable[[], bool] | None = None) -> None:
        """Wait until rate gating conditions allow the next request start."""
        while True:
            if is_cancelled and is_cancelled():
                raise TimeoutError("Request cancelled while waiting on rate gate.")
            with self._lock:
                now = self.clock()
                slot = self._reserve_slot(now)
                wait_time = max(0.0, slot - now)
            if wait_time > 0.0:
                if self.on_wait:
                    self.on_wait(wait_time)
                try:
                    self._sleep_interruptibly(wait_time, is_cancelled)
                finally:
                    if self.on_wait:
                        self.on_wait(0.0)
            with self._lock:
                if self._backoff_until > self.clock():
                    continue
                self._consecutive_429s = max(0, self._consecutive_429s - 1)
                return


class ControlledJsonFetcher:
    """Wrapper around a JSON fetcher applying rate gating, retries, and cancellation."""

    def __init__(
        self,
        fetch: JsonFetcherProtocol | Callable[[str, Mapping[str, str]], JsonValue],
        gate: RateGate | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        on_request_start: Callable[[str], None] | None = None,
        on_request_end: Callable[[str, int], None] | None = None,
        cache: RequestResultCache | None = None,
        max_retries: int = 3,
    ) -> None:
        self._fetch = fetch
        self._gate = gate
        self._is_cancelled = is_cancelled
        self._on_request_start = on_request_start
        self._on_request_end = on_request_end
        self._cache = cache
        self._max_retries = max_retries

    def __call__(self, url: str, headers: Mapping[str, str]) -> JsonValue:
        attempt = 0
        while True:
            attempt += 1
            if self._is_cancelled and self._is_cancelled():
                raise TimeoutError("Download cancelled.")

            if self._cache:
                cached = self._cache.get(url, headers)
                if cached is not None:
                    return cached

            if self._gate:
                self._gate.acquire(is_cancelled=self._is_cancelled)

            if self._on_request_start:
                self._on_request_start(url)

            try:
                result = self._fetch(url, headers)
                if self._on_request_end:
                    approx_bytes = len(str(result))
                    self._on_request_end(url, approx_bytes)
                if self._cache:
                    self._cache.put(url, headers, result)
                return result
            except ProviderHttpError as error:
                if error.status_code == 429 and attempt <= self._max_retries and self._gate:
                    retry_after = (
                        error.headers.get("Retry-After")
                        or error.headers.get("retry-after")
                    )
                    self._gate.record_429(retry_after)
                    continue
                raise
