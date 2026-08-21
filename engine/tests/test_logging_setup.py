"""Checks for local diagnostic logging."""

from __future__ import annotations

import logging

from market_research_lab.logging_setup import (
    configure_logging,
    diagnostic_context,
    run_log_context,
)


def test_logging_links_application_and_run_records(tmp_path):
    run_logs: list[tuple[str, str, str]] = []
    configure_logging(
        tmp_path,
        write_run_log=lambda project_id, run_id, line: run_logs.append((project_id, run_id, line)),
    )

    with diagnostic_context("diagnostic-123"):
        with run_log_context("project-123", "run-123"):
            logging.getLogger("market_research_lab.tests").warning("Run could not complete")

    application_log = (tmp_path / "application.log").read_text(encoding="utf-8")
    assert "diagnostic_id=diagnostic-123" in application_log
    assert "project_id=project-123" in application_log
    assert "run_id=run-123" in application_log
    assert "Run could not complete" in application_log
    assert len(run_logs) == 1
    project_id, run_id, line = run_logs[0]
    assert project_id == "project-123"
    assert run_id == "run-123"
    assert "diagnostic_id=diagnostic-123" in line
