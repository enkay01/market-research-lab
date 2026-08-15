"""Application-bound configuration loading for local provider credentials."""

from __future__ import annotations

import os
from pathlib import Path

from .providers import ProviderCredentials


def load_provider_credentials(env_file: Path | None = None) -> ProviderCredentials:
    """Read provider configuration at the application boundary only."""
    values: dict[str, str] = {}
    if env_file is not None and env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[key.strip()] = value

    def value(name: str) -> str | None:
        configured = os.environ.get(name) or values.get(name, "")
        return configured.strip() or None

    return ProviderCredentials(
        tiingo_api_token=value("TIINGO_API_TOKEN"),
        sec_edgar_user_agent=value("SEC_EDGAR_USER_AGENT"),
    )
