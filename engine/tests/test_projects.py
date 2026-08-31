"""Unit tests for ProjectStore watchlist and thesis operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_research_lab.market_data import InvalidSecurityIdError
from market_research_lab.projects import ProjectNotFoundError, ProjectStore
from market_research_lab.routes.deps import SecurityNotWatchedError


def test_create_project_initializes_empty_watchlist(tmp_path: Path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")
    assert store.get_watchlist(project.id) == []


def test_add_and_remove_from_watchlist(tmp_path: Path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")

    watchlist = store.add_to_watchlist(project.id, "sec-aapl")
    assert watchlist == ["sec-aapl"]
    assert store.is_watched(project.id, "sec-aapl") is True

    # Duplicate adds are idempotent
    watchlist = store.add_to_watchlist(project.id, "sec-aapl")
    assert watchlist == ["sec-aapl"]

    # Add second security
    watchlist = store.add_to_watchlist(project.id, "sec-msft")
    assert watchlist == ["sec-aapl", "sec-msft"]

    # Remove first
    watchlist = store.remove_from_watchlist(project.id, "sec-aapl")
    assert watchlist == ["sec-msft"]
    assert store.is_watched(project.id, "sec-aapl") is False





def test_watchlist_operations_reject_unsafe_security_ids(tmp_path: Path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")

    with pytest.raises(InvalidSecurityIdError):
        store.add_to_watchlist(project.id, "../unsafe")


def test_watchlist_operations_on_nonexistent_project(tmp_path: Path):
    store = ProjectStore(tmp_path)
    with pytest.raises(ProjectNotFoundError):
        store.get_watchlist("non-existent-id")
