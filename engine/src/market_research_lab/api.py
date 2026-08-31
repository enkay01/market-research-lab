"""Validated HTTP interface for the local application."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable

from fastapi import (
    FastAPI,
    Request,
    status,
)
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .configuration import load_provider_credentials
from .logging_setup import (
    DIAGNOSTIC_ID_HEADER,
    configure_logging,
    diagnostic_context,
    new_diagnostic_id,
)
from .market_data import MarketDataStore
from .projects import ProjectStore
from .providers import JsonFetcher
from .routes import (
    ErrorResponse,
    backtests_router,
    cleanup_router,
    indicators_router,
    market_data_router,
    options_router,
    projects_router,
    register_domain_exception_handlers,
    strategies_router,
)
from .routes.backtests import ExecutionModelAssumptionsRequest
from .routes.deps import DatasetVersionInUseError, SecurityNotFoundError

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "DatasetVersionInUseError",
    "ErrorResponse",
    "ExecutionModelAssumptionsRequest",
    "HealthResponse",
    "SecurityNotFoundError",
    "app",
    "create_app",
]


class HealthResponse(BaseModel):
    status: str


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def create_app(
    workspace_root: Path | None = None,
    static_dir: Path | None = None,
    provider_fetch_json: JsonFetcher | None = None,
) -> FastAPI:
    repository_root = _repository_root()
    workspace_root = workspace_root or repository_root / "workspace"
    store = ProjectStore(workspace_root)
    market_store = MarketDataStore(workspace_root)
    configure_logging(workspace_root / "logs", write_run_log=store.append_run_log)
    app = FastAPI(title="Market Research Lab", version="0.1.0")

    env_candidates = [
        workspace_root / ".env.local",
        workspace_root / ".env",
        repository_root / ".env.local",
        repository_root / ".env",
    ]
    env_file = next((p for p in env_candidates if p.exists()), env_candidates[0])

    app.state.project_store = store
    app.state.market_store = market_store
    app.state.provider_credentials = load_provider_credentials(env_file)
    app.state.provider_fetch_json = provider_fetch_json

    @app.middleware("http")
    async def log_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_diagnostic_id = new_diagnostic_id()
        with diagnostic_context(request_diagnostic_id):
            started_at = perf_counter()
            logger.info("Request started: %s %s", request.method, request.url.path)
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unexpected API failure: %s %s", request.method, request.url.path)
                response = JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content=ErrorResponse(
                        code="unexpected_error",
                        message="The application could not complete this request.",
                        diagnostic_id=request_diagnostic_id,
                    ).model_dump(),
                )
            response.headers[DIAGNOSTIC_ID_HEADER] = request_diagnostic_id
            elapsed_ms = (perf_counter() - started_at) * 1000
            logger.info(
                "Request finished: %s %s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response

    register_domain_exception_handlers(app)

    @app.get("/api/health", response_model=HealthResponse, tags=["application"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    # Mount domain sub-routers
    app.include_router(projects_router)
    app.include_router(market_data_router)
    app.include_router(indicators_router)
    app.include_router(strategies_router)
    app.include_router(backtests_router)
    app.include_router(options_router)
    app.include_router(cleanup_router)

    built_interface = static_dir or repository_root / "web" / "dist"
    if built_interface.is_dir():
        app.mount("/", StaticFiles(directory=built_interface, html=True), name="interface")

    return app


app = create_app()
