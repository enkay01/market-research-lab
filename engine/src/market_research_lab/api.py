"""Validated HTTP interface for the local application."""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, File, Form, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .market_data import IngestionRequest, MarketDataStore
from .projects import Project, ProjectNotFoundError, ProjectStore


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


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
    definition: dict[str, Any]

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class DraftRequest(BaseModel):
    definition: dict[str, Any]


class DraftResponse(BaseModel):
    name: str
    definition: dict[str, Any]
    saved_at: str


class DefinitionResponse(BaseModel):
    revision: str


class RunResponse(BaseModel):
    id: str
    status: str


class DatasetImportResponse(BaseModel):
    dataset_version_id: str


class CoverageResponse(BaseModel):
    id: str
    source: str
    coverage_start: str | None
    coverage_end: str | None
    row_count: int
    rejected_count: int
    warnings: list[str]
    files: list[str]


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at)


def _non_blank_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Name cannot be blank.")
    return name


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def create_app(workspace_root: Path | None = None, static_dir: Path | None = None) -> FastAPI:
    repository_root = _repository_root()
    workspace_root = workspace_root or repository_root / "workspace"
    store = ProjectStore(workspace_root)
    market_store = MarketDataStore(workspace_root)
    app = FastAPI(title="Market Research Lab", version="0.1.0")

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

    @app.patch("/api/projects/{project_id}", response_model=ProjectResponse, tags=["projects"])
    def rename_project(project_id: UUID, request: ProjectRenameRequest) -> ProjectResponse:
        return _project_response(store.rename_project(str(project_id), request.name.strip()))

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
    def create_run(project_id: UUID) -> RunResponse:
        return RunResponse(id=store.create_run(str(project_id)), status="pending")

    @app.post(
        "/api/datasets",
        response_model=DatasetImportResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["datasets"],
    )
    def import_dataset(
        source: str = Form(...), file: UploadFile = File(...)
    ) -> DatasetImportResponse:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)

        request = IngestionRequest(
            source=source, file_path=tmp_path, retrieval_time=datetime.now(UTC).isoformat()
        )
        try:
            version = market_store.ingest(request)
            return DatasetImportResponse(dataset_version_id=version.id)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @app.get(
        "/api/datasets/{dataset_version_id}/coverage",
        response_model=CoverageResponse,
        tags=["datasets"],
    )
    def get_coverage(dataset_version_id: str) -> CoverageResponse:
        coverage = market_store.coverage(dataset_version_id)
        return CoverageResponse(
            id=coverage.id,
            source=coverage.source,
            coverage_start=coverage.coverage_start,
            coverage_end=coverage.coverage_end,
            row_count=coverage.row_count,
            rejected_count=coverage.rejected_count,
            warnings=coverage.warnings,
            files=coverage.files,
        )

    built_interface = static_dir or repository_root / "web" / "dist"
    if built_interface.is_dir():
        app.mount("/", StaticFiles(directory=built_interface, html=True), name="interface")

    return app


app = create_app()
