"""FastAPI router for projects, definitions, watchlist, research, and project runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi import (
    Path as FastAPIPath,
)
from pydantic import BaseModel, Field, field_validator

from ..json_types import JsonValue
from ..market_data import MarketDataStore
from ..projects import Project, ProjectStore

from .deps import SecurityNotFoundError, get_market_store, get_project_store, non_blank_name

router = APIRouter()


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return non_blank_name(value)


class ProjectRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return non_blank_name(value)


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: str


class DefinitionCreateRequest(BaseModel):
    kind: str = Field(pattern=r"^[a-z][a-z_]*$")
    name: str = Field(min_length=1, max_length=120)
    definition: dict[str, JsonValue]

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return non_blank_name(value)


class DraftRequest(BaseModel):
    definition: dict[str, JsonValue]


class DraftResponse(BaseModel):
    name: str
    definition: dict[str, JsonValue]
    saved_at: str


class DefinitionResponse(BaseModel):
    revision: str


class DefinitionRevisionResponse(BaseModel):
    kind: str
    name: str
    revision: str
    definition: dict[str, JsonValue]


class RunResponse(BaseModel):
    id: str
    status: str


class RunSummaryResponse(BaseModel):
    id: str
    kind: str
    status: str
    created_at: str
    dataset_version_ids: list[str] = Field(default_factory=list)
    definition_revisions: list[str] = Field(default_factory=list)


class SecurityResponse(BaseModel):
    security_id: str
    symbol: str
    name: str
    exchange: str | None = None
    currency: str = "USD"


class WatchlistItemResponse(BaseModel):
    security: SecurityResponse
    security_id: str
    symbol: str
    has_thesis: bool
    thesis_updated_at: str | None = None
    thesis_preview: str | None = None


class WatchlistResponse(BaseModel):
    project_id: str
    items: list[WatchlistItemResponse]
    total: int
    offset: int
    limit: int


class WatchlistQueryOptions(BaseModel):
    query: str | None = Field(default=None, description="Filter symbol or name")
    exchange: str | None = Field(default=None, description="Filter exchange")
    thesis_status: str | None = Field(default=None, description="all | has_thesis | no_thesis")
    sort_by: str = Field(
        default="symbol", description="symbol | name | exchange | thesis_updated_at"
    )
    sort_order: str = Field(default="asc", description="asc | desc")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class WatchlistAddRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class ResearchThesisResponse(BaseModel):
    security_id: str
    content: str
    updated_at: str | None = None
    summary: str | None = None
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    dated_updates: list[str] = Field(default_factory=list)


class ResearchThesisSaveRequest(BaseModel):
    content: str = Field(min_length=1)


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at)


def _thesis_response(thesis: ResearchThesis) -> ResearchThesisResponse:
    return ResearchThesisResponse(
        security_id=thesis.security_id,
        content=thesis.content,
        updated_at=thesis.updated_at,
        summary=thesis.summary,
        evidence=thesis.evidence,
        risks=thesis.risks,
        catalysts=thesis.catalysts,
        assumptions=thesis.assumptions,
        sources=thesis.sources,
        dated_updates=thesis.dated_updates,
    )


def _build_watchlist_response(
    project_id: str,
    store: ProjectStore,
    market_store: MarketDataStore,
    options: WatchlistQueryOptions | None = None,
) -> WatchlistResponse:
    opts = options or WatchlistQueryOptions()
    security_ids = store.get_watchlist(project_id)
    items: list[WatchlistItemResponse] = []

    for sid in security_ids:
        sec = market_store.get_security(sid)
        if not sec:
            continue

        if opts.query:
            q = opts.query.lower().strip()
            if q not in sec.symbol.lower() and q not in sec.name.lower():
                continue

        if opts.exchange:
            req_ex = opts.exchange.lower().strip()
            sec_ex = (sec.exchange or "").lower().strip()
            if req_ex != sec_ex:
                continue

        has_thesis = False
        thesis_updated_at = None
        thesis_preview = None

        items.append(
            WatchlistItemResponse(
                security=SecurityResponse(
                    security_id=sec.security_id,
                    symbol=sec.symbol,
                    name=sec.name,
                    exchange=sec.exchange,
                    currency=sec.currency,
                ),
                security_id=sec.security_id,
                symbol=sec.symbol,
                has_thesis=has_thesis,
                thesis_updated_at=thesis_updated_at,
                thesis_preview=thesis_preview,
            )
        )

    reverse = opts.sort_order.lower() == "desc"
    if opts.sort_by == "name":
        items.sort(key=lambda x: x.security.name.lower(), reverse=reverse)
    elif opts.sort_by == "exchange":
        items.sort(key=lambda x: (x.security.exchange or "").lower(), reverse=reverse)
    elif opts.sort_by == "thesis_updated_at":
        items.sort(key=lambda x: x.thesis_updated_at or "", reverse=reverse)
    else:
        items.sort(key=lambda x: x.symbol.lower(), reverse=reverse)

    total = len(items)
    paged_items = items[opts.offset : opts.offset + opts.limit]

    return WatchlistResponse(
        project_id=project_id,
        items=paged_items,
        total=total,
        offset=opts.offset,
        limit=opts.limit,
    )


@router.get("/api/projects", response_model=list[ProjectResponse], tags=["projects"])
def list_projects(
    store: ProjectStore = Depends(get_project_store),
) -> list[ProjectResponse]:
    return [_project_response(project) for project in store.list_projects()]


@router.post(
    "/api/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(
    request: ProjectCreateRequest,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    return _project_response(store.create_project(request.name.strip()))


@router.get("/api/projects/{project_id}", response_model=ProjectResponse, tags=["projects"])
def get_project(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    return _project_response(store.get_project(str(project_id)))


@router.api_route(
    "/api/projects/{project_id}",
    methods=["PATCH"],
    response_model=ProjectResponse,
    tags=["projects"],
)
def rename_project(
    project_id: UUID,
    request: ProjectRenameRequest,
    store: ProjectStore = Depends(get_project_store),
) -> ProjectResponse:
    return _project_response(store.rename_project(str(project_id), request.name.strip()))


@router.delete(
    "/api/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["projects"],
)
def delete_project(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> None:
    store.delete_project(str(project_id))


@router.post(
    "/api/projects/{project_id}/definitions",
    response_model=DefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["definitions"],
)
def save_definition(
    project_id: UUID,
    request: DefinitionCreateRequest,
    store: ProjectStore = Depends(get_project_store),
) -> DefinitionResponse:
    return DefinitionResponse(
        revision=store.save_revision(
            str(project_id),
            kind=request.kind,
            name=request.name.strip(),
            definition=request.definition,
        )
    )


@dataclass(frozen=True)
class DefinitionPathTarget:
    project_id: str
    kind: str
    name: str


def _extract_definition_path(
    project_id: UUID,
    kind: str,
    name: str,
) -> DefinitionPathTarget:
    return DefinitionPathTarget(project_id=str(project_id), kind=kind, name=name)


@dataclass(frozen=True)
class RevisionPathTarget:
    project_id: str
    kind: str
    name: str
    revision: str


def _extract_revision_path(
    project_id: UUID,
    kind: str = FastAPIPath(pattern=r"^[a-z][a-z_]*$"),
    name: str = FastAPIPath(min_length=1, max_length=128),
    revision: str = FastAPIPath(pattern=r"^v[1-9][0-9]*$"),
) -> RevisionPathTarget:
    return RevisionPathTarget(
        project_id=str(project_id), kind=kind, name=name, revision=revision
    )


class CreateRunOptions(BaseModel):
    dataset_version_id: str | None = None
    historical: bool = False


@router.put(
    "/api/projects/{project_id}/definitions/{kind}/{name}/draft",
    response_model=DraftResponse,
    tags=["definitions"],
)
def save_draft(
    request: DraftRequest,
    target: DefinitionPathTarget = Depends(_extract_definition_path),
    store: ProjectStore = Depends(get_project_store),
) -> DraftResponse:
    store.save_draft(
        target.project_id,
        kind=target.kind,
        name=target.name,
        definition=request.definition,
    )
    return DraftResponse(
        name=target.name, definition=request.definition, saved_at="saved locally"
    )


@router.get(
    "/api/projects/{project_id}/definitions/{kind}/{name}/draft",
    response_model=DraftResponse,
    tags=["definitions"],
)
def get_draft(
    project_id: UUID,
    kind: str,
    name: str,
    store: ProjectStore = Depends(get_project_store),
) -> DraftResponse:
    return DraftResponse(**store.read_draft(str(project_id), kind=kind, name=name))


@router.get(
    "/api/projects/{project_id}/definitions/{kind}/{name}/{revision}",
    response_model=DefinitionRevisionResponse,
    tags=["definitions"],
)
def read_definition_revision(
    target: RevisionPathTarget = Depends(_extract_revision_path),
    store: ProjectStore = Depends(get_project_store),
) -> DefinitionRevisionResponse:
    wrapped = store.read_revision(
        target.project_id, kind=target.kind, name=target.name, revision=target.revision
    )
    return DefinitionRevisionResponse(
        kind=target.kind,
        name=str(wrapped.get("name", target.name)),
        revision=target.revision,
        definition=wrapped.get("definition", {}),
    )


@router.get(
    "/api/projects/{project_id}/watchlist",
    response_model=WatchlistResponse,
    tags=["projects"],
)
def get_project_watchlist(
    project_id: UUID,
    options: Annotated[WatchlistQueryOptions, Query()] = WatchlistQueryOptions(),
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> WatchlistResponse:
    return _build_watchlist_response(
        str(project_id),
        store,
        market_store,
        options=options,
    )


@router.post(
    "/api/projects/{project_id}/watchlist",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def add_to_project_watchlist(
    project_id: UUID,
    request: WatchlistAddRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> WatchlistResponse:
    clean_id = request.identifier.strip()
    sec = market_store.get_security(clean_id)
    if not sec:
        raise SecurityNotFoundError(clean_id)

    store.add_to_watchlist(str(project_id), sec.security_id)
    return _build_watchlist_response(str(project_id), store, market_store)


@router.delete(
    "/api/projects/{project_id}/watchlist/{security_id}",
    response_model=WatchlistResponse,
    tags=["projects"],
)
def remove_from_project_watchlist(
    project_id: UUID,
    security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> WatchlistResponse:
    store.remove_from_watchlist(str(project_id), security_id)
    return _build_watchlist_response(str(project_id), store, market_store)


@router.post(
    "/api/projects/{project_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["runs"],
)
def create_run(
    project_id: UUID,
    options: Annotated[CreateRunOptions, Query()] = CreateRunOptions(),
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> RunResponse:
    if options.historical and options.dataset_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A historical Run requires a Dataset Version.",
        )
    if options.historical and options.dataset_version_id is not None:
        market_store.ensure_historical_eligibility(options.dataset_version_id)
    dataset_version_ids = [options.dataset_version_id] if options.dataset_version_id else []
    return RunResponse(
        id=store.create_run(str(project_id), dataset_version_ids=dataset_version_ids),
        status="pending",
    )


@router.get(
    "/api/projects/{project_id}/runs",
    response_model=list[RunSummaryResponse],
    tags=["runs"],
)
def list_project_runs(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[RunSummaryResponse]:
    return [
        RunSummaryResponse(
            id=summary.id,
            kind=summary.kind,
            status=summary.status,
            created_at=summary.created_at,
            dataset_version_ids=summary.dataset_version_ids,
            definition_revisions=summary.definition_revisions,
        )
        for summary in store.list_run_summaries(str(project_id))
    ]
