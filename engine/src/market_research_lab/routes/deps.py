"""Shared dependency injection providers, common exceptions, and helpers for domain sub-routers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, cast
from uuid import UUID

if TYPE_CHECKING:
    from ..download_jobs import MarketDataDownloadService

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..backtest import BacktestError, BacktestParameterError
from ..configuration import load_provider_credentials
from ..indicators import IndicatorCalculationError, ParameterValidationError
from ..json_types import JsonValue
from ..logging_setup import run_log_context
from ..market_data import (
    DatasetVersionNotFoundError,
    InsufficientTimestampError,
    InvalidSecurityIdError,
    MarketDataStore,
)
from ..option_backtest import OptionBacktestError
from ..projects import (
    ProjectNotFoundError,
    ProjectStore,
    RevisionNotFoundError,
    RevisionNotImmutableError,
    RunNotFoundError,
)
from ..providers import JsonFetcher, ProviderCredentials
from ..security_lists import SecurityListNotFoundError
from ..strategies import (
    StrategyEvaluationError,
    StrategyParameterValidationError,
)

logger = logging.getLogger(__name__)


class InvalidStrategyDefinitionError(ValueError):
    """Raised when an enabled Strategy definition cannot be validated."""


class SecurityNotWatchedError(Exception):
    """Raised when an operation requires a watched security that is not in the project watchlist."""


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostic_id: str | None = None


class SecurityNotFoundError(Exception):
    """Raised when a security cannot be resolved."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Security '{identifier}' was not found.")
        self.identifier = identifier


class DatasetVersionInUseError(Exception):
    """Raised when a dataset version cannot be deleted because runs depend on it."""

    def __init__(
        self, version_id: str, referencing_runs: list[dict[str, JsonValue] | str]
    ) -> None:
        formatted = [
            r
            if isinstance(r, str)
            else f"{r.get('project_name', 'Project')} / Run {r.get('run_id', 'unknown')}"
            for r in referencing_runs
        ]
        super().__init__(
            f"Dataset Version '{version_id}' cannot be deleted because it is referenced by "
            f"Project Runs: {', '.join(formatted)}."
        )
        self.version_id = version_id
        self.referencing_runs = referencing_runs
        self.references = referencing_runs



def get_project_store(request: Request) -> ProjectStore:
    return request.app.state.project_store


def get_market_store(request: Request) -> MarketDataStore:
    return request.app.state.market_store


def get_provider_credentials(request: Request) -> ProviderCredentials:
    return getattr(
        request.app.state, "provider_credentials", None
    ) or load_provider_credentials()


def get_provider_fetch_json(request: Request) -> JsonFetcher | None:
    return getattr(request.app.state, "provider_fetch_json", None)


def get_provider_wait(request: Request) -> Callable[[float], None]:
    import time
    return getattr(request.app.state, "provider_wait", None) or time.sleep


def get_download_service(request: Request) -> MarketDataDownloadService:
    return cast("MarketDataDownloadService", request.app.state.download_service)


def non_blank_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Name cannot be blank.")
    return cleaned


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



def register_domain_exception_handlers(app: FastAPI) -> None:
    """Register uniform RFC 7807-style JSON error handlers on a FastAPI application."""

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_: Request, error: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="project_not_found",
                message="The requested Project does not exist.",
                details={"error": str(error)},
            ).model_dump(),
        )

    @app.exception_handler(RunNotFoundError)
    async def run_not_found(_: Request, error: RunNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="run_not_found",
                message=str(error),
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
                code="dataset_version_not_found",
                message=str(error),
                details={},
            ).model_dump(),
        )

    @app.exception_handler(DatasetVersionInUseError)
    async def dataset_version_in_use(
        _: Request, error: DatasetVersionInUseError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                code="dataset_version_in_use",
                message=str(error),
                details={
                    "references": error.references,
                    "referencing_runs": error.referencing_runs,
                },
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

    @app.exception_handler(InsufficientTimestampError)
    async def inadequate_temporal_provenance(
        _: Request, error: InsufficientTimestampError
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

    @app.exception_handler(SecurityListNotFoundError)
    async def security_list_not_found(_: Request, error: SecurityListNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="security_list_not_found",
                message=str(error),
                details={},
            ).model_dump(),
        )



