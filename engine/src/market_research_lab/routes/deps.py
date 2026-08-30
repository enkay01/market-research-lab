"""Shared dependency injection providers, common exceptions, and helpers for domain sub-routers."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..alerts import InvalidStrategyDefinitionError
from ..backtest import BacktestError, BacktestParameterError
from ..configuration import load_provider_credentials
from ..indicators import IndicatorCalculationError, ParameterValidationError
from ..json_types import JsonValue
from ..logging_setup import run_log_context
from ..market_data import (
    DatasetVersionNotFoundError,
    InadequateTemporalProvenanceError,
    MarketDataStore,
)
from ..option_backtest import OptionBacktestError
from ..predictive_models import (
    PredictiveModelCalculationError,
    PredictiveModelDataError,
    PredictiveModelNotFoundError,
    PredictiveModelParameterError,
)
from ..projects import (
    ProjectNotFoundError,
    ProjectStore,
    RevisionNotFoundError,
    RevisionNotImmutableError,
    RunNotFoundError,
)
from ..providers import JsonFetcher, ProviderCredentials
from ..research import (
    InvalidSecurityIdError,
    SecurityNotWatchedError,
)
from ..strategies import (
    StrategyEvaluationError,
    StrategyParameterValidationError,
)

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostic_id: str | None = None


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


def register_domain_exception_handlers(app: FastAPI) -> None:
    """Register domain-specific exception handlers on a FastAPI application instance."""

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
