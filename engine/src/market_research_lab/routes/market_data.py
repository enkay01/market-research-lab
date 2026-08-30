"""FastAPI router for securities and market datasets."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi import (
    Path as FastAPIPath,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from ..downloads import download_provider
from ..json_types import JsonValue
from ..market_data import (
    CoverageReport,
    IngestionRequest,
    MarketDataStore,
)
from ..projects import ProjectNotFoundError, ProjectStore
from ..providers import (
    AlpacaDownloadSpec,
    JsonFetcher,
    ProviderCredentials,
    ProviderDownloadError,
    SecEdgarDownloadSpec,
    TiingoDownloadSpec,
)
from .alerts import signal_response
from .deps import (
    SecurityNotFoundError,
    get_market_store,
    get_project_store,
    get_provider_credentials,
    get_provider_fetch_json,
)

router = APIRouter()


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostic_id: str | None = None


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


class DatasetImportResponse(BaseModel):
    dataset_version_id: str


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


class ProviderDownloadRequestBase(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> ProviderDownloadRequestBase:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        return self


class TiingoDownloadRequest(ProviderDownloadRequestBase):
    provider: Literal["tiingo"]
    symbols: list[str] = Field(min_length=1, max_length=500)

    @field_validator("symbols")
    @classmethod
    def normalise_symbols(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        if not cleaned:
            raise ValueError("At least one Tiingo symbol is required.")
        return cleaned

    def to_spec(self) -> TiingoDownloadSpec:
        return TiingoDownloadSpec(
            symbols=tuple(self.symbols),
            start_date=self.start_date,
            end_date=self.end_date,
        )


class AlpacaDownloadRequest(ProviderDownloadRequestBase):
    provider: Literal["alpaca"]
    symbol: str = Field(min_length=1, max_length=16)
    start_date: date
    end_date: date

    @field_validator("symbol")
    @classmethod
    def normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("An Alpaca symbol is required.")
        return cleaned

    def to_spec(self) -> AlpacaDownloadSpec:
        return AlpacaDownloadSpec(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
        )


class SecEdgarDownloadRequest(ProviderDownloadRequestBase):
    provider: Literal["sec_edgar"]
    ciks: list[str] = Field(min_length=1, max_length=500)

    @field_validator("ciks")
    @classmethod
    def normalise_ciks(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw_cik in values:
            cik = raw_cik.strip()
            if not cik:
                continue
            if not cik.isdigit() or len(cik) > 10:
                raise ValueError("SEC EDGAR CIKs must contain up to 10 digits.")
            cleaned.append(cik.zfill(10))
        cleaned = list(dict.fromkeys(cleaned))
        if not cleaned:
            raise ValueError("At least one SEC EDGAR CIK is required.")
        return cleaned

    def to_spec(self) -> SecEdgarDownloadSpec:
        return SecEdgarDownloadSpec(
            ciks=tuple(self.ciks),
            start_date=self.start_date,
            end_date=self.end_date,
        )


ProviderDownloadRequest = Annotated[
    TiingoDownloadRequest | SecEdgarDownloadRequest | AlpacaDownloadRequest,
    Field(discriminator="provider"),
]


class ProviderDownloadResponse(BaseModel):
    dataset_version_id: str
    dataset_version_ids: list[str]


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


@router.get(
    "/api/securities",
    response_model=list[SecurityResponse],
    tags=["securities"],
)
def list_securities(
    query: str | None = Query(default=None, description="Search symbol or name"),
    limit: int = Query(default=50, ge=1, le=500),
    market_store: MarketDataStore = Depends(get_market_store),
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


@router.get(
    "/api/securities/{security_id}",
    response_model=SecuritySummaryResponse,
    tags=["securities"],
)
def get_security_details(
    security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    project_id: UUID | None = Query(
        default=None, description="Optional Project ID for linked valuations/runs"
    ),
    market_store: MarketDataStore = Depends(get_market_store),
    store: ProjectStore = Depends(get_project_store),
) -> SecuritySummaryResponse:
    summary = market_store.get_security_summary(security_id)
    if not summary:
        raise SecurityNotFoundError(security_id)

    valuations: list[dict[str, JsonValue]] = []
    runs: list[dict[str, JsonValue]] = []
    alerts: list[dict[str, JsonValue]] = []
    if project_id:
        with contextlib.suppress(ProjectNotFoundError, OSError, KeyError):
            valuations = store.list_valuations_for_security(
                str(project_id), summary.security.security_id
            )
            runs = store.list_runs_for_security(str(project_id), summary.security.security_id)
            alerts = [
                signal_response(s).model_dump(mode="json")
                for s in store.list_signals_for_security(
                    str(project_id), summary.security.security_id
                )
            ]

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
        alerts=alerts,
    )


@router.post(
    "/api/datasets",
    response_model=DatasetImportResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["datasets"],
)
def import_dataset(
    source: str = Form(...),
    file: UploadFile = File(...),
    market_store: MarketDataStore = Depends(get_market_store),
) -> DatasetImportResponse | JSONResponse:
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
                message=f"Unsupported file format '{ext}'. Allowed formats: .csv, .json, .parquet",
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


@router.get(
    "/api/datasets",
    response_model=list[CoverageResponse],
    tags=["datasets"],
)
def list_datasets(
    market_store: MarketDataStore = Depends(get_market_store),
) -> list[CoverageResponse]:
    return [_coverage_response(report) for report in market_store.list_dataset_versions()]


@router.get(
    "/api/datasets/{dataset_version_id}/coverage",
    response_model=CoverageResponse,
    tags=["datasets"],
)
def get_coverage(
    dataset_version_id: str,
    market_store: MarketDataStore = Depends(get_market_store),
) -> CoverageResponse:
    return _coverage_response(market_store.coverage(dataset_version_id))


@router.get(
    "/api/datasets/{dataset_version_id}/preview",
    response_model=list[dict[str, JsonValue]],
    tags=["datasets"],
)
def get_dataset_preview(
    dataset_version_id: str,
    limit: int = 50,
    market_store: MarketDataStore = Depends(get_market_store),
) -> list[dict[str, JsonValue]]:
    return market_store.preview(dataset_version_id, limit=limit)


@router.get(
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
    market_store: MarketDataStore = Depends(get_market_store),
) -> list[DailyBarResponse]:
    bars = market_store.history(dataset_version_id, symbol=symbol, as_of=as_of)
    return [DailyBarResponse.model_validate(bar, from_attributes=True) for bar in bars]


@router.get(
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
    market_store: MarketDataStore = Depends(get_market_store),
) -> list[FundamentalFactResponse]:
    facts = market_store.fundamentals(dataset_version_id, symbol=symbol, as_of=as_of)
    return [FundamentalFactResponse.model_validate(fact, from_attributes=True) for fact in facts]


@router.get(
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
    market_store: MarketDataStore = Depends(get_market_store),
) -> list[CorporateActionResponse]:
    actions = market_store.corporate_actions(dataset_version_id, symbol=symbol, as_of=as_of)
    return [
        CorporateActionResponse.model_validate(action, from_attributes=True)
        for action in actions
    ]


@router.post(
    "/api/datasets/download",
    response_model=ProviderDownloadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["datasets"],
)
def download_dataset(
    request: ProviderDownloadRequest,
    market_store: MarketDataStore = Depends(get_market_store),
    credentials: ProviderCredentials = Depends(get_provider_credentials),
    provider_fetch_json: JsonFetcher | None = Depends(get_provider_fetch_json),
) -> ProviderDownloadResponse | JSONResponse:
    try:
        versions = download_provider(
            market_store,
            request.to_spec(),
            credentials=credentials,
            fetch_json=provider_fetch_json,
        )
    except ProviderDownloadError as error:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"code": "provider_error", "message": str(error), "details": {}},
        )
    except ValueError as error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "import_error", "message": str(error), "details": {}},
        )
    return ProviderDownloadResponse(
        dataset_version_id=versions[0].id,
        dataset_version_ids=[version.id for version in versions],
    )
