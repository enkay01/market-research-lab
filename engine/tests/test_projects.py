"""Unit tests for ProjectStore watchlist and thesis operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_research_lab.projects import ProjectNotFoundError, ProjectStore
from market_research_lab.research import InvalidSecurityIdError, SecurityNotWatchedError


def test_create_project_initializes_empty_watchlist(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")
    assert store.get_watchlist(project.id) == []


def test_add_and_remove_from_watchlist(tmp_path: Path) -> None:
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


def test_thesis_operations_require_watched_security(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")

    # Unwatched security throws SecurityNotWatchedError
    with pytest.raises(SecurityNotWatchedError):
        store.get_thesis(project.id, "sec-aapl")

    with pytest.raises(SecurityNotWatchedError):
        store.save_thesis(project.id, "sec-aapl", "# AAPL Thesis\n\n## Summary\nApple.")

    # After adding to watchlist, thesis can be saved and read
    store.add_to_watchlist(project.id, "sec-aapl")
    thesis = store.save_thesis(project.id, "sec-aapl", "# AAPL Thesis\n\n## Summary\nApple.")
    assert thesis.security_id == "sec-aapl"
    assert thesis.summary == "Apple."

    loaded = store.get_thesis(project.id, "sec-aapl")
    assert loaded is not None
    assert loaded.summary == "Apple."


def test_removing_from_watchlist_retains_thesis_file(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")

    store.add_to_watchlist(project.id, "sec-aapl")
    store.save_thesis(project.id, "sec-aapl", "# AAPL Thesis\n\n## Summary\nRetained Apple thesis.")

    # Remove from watchlist
    store.remove_from_watchlist(project.id, "sec-aapl")
    assert store.is_watched(project.id, "sec-aapl") is False

    # Attempting to read while unwatched fails
    with pytest.raises(SecurityNotWatchedError):
        store.get_thesis(project.id, "sec-aapl")

    # Re-adding to watchlist restores the existing thesis!
    store.add_to_watchlist(project.id, "sec-aapl")
    restored = store.get_thesis(project.id, "sec-aapl")
    assert restored is not None
    assert restored.summary == "Retained Apple thesis."


def test_watchlist_operations_reject_unsafe_security_ids(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Tech Research")

    with pytest.raises(InvalidSecurityIdError):
        store.add_to_watchlist(project.id, "../unsafe")


def test_watchlist_operations_on_nonexistent_project(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    with pytest.raises(ProjectNotFoundError):
        store.get_watchlist("non-existent-id")
