"""Validated HTTP interface for the local application."""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi import (
    Path as FastAPIPath,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .configuration import load_provider_credentials
from .json_types import JsonValue
from .market_data import (
    CoverageReport,
    InadequateTemporalProvenanceError,
    IngestionRequest,
    MarketDataStore,
)
from .projects import Project, ProjectNotFoundError, ProjectStore
from .provider_routes import register_provider_download_route
from .providers import JsonFetcher
from .research import (
    InvalidSecurityIdError,
    ResearchThesis,
    SecurityNotWatchedError,
    default_thesis_template,
)
from .valuation import ComparableCompanyInput, ComparableValuationResult, evaluate_comparables


class SecurityNotFoundError(Exception):
    """Raised when a security is not found in the local catalogue."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Security '{identifier}' was not found in the local catalogue.")
        self.identifier = identifier


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


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
    definition: dict[str, JsonValue]

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class DraftRequest(BaseModel):
    definition: dict[str, JsonValue]


class DraftResponse(BaseModel):
    name: str
    definition: dict[str, JsonValue]
    saved_at: str


class DefinitionResponse(BaseModel):
    revision: str


class RunResponse(BaseModel):
    id: str
    status: str


class DatasetImportResponse(BaseModel):
    dataset_version_id: str


class SecurityResponse(BaseModel):
    security_id: str
    symbol: str
    name: str
    exchange: str | None = None
    currency: str = "USD"


class SecuritySummaryResponse(BaseModel):
    security: SecurityResponse
    daily_bars_count: int = 0
    daily_bars_start: str | None = None
    daily_bars_end: str | None = None
    latest_close: float | None = None
    daily_bars_dataset_versions: list[str] = Field(default_factory=list)
    corporate_actions_count: int = 0
    corporate_actions_dataset_versions: list[str] = Field(default_factory=list)
    fundamentals_count: int = 0
    fundamentals_fiscal_periods: list[str] = Field(default_factory=list)
    fundamentals_dataset_versions: list[str] = Field(default_factory=list)
    covering_dataset_versions: list[str] = Field(default_factory=list)
    valuations: list[dict[str, JsonValue]] = Field(default_factory=list)
    runs: list[dict[str, JsonValue]] = Field(default_factory=list)
    alerts: list[dict[str, JsonValue]] = Field(default_factory=list)


class WatchlistItemResponse(BaseModel):
    security: SecurityResponse
    has_thesis: bool
    thesis_updated_at: str | None = None
    thesis_preview: str | None = None


class WatchlistResponse(BaseModel):
    project_id: str
    items: list[WatchlistItemResponse]
    total: int
    offset: int
    limit: int


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
    incomplete_fields: list[str] | None = None


class ComparableValuationRequest(BaseModel):
    target_security_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    peer_security_ids: list[str] = Field(min_length=1, max_length=50)

    @field_validator("peer_security_ids")
    @classmethod
    def peer_security_ids_are_unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Each peer Security can be selected only once.")
        if any(not value.replace("_", "").replace("-", "").isalnum() for value in values):
            raise ValueError("Peer Security IDs are not valid.")
        return values


class ComparableCompanyInputResponse(BaseModel):
    security_id: str
    symbol: str
    name: str
    currency: str
    market_cap: float | None
    total_debt: float | None
    cash: float | None
    revenue: float | None
    ebitda: float | None
    net_income: float | None
    free_cash_flow: float | None
    dataset_version_ids: list[str]
    provenance: dict[str, str]
    units: dict[str, str]


class ComparableCompanyValuationResponse(BaseModel):
    security_id: str
    symbol: str
    name: str
    currency: str
    market_cap: float | None
    enterprise_value: float | None
    price_to_earnings: float | None
    ev_to_revenue: float | None
    ev_to_ebitda: float | None
    free_cash_flow_yield: float | None
    inputs: ComparableCompanyInputResponse


class ComparableValuationResponse(BaseModel):
    target: ComparableCompanyValuationResponse
    peers: list[ComparableCompanyValuationResponse]
    peer_medians: ComparableCompanyValuationResponse
    warnings: list[str]
    dataset_version_ids: list[str]
    calculated_at: str


class CoverageResponse(BaseModel):
    id: str
    source: str
    retrieval_time: str
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
        retrieval_time=coverage.retrieval_time,
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


_FUNDAMENTAL_FIELDS: dict[str, tuple[str, ...]] = {
    "shares_outstanding": (
        "shares_outstanding",
        "us-gaap:CommonStocksSharesOutstanding",
    ),
    "total_debt": ("total_debt", "us-gaap:LongTermDebt"),
    "cash": ("cash", "cash_and_cash_equivalents", "us-gaap:CashAndCashEquivalentsAtCarryingValue"),
    "revenue": ("revenue", "us-gaap:Revenues", "us-gaap:SalesRevenueNet"),
    "ebitda": ("ebitda",),
    "net_income": ("net_income", "us-gaap:NetIncomeLoss"),
    "free_cash_flow": ("free_cash_flow",),
}


def _comparable_company_input(
    market_store: MarketDataStore, security_id: str
) -> ComparableCompanyInput:
    summary = market_store.get_security_summary(security_id)
    if summary is None:
        raise SecurityNotFoundError(security_id)

    latest_facts: dict[str, tuple[float, str, str, str]] = {}
    aliases = {
        alias.lower(): field_name
        for field_name, field_aliases in _FUNDAMENTAL_FIELDS.items()
        for alias in field_aliases
    }
    for dataset_version_id in summary.fundamentals_dataset_versions:
        facts = market_store.fundamentals(
            dataset_version_id, symbol=summary.security.security_id
        )
        for fact in facts:
            field_name = aliases.get(fact.field.lower())
            if field_name is None:
                continue
            try:
                value = float(fact.value)
            except (TypeError, ValueError):
                continue
            timestamp = fact.available_at or fact.filed_at or fact.fiscal_period
            current = latest_facts.get(field_name)
            if current is None or timestamp >= current[1]:
                latest_facts[field_name] = (value, timestamp, fact.unit, dataset_version_id)

    provenance = {
        field_name: fact[3] for field_name, fact in latest_facts.items()
    }
    shares = latest_facts.get("shares_outstanding")
    market_cap = (
        summary.latest_close * shares[0]
        if summary.latest_close is not None and shares
        else None
    )
    if summary.daily_bars_dataset_versions and market_cap is not None:
        provenance["market_cap"] = summary.daily_bars_dataset_versions[-1]
    units = {field_name: fact[2] for field_name, fact in latest_facts.items()}
    if market_cap is not None:
        units["market_cap"] = summary.security.currency
    return ComparableCompanyInput(
        security_id=summary.security.security_id,
        symbol=summary.security.symbol,
        name=summary.security.name,
        currency=summary.security.currency,
        market_cap=market_cap,
        total_debt=_fact_value(latest_facts, "total_debt"),
        cash=_fact_value(latest_facts, "cash"),
        revenue=_fact_value(latest_facts, "revenue"),
        ebitda=_fact_value(latest_facts, "ebitda"),
        net_income=_fact_value(latest_facts, "net_income"),
        free_cash_flow=_fact_value(latest_facts, "free_cash_flow"),
        dataset_version_ids=tuple(summary.covering_dataset_versions),
        provenance=provenance,
        units=units,
    )


def _fact_value(
    facts: dict[str, tuple[float, str, str, str]], field_name: str
) -> float | None:
    fact = facts.get(field_name)
    return fact[0] if fact else None


def _comparable_valuation_response(
    result: ComparableValuationResult,
) -> ComparableValuationResponse:
    return ComparableValuationResponse.model_validate(result, from_attributes=True)


def _build_watchlist_response(
    project_id: str,
    store: ProjectStore,
    market_store: MarketDataStore,
    *,
    query: str | None = None,
    exchange: str | None = None,
    thesis_status: str | None = None,
    sort_by: str = "symbol",
    sort_order: str = "asc",
    offset: int = 0,
    limit: int = 50,
) -> WatchlistResponse:
    security_ids = store.get_watchlist(project_id)
    all_theses = store.list_theses(project_id)

    raw_items: list[WatchlistItemResponse] = []
    for sec_id in security_ids:
        sec = market_store.get_security(sec_id)
        if not sec:
            continue
        thesis = (
            all_theses.get(sec_id)
            or all_theses.get(sec.security_id)
            or all_theses.get(sec.symbol)
        )
        has_thesis = thesis is not None and bool(thesis.content.strip())
        thesis_updated = thesis.updated_at if thesis else None
        thesis_preview = thesis.summary if thesis else None

        raw_items.append(
            WatchlistItemResponse(
                security=SecurityResponse(
                    security_id=sec.security_id,
                    symbol=sec.symbol,
                    name=sec.name,
                    exchange=sec.exchange,
                    currency=sec.currency,
                ),
                has_thesis=has_thesis,
                thesis_updated_at=thesis_updated,
                thesis_preview=thesis_preview,
            )
        )

    # Filtering (RES-006)
    filtered = raw_items
    if query and query.strip():
        q_lower = query.strip().lower()
        filtered = [
            item
            for item in filtered
            if q_lower in item.security.symbol.lower() or q_lower in item.security.name.lower()
        ]
    if exchange and exchange.strip() and exchange.lower() != "all":
        ex_lower = exchange.strip().lower()
        filtered = [
            item
            for item in filtered
            if item.security.exchange and item.security.exchange.lower() == ex_lower
        ]
    if thesis_status:
        st = thesis_status.strip().lower()
        if st == "has_thesis":
            filtered = [item for item in filtered if item.has_thesis]
        elif st == "no_thesis":
            filtered = [item for item in filtered if not item.has_thesis]

    # Sorting (RES-006)
    reverse = sort_order.lower() == "desc"
    if sort_by == "name":
        filtered.sort(key=lambda item: item.security.name.lower(), reverse=reverse)
    elif sort_by == "exchange":
        filtered.sort(
            key=lambda item: (item.security.exchange or "").lower(), reverse=reverse
        )
    elif sort_by == "thesis_updated_at":
        filtered.sort(key=lambda item: item.thesis_updated_at or "", reverse=reverse)
    else:  # default 'symbol'
        filtered.sort(key=lambda item: item.security.symbol.lower(), reverse=reverse)

    total = len(filtered)
    paged = filtered[offset : offset + limit]

    return WatchlistResponse(
        project_id=project_id,
        items=paged,
        total=total,
        offset=offset,
        limit=limit,
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

    @app.get(
        "/api/securities",
        response_model=list[SecurityResponse],
        tags=["securities"],
    )
    def list_securities(
        query: str | None = Query(default=None, description="Search symbol or name"),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[SecurityResponse]:
        securities = market_store.search_securities(query=query, limit=limit)
        return [
            SecurityResponse(
                security_id=s.security_id,
                symbol=s.symbol,
                name=s.name,
                exchange=s.exchange,
                currency=s.currency,
            )
            for s in securities
        ]

    @app.post(
        "/api/valuations/comparables",
        response_model=ComparableValuationResponse,
        tags=["valuations"],
    )
    def calculate_comparable_valuation(
        request: ComparableValuationRequest,
    ) -> ComparableValuationResponse:
        if request.target_security_id in request.peer_security_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The target Security cannot also be a peer.",
            )
        target = _comparable_company_input(market_store, request.target_security_id)
        peers = [
            _comparable_company_input(market_store, security_id)
            for security_id in request.peer_security_ids
        ]
        result = evaluate_comparables(
            target,
            peers,
            calculated_at=datetime.now(UTC).isoformat(),
        )
        return _comparable_valuation_response(result)

    @app.get(
        "/api/securities/{security_id}",
        response_model=SecuritySummaryResponse,
        tags=["securities"],
    )
    def get_security_details(
        security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
        project_id: UUID | None = Query(
            default=None, description="Optional Project ID for linked valuations/runs"
        ),
    ) -> SecuritySummaryResponse:
        summary = market_store.get_security_summary(security_id)
        if not summary:
            raise SecurityNotFoundError(security_id)

        valuations: list[dict[str, JsonValue]] = []
        runs: list[dict[str, JsonValue]] = []
        if project_id:
            try:
                valuations = store.list_valuations_for_security(
                    str(project_id), summary.security.security_id
                )
                runs = store.list_runs_for_security(
                    str(project_id), summary.security.security_id
                )
            except Exception:
                pass

        return SecuritySummaryResponse(
            security=SecurityResponse(
                security_id=summary.security.security_id,
                symbol=summary.security.symbol,
                name=summary.security.name,
                exchange=summary.security.exchange,
                currency=summary.security.currency,
            ),
            daily_bars_count=summary.daily_bars_count,
            daily_bars_start=summary.daily_bars_start,
            daily_bars_end=summary.daily_bars_end,
            latest_close=summary.latest_close,
            daily_bars_dataset_versions=summary.daily_bars_dataset_versions,
            corporate_actions_count=summary.corporate_actions_count,
            corporate_actions_dataset_versions=summary.corporate_actions_dataset_versions,
            fundamentals_count=summary.fundamentals_count,
            fundamentals_fiscal_periods=summary.fundamentals_fiscal_periods,
            fundamentals_dataset_versions=summary.fundamentals_dataset_versions,
            covering_dataset_versions=summary.covering_dataset_versions,
            valuations=valuations,
            runs=runs,
        )

    @app.get(
        "/api/projects/{project_id}/watchlist",
        response_model=WatchlistResponse,
        tags=["projects"],
    )
    def get_project_watchlist(
        project_id: UUID,
        query: str | None = Query(default=None, description="Filter symbol or name"),
        exchange: str | None = Query(default=None, description="Filter exchange"),
        thesis_status: str | None = Query(
            default=None, description="all | has_thesis | no_thesis"
        ),
        sort_by: str = Query(
            default="symbol", description="symbol | name | exchange | thesis_updated_at"
        ),
        sort_order: str = Query(default="asc", description="asc | desc"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> WatchlistResponse:
        return _build_watchlist_response(
            str(project_id),
            store,
            market_store,
            query=query,
            exchange=exchange,
            thesis_status=thesis_status,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
        )

    @app.post(
        "/api/projects/{project_id}/watchlist",
        response_model=WatchlistResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["projects"],
    )
    def add_to_project_watchlist(
        project_id: UUID,
        request: WatchlistAddRequest,
    ) -> WatchlistResponse:
        clean_id = request.identifier.strip()
        sec = market_store.get_security(clean_id)
        if not sec:
            raise SecurityNotFoundError(clean_id)

        store.add_to_watchlist(str(project_id), sec.security_id)
        return _build_watchlist_response(str(project_id), store, market_store)

    @app.delete(
        "/api/projects/{project_id}/watchlist/{security_id}",
        response_model=WatchlistResponse,
        tags=["projects"],
    )
    def remove_from_project_watchlist(
        project_id: UUID,
        security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    ) -> WatchlistResponse:
        store.remove_from_watchlist(str(project_id), security_id)
        return _build_watchlist_response(str(project_id), store, market_store)

    @app.get(
        "/api/projects/{project_id}/research/{security_id}",
        response_model=ResearchThesisResponse,
        tags=["research"],
    )
    def get_security_thesis(
        project_id: UUID,
        security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    ) -> ResearchThesisResponse:
        thesis = store.get_thesis(str(project_id), security_id)
        if not thesis:
            sec = market_store.get_security(security_id)
            symbol = sec.symbol if sec else security_id
            template = default_thesis_template(symbol)
            return ResearchThesisResponse(
                security_id=security_id,
                content=template,
                updated_at=None,
                summary=None,
            )
        return _thesis_response(thesis)

    @app.put(
        "/api/projects/{project_id}/research/{security_id}",
        response_model=ResearchThesisResponse,
        tags=["research"],
    )
    def save_security_thesis(
        project_id: UUID,
        request: ResearchThesisSaveRequest,
        security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    ) -> ResearchThesisResponse:
        thesis = store.save_thesis(str(project_id), security_id, request.content)
        return _thesis_response(thesis)

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
        "/api/datasets",
        response_model=list[CoverageResponse],
        tags=["datasets"],
    )
    def list_datasets() -> list[CoverageResponse]:
        return [
            _coverage_response(report) for report in market_store.list_dataset_versions()
        ]

    @app.get(
        "/api/datasets/{dataset_version_id}/coverage",
        response_model=CoverageResponse,
        tags=["datasets"],
    )
    def get_coverage(dataset_version_id: str) -> CoverageResponse:
        return _coverage_response(market_store.coverage(dataset_version_id))

    @app.get(
        "/api/datasets/{dataset_version_id}/preview",
        response_model=list[dict[str, JsonValue]],
        tags=["datasets"],
    )
    def get_dataset_preview(dataset_version_id: str, limit: int = 50) -> list[dict[str, JsonValue]]:
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
