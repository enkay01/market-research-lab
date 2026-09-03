"""Transport-level error types and protocols for provider requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .json_types import JsonValue


class ProviderHttpError(Exception):
    """Raised when a remote provider returns an HTTP error code with headers."""

    def __init__(
        self,
        status_code: int,
        headers: Mapping[str, str] | None = None,
        message: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = dict(headers or {})
        detail = message or f"HTTP {status_code}"
        super().__init__(f"Provider HTTP error ({detail})")


class JsonFetcherProtocol(Protocol):
    """Callable protocol for fetching JSON payloads over HTTP."""

    def __call__(self, url: str, headers: Mapping[str, str]) -> JsonValue: ...
