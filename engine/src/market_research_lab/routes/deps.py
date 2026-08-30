"""Shared dependency injection providers, common exceptions, and helpers for domain sub-routers."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import Request

from ..configuration import load_provider_credentials
from ..json_types import JsonValue
from ..logging_setup import run_log_context
from ..market_data import MarketDataStore
from ..projects import ProjectStore
from ..providers import JsonFetcher, ProviderCredentials

logger = logging.getLogger(__name__)


class SecurityNotFoundError(Exception):
    """Raised when a security is not found in the local catalogue."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Security '{identifier}' was not found in the local catalogue.")
        self.identifier = identifier


class DatasetVersionInUseError(Exception):
    """Raised when a Dataset Version is still referenced by a Project Run."""

    def __init__(self, dataset_version_id: str, references: list[dict[str, JsonValue]]) -> None:
        self.dataset_version_id = dataset_version_id
        self.references = references
        reference_labels = ", ".join(
            f"{reference.get('project_name', 'Project')} / Run {reference.get('run_id', 'unknown')}"
            for reference in references
        )
        super().__init__(
            f"Dataset Version '{dataset_version_id}' is referenced by "
            f"{len(references)} Project Run(s): {reference_labels}. "
            "Delete those Runs first."
        )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def non_blank_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Name cannot be empty or whitespace.")
    return cleaned


def get_project_store(request: Request) -> ProjectStore:
    """Resolve the ProjectStore from app state or default workspace."""
    if hasattr(request.app.state, "project_store") and request.app.state.project_store is not None:
        return request.app.state.project_store
    return ProjectStore(_repository_root() / "workspace")


def get_market_store(request: Request) -> MarketDataStore:
    """Resolve the MarketDataStore from app state or default workspace."""
    if hasattr(request.app.state, "market_store") and request.app.state.market_store is not None:
        return request.app.state.market_store
    return MarketDataStore(_repository_root() / "workspace")


def get_provider_credentials(request: Request) -> ProviderCredentials:
    """Resolve provider credentials from app state or env files."""
    if (
        hasattr(request.app.state, "provider_credentials")
        and request.app.state.provider_credentials is not None
    ):
        return request.app.state.provider_credentials
    workspace_root = _repository_root() / "workspace"
    repository_root = _repository_root()
    env_candidates = [
        workspace_root / ".env.local",
        workspace_root / ".env",
        repository_root / ".env.local",
        repository_root / ".env",
    ]
    env_file = next((p for p in env_candidates if p.exists()), env_candidates[0])
    return load_provider_credentials(env_file)


def get_provider_fetch_json(request: Request) -> JsonFetcher | None:
    """Resolve custom JSON fetcher from app state if configured."""
    if hasattr(request.app.state, "provider_fetch_json"):
        return request.app.state.provider_fetch_json
    return None


def log_run_event(project_id: UUID | str, run_id: str, message: str) -> None:
    with run_log_context(str(project_id), run_id):
        logger.info(message)


def log_failed_run(
    project_id: UUID | str,
    run_id: str,
    message: str,
    diagnostic_id: str | None,
) -> None:
    with run_log_context(str(project_id), run_id):
        logger.error(
            "%s [diagnostic_id=%s]",
            message,
            diagnostic_id or "none",
        )
