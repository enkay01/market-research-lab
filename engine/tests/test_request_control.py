"""Unit tests for RateGate and ControlledJsonFetcher."""

from __future__ import annotations

from typing import Any

import pytest

from market_research_lab.request_control import ControlledJsonFetcher, RateGate
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
    clock = FakeClock(start_time=1704200000.0)
    gate = RateGate(
        min_interval_seconds=0.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
    )

    # Wed, 03 Jan 2024 12:54:00 GMT is 1704286440 (86440 seconds later)
    gate.record_429(retry_after="Wed, 03 Jan 2024 12:54:00 GMT")
    gate.acquire()
    assert clock.sleeps == [86440.0]


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
