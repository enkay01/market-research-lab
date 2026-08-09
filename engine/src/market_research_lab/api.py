"""Validated HTTP interface for the local application."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi import Path as ApiPath
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .projects import (
    DefinitionRevisionReference,
    InvalidRunStateError,
    Project,
    ProjectNotFoundError,
    ProjectStore,
    RevisionNotFoundError,
    RunNotFoundError,
    RunRecord,
)

_DEFINITION_KIND_PATTERN = r"^[a-z][a-z_]*$"
_DEFINITION_NAME_MAX_LENGTH = 120
DefinitionKind = Annotated[str, ApiPath(pattern=_DEFINITION_KIND_PATTERN)]
DefinitionName = Annotated[str, ApiPath(min_length=1, max_length=_DEFINITION_NAME_MAX_LENGTH)]


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
    kind: str = Field(pattern=_DEFINITION_KIND_PATTERN)
    name: str = Field(min_length=1, max_length=_DEFINITION_NAME_MAX_LENGTH)
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


class DefinitionRevisionReferenceRequest(BaseModel):
    kind: str = Field(pattern=_DEFINITION_KIND_PATTERN)
    name: str = Field(min_length=1, max_length=_DEFINITION_NAME_MAX_LENGTH)
    revision: str = Field(pattern=r"^v[1-9][0-9]*$")

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class RunCreateRequest(BaseModel):
    definition_revisions: list[DefinitionRevisionReferenceRequest] = Field(default_factory=list)
    dataset_versions: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RunDetailResponse(BaseModel):
    id: str
    status: str
    error: str | None = None
    definition_revisions: list[DefinitionRevisionReferenceRequest]
    dataset_versions: list[str]
    parameters: dict[str, Any]
    software_revision: str
    environment: dict[str, str]
    logs: str
    artifacts: list[str]


class RunFailureRequest(BaseModel):
    error: str = Field(min_length=1, max_length=2_000)


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at)


def _run_detail_response(run: RunRecord) -> RunDetailResponse:
    return RunDetailResponse(
        id=run.id,
        status=run.status,
        error=run.error,
        definition_revisions=[
            {"kind": reference.kind, "name": reference.name, "revision": reference.revision}
            for reference in run.definition_revisions
        ],
        dataset_versions=run.dataset_versions,
        parameters=run.parameters,
        software_revision=run.software_revision,
        environment=run.environment,
        logs=run.logs,
        artifacts=run.artifacts,
    )


def _non_blank_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Name cannot be blank.")
    return name


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _software_revision(repository_root: Path) -> str:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    is_dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if revision.returncode != 0 or is_dirty.returncode != 0 or is_dirty.stdout:
        return "uncommitted"
    return revision.stdout.strip()


def create_app(workspace_root: Path | None = None, static_dir: Path | None = None) -> FastAPI:
    repository_root = _repository_root()
    store = ProjectStore(workspace_root or repository_root / "workspace")
    app = FastAPI(title="Market Research Lab", version="0.1.0")

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_: Request, error: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="project_not_found", message="The requested Project does not exist."
            ).model_dump(),
        )

    @app.exception_handler(RevisionNotFoundError)
    async def revision_not_found(_: Request, error: RevisionNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="definition_revision_not_found",
                message="A requested Definition Revision does not exist.",
                details={"revision": str(error)},
            ).model_dump(),
        )

    @app.exception_handler(RunNotFoundError)
    async def run_not_found(_: Request, error: RunNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                code="run_not_found", message="The requested Run does not exist."
            ).model_dump(),
        )

    @app.exception_handler(InvalidRunStateError)
    async def run_not_pending(_: Request, error: InvalidRunStateError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                code="run_not_pending",
                message="A terminal Run operation cannot be applied again.",
                details={"status": str(error)},
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
    def save_draft(
        project_id: UUID, kind: DefinitionKind, name: DefinitionName, request: DraftRequest
    ) -> DraftResponse:
        draft_name = _non_blank_name(name)
        store.save_draft(str(project_id), kind=kind, name=draft_name, definition=request.definition)
        return DraftResponse(
            name=draft_name, definition=request.definition, saved_at="saved locally"
        )

    @app.post(
        "/api/projects/{project_id}/definitions/{kind}/{name}/revisions",
        response_model=DefinitionResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["definitions"],
    )
    def save_draft_as_revision(
        project_id: UUID, kind: DefinitionKind, name: DefinitionName
    ) -> DefinitionResponse:
        return DefinitionResponse(
            revision=store.save_draft_as_revision(
                str(project_id), kind=kind, name=_non_blank_name(name)
            )
        )

    @app.get(
        "/api/projects/{project_id}/definitions/{kind}/{name}/draft",
        response_model=DraftResponse,
        tags=["definitions"],
    )
    def get_draft(project_id: UUID, kind: DefinitionKind, name: DefinitionName) -> DraftResponse:
        draft = store.read_draft(str(project_id), kind=kind, name=_non_blank_name(name))
        return DraftResponse(**draft)

    @app.post(
        "/api/projects/{project_id}/runs",
        response_model=RunResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["runs"],
    )
    def create_run(project_id: UUID, request: RunCreateRequest) -> RunResponse:
        return RunResponse(
            id=store.create_run(
                str(project_id),
                definition_revisions=[
                    DefinitionRevisionReference(
                        kind=reference.kind,
                        name=reference.name,
                        revision=reference.revision,
                    )
                    for reference in request.definition_revisions
                ],
                dataset_versions=request.dataset_versions,
                parameters=request.parameters,
                software_revision=_software_revision(repository_root),
                environment={"python": platform.python_version(), "platform": platform.platform()},
            ),
            status="pending",
        )

    @app.get(
        "/api/projects/{project_id}/runs/{run_id}",
        response_model=RunDetailResponse,
        tags=["runs"],
    )
    def get_run(project_id: UUID, run_id: UUID) -> RunDetailResponse:
        return _run_detail_response(store.read_run(str(project_id), str(run_id)))

    @app.post(
        "/api/projects/{project_id}/runs/{run_id}/complete",
        response_model=RunDetailResponse,
        tags=["runs"],
    )
    def complete_run(project_id: UUID, run_id: UUID) -> RunDetailResponse:
        store.complete_run(str(project_id), str(run_id))
        return _run_detail_response(store.read_run(str(project_id), str(run_id)))

    @app.post(
        "/api/projects/{project_id}/runs/{run_id}/fail",
        response_model=RunDetailResponse,
        tags=["runs"],
    )
    def fail_run(project_id: UUID, run_id: UUID, request: RunFailureRequest) -> RunDetailResponse:
        store.fail_run(str(project_id), str(run_id), error=request.error)
        return _run_detail_response(store.read_run(str(project_id), str(run_id)))

    built_interface = static_dir or repository_root / "web" / "dist"
    if built_interface.is_dir():
        app.mount("/", StaticFiles(directory=built_interface, html=True), name="interface")

    return app


app = create_app()
