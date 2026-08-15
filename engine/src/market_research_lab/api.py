"""Validated HTTP interface for the local application."""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .configuration import load_provider_credentials
from .json_types import JsonObject
from .market_data import (
    CoverageReport,
    InadequateTemporalProvenanceError,
    IngestionRequest,
    MarketDataStore,
)
from .projects import Project, ProjectNotFoundError, ProjectStore
from .provider_routes import register_provider_download_route
from .providers import JsonFetcher


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: JsonObject = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class ProjectRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: str


class DefinitionCreateRequest(BaseModel):
    kind: str = Field(pattern=r"^[a-z][a-z_]*$")
    name: str = Field(min_length=1, max_length=120)
    definition: JsonObject

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class DraftRequest(BaseModel):
    definition: JsonObject


class DraftResponse(BaseModel):
    name: str
    definition: JsonObject
    saved_at: str


class DefinitionResponse(BaseModel):
    revision: str


class RunResponse(BaseModel):
    id: str
    status: str


class DatasetImportResponse(BaseModel):
    dataset_version_id: str


class DailyBarResponse(BaseModel):
    security_id: str
    session_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    retrieval_time: str
    available_at: str | None = None
    eligibility_provenance: str | None = None
    units: str = "USD"
    adjusted_open: float | None = None
    adjusted_high: float | None = None
    adjusted_low: float | None = None
    adjusted_close: float | None = None


class CorporateActionResponse(BaseModel):
    security_id: str
    type: str
    effective_date: str
    value: float
    source: str
    retrieval_time: str
    available_at: str | None = None
    eligibility_provenance: str | None = None
    units: str = "USD"


class FundamentalFactResponse(BaseModel):
    security_id: str
    field: str
    fiscal_period: str
    value: float | str
    unit: str
    filed_at: str | None = None
    available_at: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    eligibility_provenance: str | None = None
    source: str
    retrieval_time: str


class CoverageResponse(BaseModel):
    id: str
    source: str
    coverage_start: str | None
    coverage_end: str | None
    row_count: int
    rejected_count: int
    missing_fields: dict[str, int]
    warnings: list[str]
    total_warnings: int
    files: list[str]
    has_temporal_provenance: bool = False
    is_fundamentals: bool = False
    is_corporate_actions: bool = False
    dataset_type: str = "daily_bars"


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at)


def _coverage_response(coverage: CoverageReport) -> CoverageResponse:
    return CoverageResponse(
        id=coverage.id,
        source=coverage.source,
        coverage_start=coverage.coverage_start,
        coverage_end=coverage.coverage_end,
        row_count=coverage.row_count,
        rejected_count=coverage.rejected_count,
        missing_fields=coverage.missing_fields,
        warnings=coverage.warnings,
        total_warnings=coverage.total_warnings,
        files=coverage.files,
        has_temporal_provenance=coverage.has_temporal_provenance,
        is_fundamentals=coverage.is_fundamentals,
        is_corporate_actions=coverage.is_corporate_actions,
        dataset_type=coverage.dataset_type,
    )


