"""Local application logging with request and Run correlation."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

DIAGNOSTIC_ID_HEADER = "X-Diagnostic-ID"
_diagnostic_id: ContextVar[str] = ContextVar("diagnostic_id", default="-")
_project_id: ContextVar[str] = ContextVar("project_id", default="-")
_run_id: ContextVar[str] = ContextVar("run_id", default="-")

RunLogWriter = Callable[[str, str, str], None]


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.diagnostic_id = _diagnostic_id.get()
        record.project_id = _project_id.get()
        record.run_id = _run_id.get()
        return True


class _RunLogHandler(logging.Handler):
    def __init__(self, write_run_log: RunLogWriter) -> None:
        super().__init__()
        self._write_run_log = write_run_log

    def emit(self, record: logging.LogRecord) -> None:
        project_id = _project_id.get()
        run_id = _run_id.get()
        if project_id == "-" or run_id == "-":
            return
        try:
            self._write_run_log(project_id, run_id, self.format(record))
        except OSError:
            # Logging must not make an operation fail when its Run directory is unavailable.
            return


def configure_logging(log_directory: Path, *, write_run_log: RunLogWriter) -> None:
    """Configure readable local logs for this application's Python modules."""
    log_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("market_research_lab")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "[diagnostic_id=%(diagnostic_id)s project_id=%(project_id)s run_id=%(run_id)s] "
        "%(message)s"
    )
    context_filter = _ContextFilter()

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    application_handler = RotatingFileHandler(
        log_directory / "application.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    application_handler.setFormatter(formatter)
    application_handler.addFilter(context_filter)

    run_handler = _RunLogHandler(write_run_log)
    run_handler.setFormatter(formatter)
    run_handler.addFilter(context_filter)

    logger.addHandler(console_handler)
    logger.addHandler(application_handler)
    logger.addHandler(run_handler)


def new_diagnostic_id() -> str:
    """Return an identifier that links a response to its local log records."""
    return uuid4().hex


@contextmanager
def diagnostic_context(value: str) -> Iterator[None]:
    """Attach one diagnostic identifier to emitted records in this context."""
    token = _diagnostic_id.set(value)
    try:
        yield
    finally:
        _diagnostic_id.reset(token)


@contextmanager
def run_log_context(project_id: str, run_id: str) -> Iterator[None]:
    """Attach one Project and Run to emitted records in this context."""
    project_token = _project_id.set(project_id)
    run_token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(run_token)
        _project_id.reset(project_token)
