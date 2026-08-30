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
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .alerts import (
    InvalidStrategyDefinitionError,
)
from .backtest import (
    BacktestError,
    BacktestParameterError,
)
from .configuration import load_provider_credentials
from .indicators import (
    IndicatorCalculationError,
    ParameterValidationError,
)
from .json_types import JsonValue
from .logging_setup import (
    DIAGNOSTIC_ID_HEADER,
    configure_logging,
    diagnostic_context,
    new_diagnostic_id,
)
from .market_data import (
    DatasetVersionNotFoundError,
    InadequateTemporalProvenanceError,
    MarketDataStore,
)
from .option_backtest import (
    OptionBacktestError,
)
from .predictive_models import (
    PredictiveModelCalculationError,
    PredictiveModelDataError,
    PredictiveModelNotFoundError,
    PredictiveModelParameterError,
)
from .projects import (
    ProjectNotFoundError,
    ProjectStore,
    RevisionNotFoundError,
    RevisionNotImmutableError,
    RunNotFoundError,
)
from .providers import JsonFetcher
from .research import (
    InvalidSecurityIdError,
    SecurityNotWatchedError,
)
from .routes import (
    alerts_router,
    backtests_router,
    cleanup_router,
    indicators_router,
    market_data_router,
    options_router,
    predictive_models_router,
    projects_router,
    strategies_router,
    valuations_router,
)
from .routes.backtests import ExecutionModelAssumptionsRequest
from .routes.deps import DatasetVersionInUseError, SecurityNotFoundError
from .strategies import (
    StrategyEvaluationError,
    StrategyParameterValidationError,
)

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


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostic_id: str | None = None


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

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_: Request, error: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="project_not_found", message="The requested Project does not exist."
            ).model_dump(),
        )

    @app.exception_handler(RunNotFoundError)
    async def run_not_found(_: Request, error: RunNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="run_not_found",
                message=f"The requested Run '{error}' does not exist.",
                details={},
            ).model_dump(),
        )

    @app.exception_handler(DatasetVersionNotFoundError)
    async def dataset_version_not_found(
        _: Request, error: DatasetVersionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="dataset_version_not_found", message=str(error), details={}
            ).model_dump(),
        )

    @app.exception_handler(DatasetVersionInUseError)
    async def dataset_version_in_use(_: Request, error: DatasetVersionInUseError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                code="dataset_version_in_use",
                message=str(error),
                details={"references": error.references},
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="validation_error",
                message="The request is not valid.",
                details={"errors": jsonable_encoder(error.errors())},
            ).model_dump(),
        )

    @app.exception_handler(InadequateTemporalProvenanceError)
    async def inadequate_temporal_provenance(
        _: Request, error: InadequateTemporalProvenanceError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="point_in_time_data_required",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(SecurityNotFoundError)
    async def security_not_found(_: Request, error: SecurityNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="security_not_found",
                message=str(error),
                details={"identifier": error.identifier},
            ).model_dump(),
        )

    @app.exception_handler(SecurityNotWatchedError)
    async def security_not_watched(_: Request, error: SecurityNotWatchedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="security_not_watched",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(InvalidSecurityIdError)
    async def invalid_security_id(_: Request, error: InvalidSecurityIdError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="invalid_security_id",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(ParameterValidationError)
    async def parameter_validation_error(
        _: Request, error: ParameterValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="parameter_validation_error",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(IndicatorCalculationError)
    async def indicator_calculation_error(
        _: Request, error: IndicatorCalculationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="indicator_calculation_error",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(StrategyParameterValidationError)
    async def strategy_parameter_validation_error(
        _: Request, error: StrategyParameterValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="parameter_validation_error",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(StrategyEvaluationError)
    async def strategy_evaluation_error(_: Request, error: StrategyEvaluationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="strategy_evaluation_error",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(RevisionNotImmutableError)
    async def revision_not_immutable(_: Request, error: RevisionNotImmutableError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="revision_not_immutable",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(RevisionNotFoundError)
    async def revision_not_found(_: Request, error: RevisionNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="revision_not_found",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(InvalidStrategyDefinitionError)
    async def invalid_strategy_definition(
        _: Request, error: InvalidStrategyDefinitionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="invalid_strategy_definition",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(BacktestParameterError)
    async def backtest_parameter_error(_: Request, error: BacktestParameterError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="parameter_validation_error",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(OptionBacktestError)
    async def option_backtest_error(_: Request, error: OptionBacktestError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="options_backtest_error", message=str(error), details={}
            ).model_dump(),
        )

    @app.exception_handler(BacktestError)
    async def backtest_error(_: Request, error: BacktestError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="backtest_error",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(PredictiveModelNotFoundError)
    async def predictive_model_not_found(
        _: Request, error: PredictiveModelNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="predictive_model_not_found", message=str(error), details={}
            ).model_dump(),
        )

    @app.exception_handler(PredictiveModelParameterError)
    async def predictive_model_parameter_error(
        _: Request, error: PredictiveModelParameterError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="parameter_validation_error", message=str(error), details={}
            ).model_dump(),
        )

    @app.exception_handler(PredictiveModelDataError)
    async def predictive_model_data_error(
        _: Request, error: PredictiveModelDataError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="predictive_model_data_not_found", message=str(error), details={}
            ).model_dump(),
        )

    @app.exception_handler(PredictiveModelCalculationError)
    async def predictive_model_calculation_error(
        _: Request, error: PredictiveModelCalculationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                code="predictive_model_calculation_error", message=str(error), details={}
            ).model_dump(),
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["application"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    # Mount domain sub-routers
    app.include_router(projects_router)
    app.include_router(market_data_router)
    app.include_router(valuations_router)
    app.include_router(indicators_router)
    app.include_router(strategies_router)
    app.include_router(predictive_models_router)
    app.include_router(backtests_router)
    app.include_router(options_router)
    app.include_router(alerts_router)
    app.include_router(cleanup_router)

    built_interface = static_dir or repository_root / "web" / "dist"
    if built_interface.is_dir():
        app.mount("/", StaticFiles(directory=built_interface, html=True), name="interface")

    return app


app = create_app()
