"""Unit tests for RateGate and ControlledJsonFetcher."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest

from market_research_lab.request_control import (
    ControlledJsonFetcher,
    FileRequestResultCache,
    RateGate,
)
from market_research_lab.transport import ProviderHttpError


class FakeClock:
    def __init__(self, start_time: float = 1000.0) -> None:
        self.current_time = start_time
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current_time

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current_time += seconds


def test_rate_gate_basic_mode_enforces_interval():
    clock = FakeClock()
    gate = RateGate(
        min_interval_seconds=12.25,
        max_requests_per_window=5,
        window_seconds=60.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    gate.acquire()
    assert clock.sleeps == []

    # Second call right away must wait 12.25s
    gate.acquire()
    assert clock.sleeps == [12.25]

    # Third call after 5s elapsed must wait remaining 7.25s
    clock.current_time += 5.0
    gate.acquire()
    assert clock.sleeps == [12.25, 7.25]


def test_rate_gate_handles_429_retry_after_seconds():
    clock = FakeClock()
    gate = RateGate(
        min_interval_seconds=0.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
    )

    gate.acquire()
    # Report 429 with Retry-After: 30
    gate.record_429(retry_after="30")

    # Next acquire must wait 30 seconds
    gate.acquire()
    assert clock.sleeps == [30.0]


def test_rate_gate_handles_429_retry_after_http_date():
    clock = FakeClock(start_time=100.0)
    wall_clock = FakeClock(start_time=1704200000.0)
    gate = RateGate(
        min_interval_seconds=0.0,
        clock=clock.monotonic,
        wall_clock=wall_clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
    )

    # Wed, 03 Jan 2024 12:54:00 GMT is 1704286440 (86440 seconds later than 1704200000)
    gate.record_429(retry_after="Wed, 03 Jan 2024 12:54:00 GMT")
    gate.acquire()
    assert clock.sleeps == [86440.0]


def test_rate_gate_on_wait_callback():
    clock = FakeClock()
    recorded_waits: list[float] = []

    gate = RateGate(
        min_interval_seconds=12.25,
        clock=clock.monotonic,
        sleep=clock.sleep,
        on_wait=recorded_waits.append,
    )

    gate.acquire()
    assert recorded_waits == []

    gate.acquire()
    # Expected: on_wait called with wait_time (12.25), then 0.0 upon completion
    assert recorded_waits == [12.25, 0.0]


def test_rate_gate_cancellation_aborts_wait():
    clock = FakeClock()
    gate = RateGate(
        min_interval_seconds=12.25,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    gate.acquire()
    cancelled = True

    with pytest.raises(TimeoutError, match="cancelled"):
        gate.acquire(is_cancelled=lambda: cancelled)


def test_rate_gate_concurrent_threads_reserve_sequential_slots_without_bursting():
    # Test concurrency with 6 threads calling acquire concurrently
    interval = 0.06
    gate = RateGate(
        min_interval_seconds=interval,
    )

    def worker() -> float:
        gate.acquire()
        return time.monotonic()

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker) for _ in range(6)]
        start_times = [f.result() for f in as_completed(futures)]

    assert len(start_times) == 6
    start_times.sort()

    for i in range(len(start_times) - 1):
        diff = start_times[i + 1] - start_times[i]
        # Must be spaced by at least interval (allowing Windows clock resolution margin)
        assert diff >= 0.045, f"Interval too small between thread {i} and {i+1}: {diff:.4f}s"
    # Overall duration must span at least (N-1) * interval * 0.95
    assert (start_times[-1] - start_times[0]) >= 5 * interval * 0.9


def test_controlled_json_fetcher_intercepts_429():
    clock = FakeClock()
    gate = RateGate(
        min_interval_seconds=0.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
    )

    attempts = 0

    def mock_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderHttpError(429, headers={"Retry-After": "15"}, message="Too Many Requests")
        return {"status": "ok"}

    fetcher = ControlledJsonFetcher(fetch=mock_fetch, gate=gate)
    result = fetcher("https://api.example.com/test", {})

    assert result == {"status": "ok"}
    assert attempts == 2
    assert clock.sleeps == [15.0]


def test_cached_response_bypasses_rate_wait_and_does_not_store_credentials(tmp_path):
    clock = FakeClock()
    gate = RateGate(
        clock=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
    )
    gate.record_429(retry_after="30")
    cache = FileRequestResultCache(tmp_path / "download-cache")
    url = "https://api.example.com/prices?symbol=AAPL"
    cache.put(url, {"Authorization": "first-secret"}, {"prices": [100]})

    def unexpected_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("A completed cached response should not be downloaded again.")

    fetcher = ControlledJsonFetcher(fetch=unexpected_fetch, gate=gate, cache=cache)
    result = fetcher(url, {"Authorization": "second-secret"})

    assert result == {"prices": [100]}
    assert clock.sleeps == []
    cache_text = next((tmp_path / "download-cache").iterdir()).read_text(encoding="utf-8")
    assert "first-secret" not in cache_text
    assert "second-secret" not in cache_text
