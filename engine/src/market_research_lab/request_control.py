"""Deterministic rate limiting, HTTP 429 coordination, and controlled fetching."""

from __future__ import annotations

import email.utils
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC

from .json_types import JsonValue
from .transport import JsonFetcherProtocol, ProviderHttpError


class RateGate:
    """Thread-safe rate limiter and backoff coordinator for provider endpoints."""

    def __init__(
        self,
        min_interval_seconds: float = 0.0,
        max_requests_per_window: int | None = None,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.max_requests_per_window = max_requests_per_window
        self.window_seconds = window_seconds
        self.clock = clock
        self.sleep = sleep
        self.jitter = jitter or (lambda: random.uniform(0.1, 0.5))

        self._lock = threading.Lock()
        self._last_request_time: float = 0.0
        self._backoff_until: float = 0.0
        self._consecutive_429s: int = 0
        self._window_starts: deque[float] = deque()

    def record_429(self, retry_after: str | int | float | None = None) -> None:
        """Record an HTTP 429 response and schedule backoff."""
        with self._lock:
            now = self.clock()
            self._consecutive_429s += 1
            delay = self._parse_retry_after(retry_after, now)
            if delay is None:
                # Capped exponential backoff (e.g. 2s, 4s, 8s... up to 60s)
                base = min(60.0, 2.0 ** min(self._consecutive_429s, 6))
                delay = base
            jitter_amount = self.jitter()
            self._backoff_until = max(self._backoff_until, now + delay + jitter_amount)

    def _parse_retry_after(self, raw: str | int | float | None, now_ts: float) -> float | None:
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
            return max(0.0, target_ts - now_ts)
        except (TypeError, ValueError):
            return None

    def acquire(self, is_cancelled: Callable[[], bool] | None = None) -> None:
        """Wait until rate gating conditions allow the next request start."""
        if is_cancelled and is_cancelled():
            raise TimeoutError("Request cancelled while waiting on rate gate.")

        wait_time = 0.0
        with self._lock:
            now = self.clock()
            # Clean window history
            if self.max_requests_per_window:
                while (
                    self._window_starts
                    and now - self._window_starts[0] >= self.window_seconds
                ):
                    self._window_starts.popleft()

            # Calculate backoff constraint
            if self._backoff_until > now:
                wait_time = max(wait_time, self._backoff_until - now)

            # Calculate min interval constraint
            if self.min_interval_seconds > 0 and self._last_request_time > 0:
                elapsed = now - self._last_request_time
                if elapsed < self.min_interval_seconds:
                    wait_time = max(wait_time, self.min_interval_seconds - elapsed)

            # Calculate window constraint
            if (
                self.max_requests_per_window
                and len(self._window_starts) >= self.max_requests_per_window
            ):
                oldest = self._window_starts[0]
                wait_time = max(wait_time, self.window_seconds - (now - oldest))

        if wait_time > 0.0:
            self.sleep(wait_time)
            if is_cancelled and is_cancelled():
                raise TimeoutError("Request cancelled while waiting on rate gate.")

        with self._lock:
            now_after = self.clock()
            self._last_request_time = now_after
            if self.max_requests_per_window:
                self._window_starts.append(now_after)
            if self._backoff_until <= now_after:
                self._consecutive_429s = max(0, self._consecutive_429s - 1)


class ControlledJsonFetcher:
    """Wrapper around a JSON fetcher applying rate gating, retries, and cancellation."""

    def __init__(
        self,
        fetch: JsonFetcherProtocol | Callable[[str, Mapping[str, str]], JsonValue],
        gate: RateGate | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        on_request_start: Callable[[str], None] | None = None,
        on_request_end: Callable[[str, int], None] | None = None,
        max_retries: int = 3,
    ) -> None:
        self._fetch = fetch
        self._gate = gate
        self._is_cancelled = is_cancelled
        self._on_request_start = on_request_start
        self._on_request_end = on_request_end
        self._max_retries = max_retries

    def __call__(self, url: str, headers: Mapping[str, str]) -> JsonValue:
        attempt = 0
        while True:
            attempt += 1
            if self._is_cancelled and self._is_cancelled():
                raise TimeoutError("Download cancelled.")

            if self._gate:
                self._gate.acquire(is_cancelled=self._is_cancelled)

            if self._on_request_start:
                self._on_request_start(url)

            try:
                result = self._fetch(url, headers)
                if self._on_request_end:
                    approx_bytes = len(str(result))
                    self._on_request_end(url, approx_bytes)
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