def _non_blank_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Name cannot be blank.")
    return name


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
    app = FastAPI(title="Market Research Lab", version="0.1.0")
    env_file = (
        repository_root / ".env.local"
        if workspace_root == repository_root / "workspace"
        else workspace_root / ".env.local"
    )
    register_provider_download_route(
        app,
        market_store=market_store,
        credentials=load_provider_credentials(env_file),
        provider_fetch_json=provider_fetch_json,
    )

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_: Request, error: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="project_not_found", message="The requested Project does not exist."
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

    @app.get("/api/health", response_model=HealthResponse, tags=["application"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/projects", response_model=list[ProjectResponse], tags=["projects"])
    def list_projects() -> list[ProjectResponse]:
        return [_project_response(project) for project in store.list_projects()]

    @app.post(
        "/api/projects",
        response_model=ProjectResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["projects"],
    )
    def create_project(request: ProjectCreateRequest) -> ProjectResponse:
        return _project_response(store.create_project(request.name.strip()))

    @app.get("/api/projects/{project_id}", response_model=ProjectResponse, tags=["projects"])
    def get_project(project_id: UUID) -> ProjectResponse:
        return _project_response(store.get_project(str(project_id)))

    def rename_project(project_id: UUID, request: ProjectRenameRequest) -> ProjectResponse:
        return _project_response(store.rename_project(str(project_id), request.name.strip()))

    app.add_api_route(
        "/api/projects/{project_id}",
        rename_project,
        methods=["PATCH"],
        response_model=ProjectResponse,
        tags=["projects"],
    )

    @app.delete(
        "/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["projects"]
    )
    def delete_project(project_id: UUID) -> None:
        store.delete_project(str(project_id))

    @app.post(
        "/api/projects/{project_id}/definitions",
        response_model=DefinitionResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["definitions"],
    )
    def save_definition(project_id: UUID, request: DefinitionCreateRequest) -> DefinitionResponse:
        return DefinitionResponse(
            revision=store.save_revision(
                str(project_id),
                kind=request.kind,
                name=request.name.strip(),
                definition=request.definition,
            )
        )

    @app.put(
        "/api/projects/{project_id}/definitions/{kind}/{name}/draft",
        response_model=DraftResponse,
        tags=["definitions"],
    )
    def save_draft(project_id: UUID, kind: str, name: str, request: DraftRequest) -> DraftResponse:
        store.save_draft(str(project_id), kind=kind, name=name, definition=request.definition)
        return DraftResponse(name=name, definition=request.definition, saved_at="saved locally")

    @app.get(
        "/api/projects/{project_id}/definitions/{kind}/{name}/draft",
        response_model=DraftResponse,
        tags=["definitions"],
    )
    def get_draft(project_id: UUID, kind: str, name: str) -> DraftResponse:
        return DraftResponse(**store.read_draft(str(project_id), kind=kind, name=name))

    @app.post(
        "/api/projects/{project_id}/runs",
        response_model=RunResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["runs"],
    )
    def create_run(
        project_id: UUID,
        *,
        dataset_version_id: str | None = Query(default=None),
        historical: bool = Query(default=False),
    ) -> RunResponse:
        if historical and dataset_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A historical Run requires a Dataset Version.",
            )
        if historical and dataset_version_id is not None:
            market_store.ensure_historical_eligibility(dataset_version_id)
        return RunResponse(id=store.create_run(str(project_id)), status="pending")

    @app.post(
        "/api/datasets",
        response_model=DatasetImportResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["datasets"],
    )
    def import_dataset(
        source: str = Form(...), file: UploadFile = File(...)
    ) -> DatasetImportResponse | JSONResponse:
        # CORE-003: Interface level validation before internal module consumption
        clean_source = source.strip()
        if not clean_source:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content=ErrorResponse(
                    code="validation_error", message="Source cannot be blank."
                ).model_dump(),
            )

        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        if ext not in (".csv", ".json", ".parquet", ".pq"):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content=ErrorResponse(
                    code="validation_error",
                    message=(
                        f"Unsupported file format '{ext}'. Allowed formats: .csv, .json, .parquet"
                    ),
                ).model_dump(),
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)

        request = IngestionRequest(
            source=clean_source, file_path=tmp_path, retrieval_time=datetime.now(UTC).isoformat()
        )
        try:
            version = market_store.ingest(request)
            return DatasetImportResponse(dataset_version_id=version.id)
        except ValueError as err:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(code="import_error", message=str(err)).model_dump(),
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @app.get(
        "/api/datasets/{dataset_version_id}/coverage",
        response_model=CoverageResponse,
        tags=["datasets"],
    )
    def get_coverage(dataset_version_id: str) -> CoverageResponse:
        return _coverage_response(market_store.coverage(dataset_version_id))

    @app.get(
        "/api/datasets/{dataset_version_id}/preview",
        response_model=list[JsonObject],
        tags=["datasets"],
    )
    def get_dataset_preview(dataset_version_id: str, limit: int = 50) -> list[JsonObject]:
        return market_store.preview(dataset_version_id, limit=limit)

    @app.get(
        "/api/datasets/{dataset_version_id}/history",
        response_model=list[DailyBarResponse],
        tags=["datasets"],
    )
    def get_dataset_history(
        dataset_version_id: str,
        symbol: str | None = None,
        as_of: datetime | None = Query(
            default=None, description="As-of decision timestamp (ISO 8601)"
        ),
    ) -> list[DailyBarResponse]:
        bars = market_store.history(dataset_version_id, symbol=symbol, as_of=as_of)
        return [DailyBarResponse.model_validate(bar, from_attributes=True) for bar in bars]

    @app.get(
        "/api/datasets/{dataset_version_id}/fundamentals",
        response_model=list[FundamentalFactResponse],
        tags=["datasets"],
    )
    def get_dataset_fundamentals(
        dataset_version_id: str,
        symbol: str | None = None,
        as_of: datetime | None = Query(
            default=None, description="As-of decision timestamp (ISO 8601)"
        ),
    ) -> list[FundamentalFactResponse]:
        facts = market_store.fundamentals(dataset_version_id, symbol=symbol, as_of=as_of)
        return [
            FundamentalFactResponse.model_validate(fact, from_attributes=True) for fact in facts
        ]

    @app.get(
        "/api/datasets/{dataset_version_id}/corporate-actions",
        response_model=list[CorporateActionResponse],
        tags=["datasets"],
    )
    def get_dataset_corporate_actions(
        dataset_version_id: str,
        symbol: str | None = None,
        as_of: datetime | None = Query(
            default=None, description="As-of decision timestamp (ISO 8601)"
        ),
    ) -> list[CorporateActionResponse]:
        actions = market_store.corporate_actions(dataset_version_id, symbol=symbol, as_of=as_of)
        return [
            CorporateActionResponse.model_validate(action, from_attributes=True)
            for action in actions
        ]

    built_interface = static_dir or repository_root / "web" / "dist"
    if built_interface.is_dir():
        app.mount("/", StaticFiles(directory=built_interface, html=True), name="interface")

    return app


app = create_app()
