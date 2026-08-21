"""Validated HTTP interface for the local application."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, NamedTuple
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
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from .alerts import (
    DataFreshnessState,
    InvalidStrategyDefinitionError,
    SignalRefreshResult,
    data_freshness_state,
    refresh_enabled_strategies,
)
from .alerts import enable_strategy_revision as enable_strategy_revision_domain
from .backtest import (
    BacktestError,
    BacktestParameterError,
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from .configuration import load_provider_credentials
from .indicators import (
    IndicatorCalculationError,
    IndicatorMetadata,
    IndicatorParameter,
    IndicatorPoint,
    IndicatorSeries,
    ParameterValidationError,
    calculate_indicator,
    get_indicator_spec,
    list_indicators,
)
from .json_types import JsonValue
from .market_data import (
    DATASET_TYPE_CORPORATE_ACTIONS,
    CoverageReport,
    InadequateTemporalProvenanceError,
    IngestionRequest,
    MarketDataStore,
)
from .predictive_models import (
    FittedModelArtifact,
    PredictiveModelCalculation,
    PredictiveModelCalculationError,
    PredictiveModelDataError,
    PredictiveModelFold,
    PredictiveModelForecast,
    PredictiveModelMetadata,
    PredictiveModelNotFoundError,
    PredictiveModelOutput,
    PredictiveModelParameter,
    PredictiveModelParameterError,
    get_predictive_model_spec,
    list_predictive_models,
    run_predictive_model,
)
from .projects import (
    BacktestRunRecord,
    FailedBacktestRunRecord,
    FailedPredictiveModelRunRecord,
    PredictiveModelRunRecord,
    Project,
    ProjectNotFoundError,
    ProjectStore,
    RevisionNotFoundError,
    RevisionNotImmutableError,
    ValuationRunRecord,
)
from .provider_routes import register_provider_download_route
from .providers import JsonFetcher
from .research import (
    InvalidSecurityIdError,
    ResearchThesis,
    SecurityNotWatchedError,
    default_thesis_template,
)
from .strategies import (
    MarketView,
    StrategyEvaluation,
    StrategyEvaluationError,
    StrategyMetadata,
    StrategyParameter,
    StrategyParameterValidationError,
    StrategyTarget,
    evaluate_strategy,
    get_strategy_spec,
    list_strategies,
    validate_model_eligibility_for_strategy,
)
from .valuation import (
    ComparableCompanyInput,
    ComparableValuationResult,
    FCFFDCFInput,
    FCFFDCFResult,
    evaluate,
)


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
    input_dataset_versions: dict[str, list[str]]


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
    status: str = "ok"
    has_valuation: bool = True


class ComparableValuationResponse(BaseModel):
    target: ComparableCompanyValuationResponse
    peers: list[ComparableCompanyValuationResponse]
    peer_medians: ComparableCompanyValuationResponse
    warnings: list[str]
    dataset_version_ids: list[str]
    calculated_at: str
    method_revision: str | None = None
    run_id: str | None = None


class FCFFDCFRequest(BaseModel):
    target_security_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    base_revenue: float = Field(gt=0, description="Base period revenue")
    revenue_growth_rate: float = Field(
        ge=-0.99, le=10.0, description="Forecast revenue growth rate"
    )
    operating_margin: float = Field(ge=-1.0, le=1.0, description="Forecast operating margin")
    tax_rate: float = Field(ge=0.0, le=1.0, description="Effective tax rate")
    reinvestment_rate: float = Field(
        ge=0.0, le=2.0, description="Reinvestment rate as fraction of NOPAT"
    )
    wacc: float = Field(gt=0.0, le=1.0, description="Weighted Average Cost of Capital")
    terminal_growth_rate: float = Field(
        ge=-0.1, le=0.2, description="Perpetual terminal growth rate"
    )
    shares_outstanding: float = Field(gt=0.0, description="Shares outstanding")
    total_debt: float = Field(default=0.0, ge=0.0, description="Total debt")
    cash: float = Field(default=0.0, ge=0.0, description="Cash and cash equivalents")
    forecast_years: int = Field(default=5, ge=1, le=20, description="Number of forecast years")
    revenue_growth_rates: list[float] | None = None
    operating_margins: list[float] | None = None
    reinvestment_rates: list[float] | None = None


class FCFFDCFSeedResponse(BaseModel):
    security_id: str
    symbol: str
    name: str
    currency: str
    base_revenue: float | None = None
    operating_margin: float = 0.20
    tax_rate: float = 0.21
    reinvestment_rate: float = 0.20
    wacc: float = 0.085
    terminal_growth_rate: float = 0.025
    revenue_growth_rate: float = 0.07
    shares_outstanding: float | None = None
    total_debt: float = 0.0
    cash: float = 0.0
    market_cap: float | None = None
    latest_price: float | None = None
    forecast_years: int = 5
    dataset_version_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CashFlowForecastYearResponse(BaseModel):
    year: int
    revenue: float
    revenue_growth: float
    operating_income: float
    tax: float
    nopat: float
    reinvestment: float
    free_cash_flow: float
    discount_factor: float
    present_value: float


class ScenarioResponse(BaseModel):
    name: str
    wacc: float
    terminal_growth_rate: float
    revenue_growth_rate: float
    operating_margin: float
    enterprise_value: float | None
    equity_value: float | None
    value_per_share: float | None


class SensitivityMatrixResponse(BaseModel):
    wacc_values: list[float]
    terminal_growth_values: list[float]
    grid: list[list[float | None]]


class FCFFDCFInputResponse(BaseModel):
    base_revenue: float
    revenue_growth_rate: float
    operating_margin: float
    tax_rate: float
    reinvestment_rate: float
    wacc: float
    terminal_growth_rate: float
    shares_outstanding: float
    total_debt: float
    cash: float
    forecast_years: int
    provenance: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    input_warnings: list[str] = Field(default_factory=list)


class FCFFDCFValuationResponse(BaseModel):
    security_id: str
    symbol: str
    name: str
    currency: str
    forecast_years: int
    forecast_cash_flows: list[CashFlowForecastYearResponse]
    terminal_cash_flow: float | None
    terminal_value: float | None
    pv_terminal_value: float | None
    terminal_value_contribution: float | None
    enterprise_value: float | None
    cash: float
    total_debt: float
    equity_value: float | None
    shares_outstanding: float
    value_per_share: float | None
    scenarios: list[ScenarioResponse]
    sensitivity: SensitivityMatrixResponse
    warnings: list[str]
    dataset_version_ids: list[str]
    calculated_at: str
    inputs: FCFFDCFInputResponse | None = None
    provenance: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    method_revision: str | None = None
    run_id: str | None = None


class ValuationComparisonItemResponse(BaseModel):
    run_id: str
    method: str
    method_revision: str
    security_id: str
    symbol: str
    name: str
    currency: str
    calculated_at: str
    value_per_share: float | None = None
    enterprise_value: float | None = None
    equity_value: float | None = None
    terminal_value_contribution: float | None = None
    price_to_earnings: float | None = None
    ev_to_revenue: float | None = None
    ev_to_ebitda: float | None = None
    free_cash_flow_yield: float | None = None
    key_assumptions: dict[str, JsonValue] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    dataset_version_ids: list[str] = Field(default_factory=list)


class ValuationComparisonRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=10)


class ValuationComparisonResponse(BaseModel):
    items: list[ValuationComparisonItemResponse]
    compared_at: str


class SavedValuationResponse(BaseModel):
    run_id: str
    method_revision: str
    calculated_at: str
    result: dict[str, JsonValue]


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


class IndicatorParameterResponse(BaseModel):
    name: str
    param_type: str
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: list[str] | None = None


class IndicatorMetadataResponse(BaseModel):
    name: str
    display_name: str
    description: str
    parameters: list[IndicatorParameterResponse]
    outputs: list[str]


class IndicatorPointResponse(BaseModel):
    session_date: str
    price: float
    values: dict[str, JsonValue]
    is_warmup: bool


class IndicatorCalculateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    dataset_version_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1, max_length=32)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    as_of: datetime | None = None
    price_field: str = Field(default="close", pattern=r"^(close|open|high|low)$")


class IndicatorSeriesResponse(BaseModel):
    indicator_name: str
    dataset_version_id: str
    symbol: str
    parameters: dict[str, JsonValue]
    total_bars: int
    warmup_period: int
    valid_bars: int
    points: list[IndicatorPointResponse]


class PredictiveModelParameterResponse(BaseModel):
    name: str
    param_type: str
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: list[str] | None = None


class PredictiveModelMetadataResponse(BaseModel):
    name: str
    display_name: str
    description: str
    target: str
    horizon: int
    features: list[str]
    training_window: int
    parameters: list[PredictiveModelParameterResponse]
    output_meaning: str
    outputs: list[str]


class PredictiveModelRunRequest(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_]{1,64}$")
    dataset_version_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1, max_length=32)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    seed: int | None = Field(default=None, ge=0)
    as_of: datetime | None = None


class PredictiveModelArtifactResponse(BaseModel):
    model_name: str
    feature_name: str
    target_name: str
    horizon: int
    intercept: float
    coefficient: float
    training_start: str
    training_end: str
    training_observations: int
    parameters: dict[str, JsonValue]
    seed: int | None
    training_metrics: dict[str, float]
    feature_definition: dict[str, JsonValue] = Field(default_factory=dict)
    preprocessing: dict[str, JsonValue] = Field(default_factory=dict)


class PredictiveModelSplitResponse(BaseModel):
    period: Literal["training", "validation", "test"]
    start: str
    end: str
    feature_start: str
    feature_end: str
    observations: int
    labelled_observations: int
    fit_scope: str


class PredictiveModelPeriodMetricsResponse(BaseModel):
    period: Literal["training", "validation", "test"]
    observations: int
    metrics: dict[str, float]
    benchmark_metrics: dict[str, float] = Field(default_factory=dict)
    comparison: dict[str, JsonValue] = Field(default_factory=dict)
    sample_scope: Literal["in_sample", "validation", "out_of_sample"]


class NaiveBenchmarkEvaluationResponse(BaseModel):
    name: str
    display_name: str
    description: str
    period_metrics: dict[str, dict[str, float]]
    out_of_sample_comparison: dict[str, JsonValue]
    completed: bool = False


class PredictiveModelPredictionResponse(BaseModel):
    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: float
    target_date: str | None = None
    period: Literal["training", "validation", "test"] | None = None


class PredictiveModelForecastResponse(BaseModel):
    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: None = None
    target_date: None = None
    period: None = None


class PredictiveModelFoldResponse(BaseModel):
    fold_index: int
    period: Literal["validation", "test"]
    prediction_session_date: str
    target_date: str | None
    training_start: str
    training_end: str
    training_observations: int
    fit_scope: str
    artifact: PredictiveModelArtifactResponse
    prediction: PredictiveModelPredictionResponse | PredictiveModelForecastResponse
    metrics: dict[str, float]


class PredictiveModelRunResponse(BaseModel):
    run_id: str | None = None
    model_revision: str | None = None
    status: Literal["preview", "completed"] = "preview"
    model_name: str
    display_name: str
    description: str
    symbol: str
    dataset_version_id: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    seed: int | None
    target: str
    horizon: int
    features: list[str]
    training_window: int
    output_meaning: str
    outputs: list[str]
    artifact: PredictiveModelArtifactResponse
    predictions: list[PredictiveModelPredictionResponse | PredictiveModelForecastResponse]
    metrics: dict[str, float]
    training_start: str
    training_end: str
    completed_at: str | None = None
    as_of: datetime | None = None
    out_of_sample_status: str
    evaluation_mode: Literal["holdout", "expanding", "rolling"] = "holdout"
    splits: list[PredictiveModelSplitResponse] = Field(default_factory=list)
    period_metrics: list[PredictiveModelPeriodMetricsResponse] = Field(default_factory=list)
    fold_artifacts: list[PredictiveModelArtifactResponse] = Field(default_factory=list)
    folds: list[PredictiveModelFoldResponse] = Field(default_factory=list)
    benchmark: NaiveBenchmarkEvaluationResponse | None = None
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    is_eligible_for_strategy: bool = False
    eligibility_reason: str = (
        "Predictive Model is not eligible for a Strategy until the naive benchmark "
        "comparison is complete."
    )


@dataclass(frozen=True)
class PredictiveModelResponseContext:
    """Run identity added when a calculation is previewed or persisted."""

    symbol: str
    dataset_version_id: str
    run_id: str = ""
    model_revision: str = ""
    status: Literal["preview", "completed"] = "preview"
    completed_at: str | None = None
    as_of: datetime | None = None


class StrategyParameterResponse(BaseModel):
    name: str
    param_type: str
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: list[str] | None = None


class StrategyMetadataResponse(BaseModel):
    name: str
    display_name: str
    description: str
    parameters: list[StrategyParameterResponse]
    outputs: list[str]


class StrategyTargetResponse(BaseModel):
    security_id: str
    weight: float
    decision_time: str
    rationale: str
    indicator_state: str | None = None


class StrategyEvaluateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    dataset_version_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1, max_length=32)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    as_of: datetime | None = None
    price_field: str = Field(default="close", pattern=r"^(close|open|high|low)$")


class StrategyEvaluationResponse(BaseModel):
    strategy_name: str
    symbol: str
    dataset_version_id: str
    parameters: dict[str, JsonValue]
    decision_time: str
    targets: list[StrategyTargetResponse]
    indicator_name: str | None = None
    latest_session_date: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SavedStrategyEvaluationResponse(StrategyEvaluationResponse):
    revision: str
    strategy_revision: str


class SavedStrategyRevisionResponse(BaseModel):
    name: str
    revision: str
    saved_at: str


class EnabledStrategyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    revision: str = Field(min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        return _non_blank_name(value)


class EnabledStrategyResponse(BaseModel):
    name: str
    revision: str
    enabled_at: str


class SignalResponse(BaseModel):
    signal_id: str
    strategy_name: str
    strategy_revision: str
    security_id: str
    action: str
    weight: float
    decision_time: str
    data_time: str
    dataset_version_id: str
    rationale: str
    indicator_state: str | None = None
    created_at: str = ""
    data_state: DataFreshnessState = "stale-data"


def signal_response(signal: dict[str, JsonValue]) -> SignalResponse:
    """Build one Alert response with freshness classified at read time (ALT-004)."""
    body = dict(signal)
    body["data_state"] = data_freshness_state(
        str(body.get("data_time", "")), now=datetime.now(UTC)
    )
    return SignalResponse.model_validate(body)


class DefinitionRevisionResponse(BaseModel):
    kind: str
    name: str
    revision: str
    definition: JsonValue
    saved_at: str = ""


class SignalRefreshFailureResponse(BaseModel):
    strategy_revision: str
    error: str


class SignalRefreshResponse(BaseModel):
    signals: list[SignalResponse] = Field(default_factory=list)
    failures: list[SignalRefreshFailureResponse] = Field(default_factory=list)


class ExecutionModelAssumptionsRequest(BaseModel):
    schedule: Literal["daily"] = "daily"
    commission_rate: float = Field(default=0.0, ge=0)
    slippage_rate: float = Field(default=0.0, ge=0, lt=1)
    allow_shorting: bool = True
    borrow_fee_rate: float = Field(default=0.0, ge=0)
    cash_interest_rate: float = Field(default=0.0, allow_inf_nan=False)
    unavailable_borrow: list[str] = Field(default_factory=list)
    max_leverage: float = Field(default=1.0, gt=0)
    margin_requirement: float = Field(default=1.0, gt=0)
    maintenance_margin: float = Field(default=0.25, ge=0)
    leverage_mode: Literal["reject", "constrain"] = "reject"


class BacktestRunRequest(BaseModel):
    strategy_name: str = Field(min_length=1, max_length=64)
    strategy_revision: str = Field(min_length=1, max_length=64)
    dataset_version_id: str = Field(min_length=1)
    symbol: str | None = Field(default=None, max_length=32)
    symbols: list[str] | None = None
    benchmark_symbol: str | None = Field(default=None, max_length=32)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    starting_cash: float = Field(gt=0)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    price_field: Literal["close", "open", "high", "low"] = "close"
    calendar: Literal["US", "none"] = "none"
    execution: ExecutionModelAssumptionsRequest = Field(
        default_factory=ExecutionModelAssumptionsRequest
    )

    @model_validator(mode="after")
    def validate_symbols(self) -> BacktestRunRequest:
        if not self.symbol and not self.symbols:
            raise ValueError("Either 'symbol' or 'symbols' must be provided.")
        if self.symbols is not None and len(self.symbols) == 0:
            raise ValueError("'symbols' must not be empty.")
        return self


class FillResponse(BaseModel):
    trade_id: str
    security_id: str
    session_date: str
    decision_time: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    notional: float
    commission: float
    slippage_cost: float
    rationale: str


class PositionSnapshotResponse(BaseModel):
    shares: float
    close_price: float
    position_value: float
    weight: float


class ConstraintRejectionResponse(BaseModel):
    session_date: str
    security_id: str
    rule: str
    reason: str
    requested_weight: float | None = None


class LedgerRowResponse(BaseModel):
    session_date: str
    signal_weight: float | None = None
    signal_decision_time: str | None = None
    fill: FillResponse | None = None
    shares: float
    close_price: float
    cash: float
    position_value: float
    portfolio_value: float
    positions: dict[str, PositionSnapshotResponse] = Field(default_factory=dict)
    signal_weights: dict[str, float] = Field(default_factory=dict)
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    borrow_fees: float = 0.0
    cash_interest: float = 0.0
    dividends: float = 0.0
    splits: dict[str, float] = Field(default_factory=dict)
    delistings: list[str] = Field(default_factory=list)


class TradeResponse(BaseModel):
    trade_id: str
    security_id: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_cost: float
    exit_proceeds: float
    pnl: float
    return_pct: float


class EquityPointResponse(BaseModel):
    session_date: str
    equity: float
    drawdown: float


class ExecutionModelAssumptionsResponse(BaseModel):
    schedule: str = "daily"
    commission_rate: float = 0.0
    slippage_rate: float = 0.0
    allow_shorting: bool = True
    borrow_fee_rate: float = 0.0
    cash_interest_rate: float = 0.0
    unavailable_borrow: list[str] = Field(default_factory=list)
    max_leverage: float = 1.0
    margin_requirement: float = 1.0
    maintenance_margin: float = 0.25
    leverage_mode: str = "reject"


class BacktestSpecificationResponse(BaseModel):
    strategy_name: str
    strategy_revision: str
    dataset_version_id: str
    security_id: str = ""
    start_date: str = ""
    end_date: str = ""
    starting_cash: float = 100000.0
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    price_field: str = "close"
    calendar: str = "none"
    execution: ExecutionModelAssumptionsResponse = Field(
        default_factory=ExecutionModelAssumptionsResponse
    )
    universe: list[str] = Field(default_factory=list)
    benchmark_security_id: str | None = None


class BacktestMetricsResponse(BaseModel):
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    hit_rate: float | None = None
    turnover: float
    gross_exposure: float
    net_exposure: float
    benchmark_relative_return: float | None = None
    num_trades: int
    num_fills: int


class BacktestResultResponse(BaseModel):
    run_id: str | None = None
    strategy_revision: str | None = None
    specification: BacktestSpecificationResponse
    signals: list[StrategyTargetResponse]
    fills: list[FillResponse]
    trades: list[TradeResponse]
    ledger: list[LedgerRowResponse]
    equity_curve: list[EquityPointResponse]
    drawdown_curve: list[EquityPointResponse]
    metrics: BacktestMetricsResponse
    warnings: list[str]
    manifest: dict[str, JsonValue]
    benchmark_equity_curve: list[EquityPointResponse] = Field(default_factory=list)
    rejections: list[ConstraintRejectionResponse] = Field(default_factory=list)


class BacktestComparisonItemResponse(BaseModel):
    run_id: str
    strategy_name: str
    strategy_revision: str
    universe: list[str]
    start_date: str
    end_date: str
    starting_cash: float
    benchmark_security_id: str | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    execution: ExecutionModelAssumptionsResponse
    metrics: BacktestMetricsResponse
    costs: dict[str, JsonValue] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    dataset_version_ids: list[str] = Field(default_factory=list)


class BacktestComparisonRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1)


class BacktestComparisonResponse(BaseModel):
    items: list[BacktestComparisonItemResponse]
    compared_at: str


def _backtest_result_response(
    result: dict[str, JsonValue],
    *,
    run_id: str | None = None,
    strategy_revision: str | None = None,
) -> BacktestResultResponse:
    """Merge Run identity onto a Backtest result payload and validate it."""
    return BacktestResultResponse.model_validate(
        {**result, "run_id": run_id, "strategy_revision": strategy_revision}
    )


def _indicator_param_response(param: IndicatorParameter) -> IndicatorParameterResponse:
    return IndicatorParameterResponse(
        name=param.name,
        param_type=param.param_type,
        default=param.default,
        description=param.description,
        min_value=param.min_value,
        max_value=param.max_value,
        options=param.options,
    )


def _indicator_meta_response(spec: IndicatorMetadata) -> IndicatorMetadataResponse:
    return IndicatorMetadataResponse(
        name=spec.name,
        display_name=spec.display_name,
        description=spec.description,
        parameters=[_indicator_param_response(p) for p in spec.parameters],
        outputs=spec.outputs,
    )


def _indicator_point_response(pt: IndicatorPoint) -> IndicatorPointResponse:
    return IndicatorPointResponse(
        session_date=pt.session_date,
        price=pt.price,
        values=pt.values,
        is_warmup=pt.is_warmup,
    )


def _indicator_series_response(
    series: IndicatorSeries,
    *,
    dataset_version_id: str,
    symbol: str,
) -> IndicatorSeriesResponse:
    return IndicatorSeriesResponse(
        indicator_name=series.indicator_name,
        dataset_version_id=dataset_version_id,
        symbol=symbol,
        parameters=series.parameters,
        total_bars=series.total_bars,
        warmup_period=series.warmup_period,
        valid_bars=series.valid_bars,
        points=[_indicator_point_response(p) for p in series.points],
    )


def _predictive_parameter_response(
    parameter: PredictiveModelParameter,
) -> PredictiveModelParameterResponse:
    return PredictiveModelParameterResponse(
        name=parameter.name,
        param_type=parameter.param_type,
        default=parameter.default,
        description=parameter.description,
        min_value=parameter.min_value,
        max_value=parameter.max_value,
        options=list(parameter.options) if parameter.options else None,
    )


def _predictive_metadata_response(
    metadata: PredictiveModelMetadata,
) -> PredictiveModelMetadataResponse:
    return PredictiveModelMetadataResponse(
        name=metadata.name,
        display_name=metadata.display_name,
        description=metadata.description,
        target=metadata.target,
        horizon=metadata.horizon,
        features=list(metadata.features),
        training_window=metadata.training_window,
        parameters=[_predictive_parameter_response(p) for p in metadata.parameters],
        output_meaning=metadata.output_meaning,
        outputs=list(metadata.outputs),
    )


def _predictive_artifact_response(
    artifact: FittedModelArtifact,
) -> PredictiveModelArtifactResponse:
    metrics = {
        name: float(value)
        for name, value in artifact.training_metrics.items()
        if isinstance(value, (int, float))
    }
    return PredictiveModelArtifactResponse(
        model_name=artifact.model_name,
        feature_name=artifact.feature_name,
        target_name=artifact.target_name,
        horizon=artifact.horizon,
        intercept=artifact.intercept,
        coefficient=artifact.coefficient,
        training_start=artifact.training_start,
        training_end=artifact.training_end,
        training_observations=artifact.training_observations,
        parameters=artifact.parameters,
        seed=artifact.seed,
        training_metrics=metrics,
        feature_definition=artifact.feature_definition,
        preprocessing=artifact.preprocessing,
    )


def _predictive_prediction_response(
    prediction: PredictiveModelOutput,
) -> PredictiveModelPredictionResponse | PredictiveModelForecastResponse:
    if isinstance(prediction, PredictiveModelForecast):
        return PredictiveModelForecastResponse(
            session_date=prediction.session_date,
            feature_value=prediction.feature_value,
            predicted_value=prediction.predicted_value,
            actual_target=prediction.actual_target,
            target_date=prediction.target_date,
            period=prediction.period,
        )
    return PredictiveModelPredictionResponse(
        session_date=prediction.session_date,
        feature_value=prediction.feature_value,
        predicted_value=prediction.predicted_value,
        actual_target=prediction.actual_target,
        target_date=prediction.target_date,
        period=prediction.period,
    )


def _predictive_fold_response(fold: PredictiveModelFold) -> PredictiveModelFoldResponse:
    return PredictiveModelFoldResponse(
        fold_index=fold.fold_index,
        period=fold.period,
        prediction_session_date=fold.prediction_session_date,
        target_date=fold.target_date,
        training_start=fold.training_start,
        training_end=fold.training_end,
        training_observations=fold.training_observations,
        fit_scope=fold.fit_scope,
        artifact=_predictive_artifact_response(fold.artifact),
        prediction=_predictive_prediction_response(fold.prediction),
        metrics=fold.metrics,
    )


def _predictive_run_response(
    calculation: PredictiveModelCalculation,
    context: PredictiveModelResponseContext,
) -> PredictiveModelRunResponse:
    metadata = calculation.metadata
    return PredictiveModelRunResponse(
        run_id=context.run_id or None,
        model_revision=context.model_revision or None,
        status=context.status,
        model_name=metadata.name,
        display_name=metadata.display_name,
        description=metadata.description,
        symbol=context.symbol,
        dataset_version_id=context.dataset_version_id,
        dataset_version_ids=[context.dataset_version_id],
        parameters=calculation.parameters,
        seed=calculation.seed,
        target=metadata.target,
        horizon=metadata.horizon,
        features=list(metadata.features),
        training_window=int(calculation.parameters["training_window"]),
        output_meaning=metadata.output_meaning,
        outputs=list(metadata.outputs),
        artifact=_predictive_artifact_response(calculation.artifact),
        predictions=[_predictive_prediction_response(p) for p in calculation.predictions],
        metrics=calculation.metrics,
        training_start=calculation.training_start,
        training_end=calculation.training_end,
        completed_at=context.completed_at,
        as_of=context.as_of,
        out_of_sample_status=calculation.out_of_sample_status,
        evaluation_mode=calculation.evaluation.mode,
        splits=[
            PredictiveModelSplitResponse(
                period=split.period,
                start=split.start,
                end=split.end,
                feature_start=split.feature_start,
                feature_end=split.feature_end,
                observations=split.observations,
                labelled_observations=split.labelled_observations,
                fit_scope=split.fit_scope,
            )
            for split in calculation.evaluation.splits
        ],
        period_metrics=[
            PredictiveModelPeriodMetricsResponse(
                period=period_metrics.period,
                observations=period_metrics.observations,
                metrics=period_metrics.metrics,
                benchmark_metrics=period_metrics.benchmark_metrics,
                comparison=period_metrics.comparison,
                sample_scope=period_metrics.sample_scope,
            )
            for period_metrics in calculation.evaluation.period_metrics
        ],
        fold_artifacts=[
            _predictive_artifact_response(fold_artifact)
            for fold_artifact in calculation.fold_artifacts
        ],
        folds=[_predictive_fold_response(fold) for fold in calculation.evaluation.folds],
        benchmark=(
            NaiveBenchmarkEvaluationResponse(
                name=calculation.evaluation.benchmark.name,
                display_name=calculation.evaluation.benchmark.display_name,
                description=calculation.evaluation.benchmark.description,
                period_metrics=calculation.evaluation.benchmark.period_metrics,
                out_of_sample_comparison=(
                    calculation.evaluation.benchmark.out_of_sample_comparison
                ),
                completed=calculation.evaluation.benchmark.completed,
            )
            if calculation.evaluation.benchmark
            else None
        ),
        assumptions=list(calculation.evaluation.assumptions),
        warnings=list(calculation.evaluation.warnings),
        limitations=list(calculation.evaluation.limitations),
        unsupported_claims=list(calculation.evaluation.unsupported_claims),
        is_eligible_for_strategy=calculation.evaluation.is_eligible_for_strategy,
        eligibility_reason=calculation.evaluation.eligibility_reason,
    )


def _normalize_predictive_model_result(
    result: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Fill period scope for legacy Runs without changing persisted artifacts."""
    raw_period_metrics = result.get("period_metrics")
    if not isinstance(raw_period_metrics, list):
        return result

    scopes = {
        "training": "in_sample",
        "validation": "validation",
        "test": "out_of_sample",
    }
    normalized = dict(result)
    normalized_period_metrics: list[JsonValue] = []
    for raw_metric in raw_period_metrics:
        if not isinstance(raw_metric, dict):
            normalized_period_metrics.append(raw_metric)
            continue
        metric = dict(raw_metric)
        if "sample_scope" not in metric:
            period = metric.get("period")
            scope = scopes.get(period) if isinstance(period, str) else None
            if scope is not None:
                metric["sample_scope"] = scope
        normalized_period_metrics.append(metric)
    normalized["period_metrics"] = normalized_period_metrics
    return normalized


def _predictive_model_calculation(
    market_store: MarketDataStore,
    request: PredictiveModelRunRequest,
) -> PredictiveModelCalculation:
    try:
        bars = market_store.history(
            request.dataset_version_id,
            symbol=request.symbol,
            as_of=request.as_of,
        )
    except InadequateTemporalProvenanceError:
        raise
    except ValueError as error:
        raise PredictiveModelDataError(str(error)) from error
    if not bars:
        raise PredictiveModelDataError(
            f"No price history found for symbol '{request.symbol}' "
            f"in dataset '{request.dataset_version_id}'."
        )
    return run_predictive_model(
        request.name,
        bars,
        request.parameters,
        request.seed,
    )


def _persist_failed_predictive_model_run(
    store: ProjectStore,
    project_id: UUID,
    request: PredictiveModelRunRequest,
    error: Exception,
) -> None:
    """Preserve a failed saved-model request before returning its original error."""
    store.create_failed_predictive_model_run(
        str(project_id),
        FailedPredictiveModelRunRecord(
            model_revision=f"{request.name}:{request.symbol}:failed",
            dataset_version_ids=[request.dataset_version_id],
            parameters=dict(request.parameters),
            as_of=request.as_of.isoformat() if request.as_of else None,
            error_message=str(error),
        ),
    )


def _strategy_param_response(param: StrategyParameter) -> StrategyParameterResponse:
    return StrategyParameterResponse(
        name=param.name,
        param_type=param.param_type,
        default=param.default,
        description=param.description,
        min_value=param.min_value,
        max_value=param.max_value,
        options=param.options,
    )


def _strategy_meta_response(spec: StrategyMetadata) -> StrategyMetadataResponse:
    return StrategyMetadataResponse(
        name=spec.name,
        display_name=spec.display_name,
        description=spec.description,
        parameters=[_strategy_param_response(p) for p in spec.parameters],
        outputs=spec.outputs,
    )


def _strategy_target_response(target: StrategyTarget) -> StrategyTargetResponse:
    return StrategyTargetResponse(
        security_id=target.security_id,
        weight=target.weight,
        decision_time=target.decision_time,
        rationale=target.rationale,
        indicator_state=target.indicator_state,
    )


def _strategy_evaluation_response(
    evaluation: StrategyEvaluation,
    *,
    symbol: str,
    dataset_version_id: str,
) -> StrategyEvaluationResponse:
    return StrategyEvaluationResponse(
        strategy_name=evaluation.strategy_name,
        symbol=symbol,
        dataset_version_id=dataset_version_id,
        parameters=evaluation.parameters,
        decision_time=evaluation.decision_time,
        targets=[_strategy_target_response(t) for t in evaluation.targets],
        indicator_name=evaluation.indicator_name,
        latest_session_date=evaluation.latest_session_date,
        warnings=list(evaluation.warnings),
    )


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

    latest_facts: dict[str, tuple[float, tuple[int, str], str, str]] = {}
    aliases = {
        alias.lower(): field_name
        for field_name, field_aliases in _FUNDAMENTAL_FIELDS.items()
        for alias in field_aliases
    }
    for dataset_version_id in summary.fundamentals_dataset_versions:
        facts = market_store.fundamentals(dataset_version_id, symbol=summary.security.security_id)
        for fact in facts:
            field_name = aliases.get(fact.field.lower())
            if field_name is None:
                continue
            try:
                value = float(fact.value)
            except (TypeError, ValueError):
                continue
            timestamp = _fact_order(fact.available_at, fact.filed_at, fact.fiscal_period)
            current = latest_facts.get(field_name)
            if current is None or timestamp >= current[1]:
                latest_facts[field_name] = (value, timestamp, fact.unit, dataset_version_id)

    provenance = {field_name: fact[3] for field_name, fact in latest_facts.items()}
    input_warnings: list[str] = []
    financial_fields = (
        "total_debt",
        "cash",
        "revenue",
        "ebitda",
        "net_income",
        "free_cash_flow",
    )
    values = {field_name: _fact_value(latest_facts, field_name) for field_name in financial_fields}
    for field_name in financial_fields:
        fact = latest_facts.get(field_name)
        if fact is not None and fact[2].upper() != summary.security.currency.upper():
            input_warnings.append(
                f"{summary.security.symbol}: {field_name} unit {fact[2]} is not "
                f"compatible with currency {summary.security.currency}."
            )
            values[field_name] = None
    shares = latest_facts.get("shares_outstanding")
    if shares is not None and shares[2].lower() not in {"share", "shares", "count"}:
        input_warnings.append(
            f"{summary.security.symbol}: shares_outstanding unit {shares[2]} is not valid."
        )
        shares = None
    market_cap = (
        summary.latest_close * shares[0] if summary.latest_close is not None and shares else None
    )
    if summary.daily_bars_dataset_versions and market_cap is not None:
        provenance["market_cap"] = summary.daily_bars_dataset_versions[-1]
    units = {field_name: fact[2] for field_name, fact in latest_facts.items()}
    if market_cap is not None:
        units["market_cap"] = summary.security.currency
    input_dataset_versions = {field_name: (fact[3],) for field_name, fact in latest_facts.items()}
    if market_cap is not None and shares is not None:
        bar_version = summary.daily_bars_dataset_versions[-1]
        input_dataset_versions["market_cap"] = tuple(dict.fromkeys((bar_version, shares[3])))
    return ComparableCompanyInput(
        security_id=summary.security.security_id,
        symbol=summary.security.symbol,
        name=summary.security.name,
        currency=summary.security.currency,
        market_cap=market_cap,
        total_debt=values["total_debt"],
        cash=values["cash"],
        revenue=values["revenue"],
        ebitda=values["ebitda"],
        net_income=values["net_income"],
        free_cash_flow=values["free_cash_flow"],
        dataset_version_ids=tuple(summary.covering_dataset_versions),
        provenance=provenance,
        units=units,
        input_dataset_versions=input_dataset_versions,
        input_warnings=tuple(input_warnings),
    )


def _fact_value(
    facts: dict[str, tuple[float, tuple[int, str], str, str]], field_name: str
) -> float | None:
    fact = facts.get(field_name)
    return fact[0] if fact else None


def _comparable_valuation_response(
    result: ComparableValuationResult,
    *,
    method_revision: str | None = None,
    run_id: str | None = None,
) -> ComparableValuationResponse:
    response = ComparableValuationResponse.model_validate(result, from_attributes=True)
    return response.model_copy(update={"method_revision": method_revision, "run_id": run_id})


class FactSortKey(NamedTuple):
    priority: int
    key: str


def _fact_order(available_at: str | None, filed_at: str | None, fiscal_period: str) -> FactSortKey:
    for timestamp in (available_at, filed_at):
        if timestamp:
            try:
                return FactSortKey(
                    1, datetime.fromisoformat(timestamp.replace("Z", "+00:00")).isoformat()
                )
            except ValueError:
                return FactSortKey(1, timestamp)
    return FactSortKey(0, fiscal_period)


def _calculate_comparable_result(
    market_store: MarketDataStore, request: ComparableValuationRequest
) -> ComparableValuationResult:
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
    return evaluate(
        "trading_comparables",
        target,
        peers,
        calculated_at=datetime.now(UTC).isoformat(),
    )


def _dcf_company_seed(market_store: MarketDataStore, security_id: str) -> FCFFDCFSeedResponse:
    company = _comparable_company_input(market_store, security_id)
    summary = market_store.get_security_summary(security_id)
    latest_price = summary.latest_close if summary else None

    shares = (
        company.market_cap / latest_price
        if (company.market_cap is not None and latest_price is not None and latest_price > 0)
        else None
    )

    revenue = company.revenue
    ebitda = company.ebitda
    margin = (ebitda / revenue) if (revenue and ebitda and revenue > 0) else 0.20
    margin = max(0.01, min(0.60, margin))

    warnings = list(company.input_warnings)
    if revenue is None or revenue <= 0:
        warnings.append(
            f"{company.symbol}: Historical revenue not found; please specify base revenue."
        )
    if shares is None or shares <= 0:
        warnings.append(
            f"{company.symbol}: Shares outstanding not found; please specify shares outstanding."
        )

    return FCFFDCFSeedResponse(
        security_id=company.security_id,
        symbol=company.symbol,
        name=company.name,
        currency=company.currency,
        base_revenue=revenue,
        operating_margin=margin,
        tax_rate=0.21,
        reinvestment_rate=0.20,
        wacc=0.085,
        terminal_growth_rate=0.025,
        revenue_growth_rate=0.07,
        shares_outstanding=shares,
        total_debt=company.total_debt or 0.0,
        cash=company.cash or 0.0,
        market_cap=company.market_cap,
        latest_price=latest_price,
        forecast_years=5,
        dataset_version_ids=list(company.dataset_version_ids),
        provenance=company.provenance,
        units=company.units,
        warnings=warnings,
    )


def _calculate_dcf_result(market_store: MarketDataStore, request: FCFFDCFRequest) -> FCFFDCFResult:
    company = _comparable_company_input(market_store, request.target_security_id)
    dcf_input = FCFFDCFInput(
        security_id=company.security_id,
        symbol=company.symbol,
        name=company.name,
        currency=company.currency,
        base_revenue=request.base_revenue,
        revenue_growth_rate=request.revenue_growth_rate,
        operating_margin=request.operating_margin,
        tax_rate=request.tax_rate,
        reinvestment_rate=request.reinvestment_rate,
        wacc=request.wacc,
        terminal_growth_rate=request.terminal_growth_rate,
        shares_outstanding=request.shares_outstanding,
        total_debt=request.total_debt,
        cash=request.cash,
        forecast_years=request.forecast_years,
        revenue_growth_rates=tuple(request.revenue_growth_rates or ()),
        operating_margins=tuple(request.operating_margins or ()),
        reinvestment_rates=tuple(request.reinvestment_rates or ()),
        dataset_version_ids=company.dataset_version_ids,
        provenance=company.provenance,
        units=company.units,
        input_warnings=company.input_warnings,
    )
    return evaluate(
        "fcff_dcf",
        dcf_input,
        calculated_at=datetime.now(UTC).isoformat(),
    )


def _dcf_valuation_response(
    result: FCFFDCFResult,
    *,
    method_revision: str | None = None,
    run_id: str | None = None,
) -> FCFFDCFValuationResponse:
    return FCFFDCFValuationResponse(
        security_id=result.security_id,
        symbol=result.symbol,
        name=result.name,
        currency=result.currency,
        forecast_years=result.forecast_years,
        forecast_cash_flows=[
            CashFlowForecastYearResponse(
                year=cf.year,
                revenue=cf.revenue,
                revenue_growth=cf.revenue_growth,
                operating_income=cf.operating_income,
                tax=cf.tax,
                nopat=cf.nopat,
                reinvestment=cf.reinvestment,
                free_cash_flow=cf.free_cash_flow,
                discount_factor=cf.discount_factor,
                present_value=cf.present_value,
            )
            for cf in result.forecast_cash_flows
        ],
        terminal_cash_flow=result.terminal_cash_flow,
        terminal_value=result.terminal_value,
        pv_terminal_value=result.pv_terminal_value,
        terminal_value_contribution=result.terminal_value_contribution,
        enterprise_value=result.enterprise_value,
        cash=result.cash,
        total_debt=result.total_debt,
        equity_value=result.equity_value,
        shares_outstanding=result.shares_outstanding,
        value_per_share=result.value_per_share,
        scenarios=[
            ScenarioResponse(
                name=sc.name,
                wacc=sc.wacc,
                terminal_growth_rate=sc.terminal_growth_rate,
                revenue_growth_rate=sc.revenue_growth_rate,
                operating_margin=sc.operating_margin,
                enterprise_value=sc.enterprise_value,
                equity_value=sc.equity_value,
                value_per_share=sc.value_per_share,
            )
            for sc in result.scenarios
        ],
        sensitivity=SensitivityMatrixResponse(
            wacc_values=list(result.sensitivity.wacc_values),
            terminal_growth_values=list(result.sensitivity.terminal_growth_values),
            grid=[list(row) for row in result.sensitivity.grid],
        ),
        warnings=result.warnings,
        dataset_version_ids=result.dataset_version_ids,
        calculated_at=result.calculated_at,
        inputs=FCFFDCFInputResponse(
            base_revenue=result.inputs.base_revenue,
            revenue_growth_rate=result.inputs.revenue_growth_rate,
            operating_margin=result.inputs.operating_margin,
            tax_rate=result.inputs.tax_rate,
            reinvestment_rate=result.inputs.reinvestment_rate,
            wacc=result.inputs.wacc,
            terminal_growth_rate=result.inputs.terminal_growth_rate,
            shares_outstanding=result.inputs.shares_outstanding,
            total_debt=result.inputs.total_debt,
            cash=result.inputs.cash,
            forecast_years=result.inputs.forecast_years,
            provenance=result.inputs.provenance,
            units=result.inputs.units,
            input_warnings=result.inputs.input_warnings,
        ),
        provenance=result.inputs.provenance,
        units=result.inputs.units,
        method_revision=method_revision,
        run_id=run_id,
    )


class StrategyRequestContext(NamedTuple):
    """Eligible Market View and decision time resolved for a Strategy request."""

    market_view: MarketView
    decision_time: str


def _strategy_market_view(
    market_store: MarketDataStore, request: StrategyEvaluateRequest
) -> StrategyRequestContext:
    """Build the eligible Market View and decision time for a Strategy request."""
    bars = market_store.history(
        request.dataset_version_id,
        symbol=request.symbol,
        as_of=request.as_of,
    )
    if not bars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No price history found for symbol '{request.symbol}' "
                f"in dataset '{request.dataset_version_id}'."
            ),
        )

    sorted_bars = sorted(bars, key=lambda b: b.session_date)
    session_dates = [bar.session_date for bar in sorted_bars]
    if request.price_field == "open":
        prices = [bar.open for bar in sorted_bars]
    elif request.price_field == "high":
        prices = [bar.high for bar in sorted_bars]
    elif request.price_field == "low":
        prices = [bar.low for bar in sorted_bars]
    else:
        prices = [bar.close for bar in sorted_bars]

    latest_bar = sorted_bars[-1]
    decision_time = (
        request.as_of.isoformat()
        if request.as_of is not None
        else (latest_bar.available_at or datetime.now(UTC).isoformat())
    )
    view = MarketView(
        security_id=request.symbol,
        session_dates=tuple(session_dates),
        prices=tuple(prices),
    )
    return StrategyRequestContext(market_view=view, decision_time=decision_time)


def _build_watchlist_response(
    project_id: str,
    store: ProjectStore,
    market_store: MarketDataStore,
    *,
    options: WatchlistQueryOptions = WatchlistQueryOptions(),
) -> WatchlistResponse:
    security_ids = store.get_watchlist(project_id)
    all_theses = store.list_theses(project_id)

    raw_items: list[WatchlistItemResponse] = []
    for sec_id in security_ids:
        sec = market_store.get_security(sec_id)
        if not sec:
            continue
        thesis = (
            all_theses.get(sec_id) or all_theses.get(sec.security_id) or all_theses.get(sec.symbol)
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
                security_id=sec.security_id,
                symbol=sec.symbol,
                has_thesis=has_thesis,
                thesis_updated_at=thesis_updated,
                thesis_preview=thesis_preview,
            )
        )

    # Filtering (RES-006)
    filtered = raw_items
    if options.query and options.query.strip():
        q_lower = options.query.strip().lower()
        filtered = [
            item
            for item in filtered
            if q_lower in item.security.symbol.lower() or q_lower in item.security.name.lower()
        ]
    if options.exchange and options.exchange.strip() and options.exchange.lower() != "all":
        ex_lower = options.exchange.strip().lower()
        filtered = [
            item
            for item in filtered
            if item.security.exchange and item.security.exchange.lower() == ex_lower
        ]
    if options.thesis_status:
        st = options.thesis_status.strip().lower()
        if st == "has_thesis":
            filtered = [item for item in filtered if item.has_thesis]
        elif st == "no_thesis":
            filtered = [item for item in filtered if not item.has_thesis]

    # Sorting (RES-006)
    reverse = options.sort_order.lower() == "desc"
    if options.sort_by == "name":
        filtered.sort(key=lambda item: item.security.name.lower(), reverse=reverse)
    elif options.sort_by == "exchange":
        filtered.sort(key=lambda item: (item.security.exchange or "").lower(), reverse=reverse)
    elif options.sort_by == "thesis_updated_at":
        filtered.sort(key=lambda item: item.thesis_updated_at or "", reverse=reverse)
    else:  # default 'symbol'
        filtered.sort(key=lambda item: item.security.symbol.lower(), reverse=reverse)

    total = len(filtered)
    paged = filtered[options.offset : options.offset + options.limit]

    return WatchlistResponse(
        project_id=project_id,
        items=paged,
        total=total,
        offset=options.offset,
        limit=options.limit,
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
    env_candidates = [
        workspace_root / ".env.local",
        workspace_root / ".env",
        repository_root / ".env.local",
        repository_root / ".env",
    ]
    env_file = next((p for p in env_candidates if p.exists()), env_candidates[0])
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
    async def revision_not_immutable(
        _: Request, error: RevisionNotImmutableError
    ) -> JSONResponse:
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

    @app.api_route(
        "/api/projects/{project_id}",
        methods=["PATCH"],
        response_model=ProjectResponse,
        tags=["projects"],
    )
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
        "/api/projects/{project_id}/definitions/{kind}/{name}/{revision}",
        response_model=DefinitionRevisionResponse,
        tags=["definitions"],
    )
    def read_definition_revision(
        project_id: UUID,
        kind: str = FastAPIPath(pattern=r"^[a-z][a-z_]*$"),
        name: str = FastAPIPath(min_length=1, max_length=128),
        revision: str = FastAPIPath(pattern=r"^v[1-9][0-9]*$"),
    ) -> DefinitionRevisionResponse:
        wrapped = store.read_revision(
            str(project_id), kind=kind, name=name, revision=revision
        )
        return DefinitionRevisionResponse(
            kind=kind,
            name=str(wrapped.get("name", name)),
            revision=revision,
            definition=wrapped.get("definition"),
            saved_at=str(wrapped.get("saved_at", "")),
        )

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
        return _comparable_valuation_response(_calculate_comparable_result(market_store, request))

    @app.post(
        "/api/projects/{project_id}/valuations/comparables",
        response_model=ComparableValuationResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["valuations"],
    )
    def save_comparable_valuation(
        project_id: UUID, request: ComparableValuationRequest
    ) -> ComparableValuationResponse:
        result = _calculate_comparable_result(market_store, request)
        definition = {
            "method": "trading_comparables",
            "target_security_id": request.target_security_id,
            "peer_security_ids": request.peer_security_ids,
        }
        name = f"Comparable valuation - {result.target.symbol}"
        revision = store.save_revision(
            str(project_id), kind="valuation", name=name, definition=definition
        )
        method_revision = f"trading_comparables:{revision}"
        run_id = store.create_valuation_result(
            str(project_id),
            ValuationRunRecord(
                method_revision=method_revision,
                dataset_version_ids=result.dataset_version_ids,
                parameters=definition,
                result=_comparable_valuation_response(result).model_dump(),
            ),
        )
        return _comparable_valuation_response(
            result, method_revision=method_revision, run_id=run_id
        )

    @app.get(
        "/api/projects/{project_id}/valuations/seed/{security_id}",
        response_model=FCFFDCFSeedResponse,
        tags=["valuations"],
    )
    def seed_dcf_valuation(
        project_id: UUID,
        security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    ) -> FCFFDCFSeedResponse:
        store.get_project(str(project_id))
        return _dcf_company_seed(market_store, security_id)

    @app.post(
        "/api/valuations/dcf",
        response_model=FCFFDCFValuationResponse,
        tags=["valuations"],
    )
    def calculate_dcf_valuation(
        request: FCFFDCFRequest,
    ) -> FCFFDCFValuationResponse:
        return _dcf_valuation_response(_calculate_dcf_result(market_store, request))

    @app.post(
        "/api/projects/{project_id}/valuations/dcf",
        response_model=FCFFDCFValuationResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["valuations"],
    )
    def save_dcf_valuation(project_id: UUID, request: FCFFDCFRequest) -> FCFFDCFValuationResponse:
        result = _calculate_dcf_result(market_store, request)
        definition = {
            "method": "fcff_dcf",
            "target_security_id": request.target_security_id,
            "base_revenue": request.base_revenue,
            "revenue_growth_rate": request.revenue_growth_rate,
            "operating_margin": request.operating_margin,
            "tax_rate": request.tax_rate,
            "reinvestment_rate": request.reinvestment_rate,
            "wacc": request.wacc,
            "terminal_growth_rate": request.terminal_growth_rate,
            "shares_outstanding": request.shares_outstanding,
            "total_debt": request.total_debt,
            "cash": request.cash,
            "forecast_years": request.forecast_years,
        }
        name = f"FCFF DCF valuation - {result.symbol}"
        revision = store.save_revision(
            str(project_id), kind="valuation", name=name, definition=definition
        )
        method_revision = f"fcff_dcf:{revision}"
        run_id = store.create_valuation_result(
            str(project_id),
            ValuationRunRecord(
                method_revision=method_revision,
                dataset_version_ids=result.dataset_version_ids,
                parameters=definition,
                result=_dcf_valuation_response(result).model_dump(),
            ),
        )
        return _dcf_valuation_response(result, method_revision=method_revision, run_id=run_id)

    @app.post(
        "/api/projects/{project_id}/valuations/compare",
        response_model=ValuationComparisonResponse,
        tags=["valuations"],
    )
    def compare_valuations(
        project_id: UUID, request: ValuationComparisonRequest
    ) -> ValuationComparisonResponse:
        saved_list = store.list_valuation_results(str(project_id))
        runs_by_id = {
            item["run_id"]: item
            for item in saved_list
            if isinstance(item, dict) and "run_id" in item
        }

        items: list[ValuationComparisonItemResponse] = []
        for run_id in request.run_ids:
            entry = runs_by_id.get(run_id)
            if not entry:
                continue
            method_revision = str(entry.get("method_revision", ""))
            calc_at = str(entry.get("calculated_at", ""))
            result_dict = entry.get("result", {})
            if not isinstance(result_dict, dict):
                continue

            is_dcf = "forecast_cash_flows" in result_dict or "value_per_share" in result_dict
            method = "fcff_dcf" if is_dcf else "trading_comparables"

            if is_dcf:
                inputs = result_dict.get("inputs", {})
                scenarios_list = result_dict.get("scenarios", [])
                base_sc = scenarios_list[1] if len(scenarios_list) > 1 else {}
                key_assump: dict[str, JsonValue] = {
                    "wacc": inputs.get("wacc") or base_sc.get("wacc"),
                    "terminal_growth_rate": inputs.get("terminal_growth_rate")
                    or base_sc.get("terminal_growth_rate"),
                    "revenue_growth_rate": inputs.get("revenue_growth_rate")
                    or base_sc.get("revenue_growth_rate"),
                    "operating_margin": inputs.get("operating_margin")
                    or base_sc.get("operating_margin"),
                    "tax_rate": inputs.get("tax_rate"),
                    "reinvestment_rate": inputs.get("reinvestment_rate"),
                    "forecast_years": result_dict.get("forecast_years"),
                }
                items.append(
                    ValuationComparisonItemResponse(
                        run_id=run_id,
                        method=method,
                        method_revision=method_revision,
                        security_id=str(result_dict.get("security_id", "")),
                        symbol=str(result_dict.get("symbol", "")),
                        name=str(result_dict.get("name", "")),
                        currency=str(result_dict.get("currency", "USD")),
                        calculated_at=calc_at,
                        value_per_share=result_dict.get("value_per_share"),
                        enterprise_value=result_dict.get("enterprise_value"),
                        equity_value=result_dict.get("equity_value"),
                        terminal_value_contribution=result_dict.get("terminal_value_contribution"),
                        key_assumptions=key_assump,
                        warnings=result_dict.get("warnings", []),
                        dataset_version_ids=result_dict.get("dataset_version_ids", []),
                    )
                )
            else:
                target = result_dict.get("target", {})
                peers = result_dict.get("peers", [])
                peer_syms: list[JsonValue] = [
                    str(p.get("symbol")) for p in peers if isinstance(p, dict) and p.get("symbol")
                ]
                key_assump_comp: dict[str, JsonValue] = {
                    "peer_count": len(peers),
                    "peer_symbols": peer_syms,
                }
                items.append(
                    ValuationComparisonItemResponse(
                        run_id=run_id,
                        method=method,
                        method_revision=method_revision,
                        security_id=str(target.get("security_id", "")),
                        symbol=str(target.get("symbol", "")),
                        name=str(target.get("name", "")),
                        currency=str(target.get("currency", "USD")),
                        calculated_at=calc_at,
                        enterprise_value=target.get("enterprise_value"),
                        price_to_earnings=target.get("price_to_earnings"),
                        ev_to_revenue=target.get("ev_to_revenue"),
                        ev_to_ebitda=target.get("ev_to_ebitda"),
                        free_cash_flow_yield=target.get("free_cash_flow_yield"),
                        key_assumptions=key_assump_comp,
                        warnings=result_dict.get("warnings", []),
                        dataset_version_ids=result_dict.get("dataset_version_ids", []),
                    )
                )
        methods_present = {item.method for item in items}
        if len(methods_present) > 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "incompatible_valuation_methods",
                    "message": f"Cannot compare incompatible valuation methods side by side: {', '.join(sorted(methods_present))}.",
                    "details": {"methods": sorted(methods_present)},
                },
            )

        return ValuationComparisonResponse(
            items=items,
            compared_at=datetime.now(UTC).isoformat(),
        )

    @app.get(
        "/api/projects/{project_id}/valuations/{run_id}/export/{format_type}",
        tags=["valuations"],
    )
    def export_valuation(
        project_id: UUID,
        run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
        format_type: str = FastAPIPath(pattern=r"^(html|csv|json)$"),
    ) -> Response:
        try:
            artifact = store.get_valuation_export(str(project_id), run_id, format_type)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
        )

    @app.get(
        "/api/projects/{project_id}/valuations",
        response_model=list[SavedValuationResponse],
        tags=["valuations"],
    )
    def list_saved_valuations(project_id: UUID) -> list[SavedValuationResponse]:
        results = store.list_valuation_results(str(project_id))
        return [SavedValuationResponse.model_validate(item) for item in results]

    @app.post(
        "/api/projects/{project_id}/backtests",
        response_model=BacktestResultResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["backtests"],
    )
    def run_project_backtest(
        project_id: UUID, request: BacktestRunRequest
    ) -> BacktestResultResponse:
        store.get_project(str(project_id))
        if request.start_date > request.end_date:
            store.create_failed_backtest_run(
                str(project_id),
                FailedBacktestRunRecord(
                    strategy_revision=request.strategy_revision,
                    dataset_version_ids=[request.dataset_version_id],
                    parameters=dict(request.parameters),
                    error_message="start_date must not be after end_date.",
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="start_date must not be after end_date.",
            )
        target_symbols: list[str] = (
            request.symbols if request.symbols else ([request.symbol] if request.symbol else [])
        )
        resolved_securities = []
        for sym in target_symbols:
            sec = market_store.get_security(sym)
            if not sec:
                store.create_failed_backtest_run(
                    str(project_id),
                    FailedBacktestRunRecord(
                        strategy_revision=request.strategy_revision,
                        dataset_version_ids=[request.dataset_version_id],
                        parameters=dict(request.parameters),
                        error_message=f"Security not found: {sym}",
                    ),
                )
                raise SecurityNotFoundError(sym)
            resolved_securities.append(sec)

        bench_sec = None
        if request.benchmark_symbol:
            bench_sec = market_store.get_security(request.benchmark_symbol)
            if not bench_sec:
                store.create_failed_backtest_run(
                    str(project_id),
                    FailedBacktestRunRecord(
                        strategy_revision=request.strategy_revision,
                        dataset_version_ids=[request.dataset_version_id],
                        parameters=dict(request.parameters),
                        error_message=f"Benchmark security not found: {request.benchmark_symbol}",
                    ),
                )
                raise SecurityNotFoundError(request.benchmark_symbol)

        try:
            market_store.ensure_historical_eligibility(request.dataset_version_id)
            all_bars = []
            for sec in resolved_securities:
                bars_sec = market_store.history(request.dataset_version_id, symbol=sec.security_id)
                if not bars_sec:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=(
                            f"No price history found for symbol '{sec.symbol}' "
                            f"in dataset '{request.dataset_version_id}'."
                        ),
                    )
                all_bars.extend(bars_sec)

            if bench_sec is not None:
                bench_bars = market_store.history(
                    request.dataset_version_id, symbol=bench_sec.security_id
                )
                all_bars.extend(bench_bars)

            all_corp_actions = []
            for sec in resolved_securities:
                actions_sec = market_store.corporate_actions(
                    request.dataset_version_id, symbol=sec.security_id
                )
                if isinstance(actions_sec, list):
                    all_corp_actions.extend(actions_sec)

            for ver_cov in market_store.list_dataset_versions():
                if ver_cov.id != request.dataset_version_id and (
                    ver_cov.dataset_type == DATASET_TYPE_CORPORATE_ACTIONS or ver_cov.is_corporate_actions
                ):
                    for sec in resolved_securities:
                        actions_sec = market_store.corporate_actions(
                            ver_cov.id, symbol=sec.security_id
                        )
                        if isinstance(actions_sec, list):
                            all_corp_actions.extend(actions_sec)

            universe_ids = tuple(sec.security_id for sec in resolved_securities)
            spec = BacktestSpecification(
                strategy_name=request.strategy_name,
                strategy_revision=request.strategy_revision,
                dataset_version_id=request.dataset_version_id,
                security_id=universe_ids[0] if universe_ids else "",
                universe=universe_ids,
                start_date=request.start_date,
                end_date=request.end_date,
                starting_cash=request.starting_cash,
                parameters=request.parameters,
                price_field=request.price_field,
                calendar=request.calendar,
                execution=ExecutionModelAssumptions(
                    schedule=request.execution.schedule,
                    commission_rate=request.execution.commission_rate,
                    slippage_rate=request.execution.slippage_rate,
                    allow_shorting=request.execution.allow_shorting,
                    borrow_fee_rate=request.execution.borrow_fee_rate,
                    cash_interest_rate=request.execution.cash_interest_rate,
                    unavailable_borrow=tuple(request.execution.unavailable_borrow),
                    max_leverage=request.execution.max_leverage,
                    margin_requirement=request.execution.margin_requirement,
                    maintenance_margin=request.execution.maintenance_margin,
                    leverage_mode=request.execution.leverage_mode,
                ),
                benchmark_security_id=bench_sec.security_id if bench_sec else None,
            )
            result = run_backtest(spec, bars=all_bars, corporate_actions=all_corp_actions)
        except Exception as error:
            store.create_failed_backtest_run(
                str(project_id),
                FailedBacktestRunRecord(
                    strategy_revision=request.strategy_revision,
                    dataset_version_ids=[request.dataset_version_id],
                    parameters=dict(request.parameters),
                    error_message=str(error),
                ),
            )
            raise

        run_id = store.create_backtest_result(
            str(project_id),
            BacktestRunRecord(
                strategy_revision=request.strategy_revision,
                dataset_version_ids=[request.dataset_version_id],
                parameters=dict(request.parameters),
                result=result.to_json(),
            ),
        )
        return _backtest_result_response(
            result.to_json(),
            run_id=run_id,
            strategy_revision=request.strategy_revision,
        )

    @app.get(
        "/api/projects/{project_id}/backtests",
        response_model=list[BacktestResultResponse],
        tags=["backtests"],
    )
    def list_project_backtests(project_id: UUID) -> list[BacktestResultResponse]:
        results = store.list_backtest_results(str(project_id))
        return [
            _backtest_result_response(
                item["result"],
                run_id=item["run_id"],
                strategy_revision=item["strategy_revision"],
            )
            for item in results
        ]

    @app.get(
        "/api/projects/{project_id}/backtests/{run_id}",
        response_model=BacktestResultResponse,
        tags=["backtests"],
    )
    def get_project_backtest(project_id: UUID, run_id: str) -> BacktestResultResponse:
        item = store.get_backtest_result(str(project_id), run_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backtest Run not found.",
            )
        return _backtest_result_response(
            item["result"],
            run_id=run_id,
            strategy_revision=item["strategy_revision"],
        )

    @app.get(
        "/api/projects/{project_id}/backtests/{run_id}/export/{format_type}",
        tags=["backtests"],
    )
    def export_backtest(
        project_id: UUID,
        run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
        format_type: str = FastAPIPath(pattern=r"^(html|csv|json)$"),
    ) -> Response:
        try:
            artifact = store.get_backtest_export(str(project_id), run_id, format_type)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
        )

    @app.post(
        "/api/projects/{project_id}/backtests/compare",
        response_model=BacktestComparisonResponse,
        tags=["backtests"],
    )
    def compare_backtests(
        project_id: UUID, request: BacktestComparisonRequest
    ) -> BacktestComparisonResponse:
        store.get_project(str(project_id))
        items: list[BacktestComparisonItemResponse] = []
        for run_id in request.run_ids:
            entry = store.get_backtest_result(str(project_id), run_id)
            if entry is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Backtest Run '{run_id}' not found.",
                )
            result_obj = _backtest_result_response(
                entry["result"],
                run_id=entry["run_id"],
                strategy_revision=entry["strategy_revision"],
            )
            raw_costs = result_obj.manifest.get("costs")
            costs_dict = raw_costs if isinstance(raw_costs, dict) else {}

            items.append(
                BacktestComparisonItemResponse(
                    run_id=result_obj.run_id or run_id,
                    strategy_name=result_obj.specification.strategy_name,
                    strategy_revision=result_obj.strategy_revision or "",
                    universe=result_obj.specification.universe,
                    start_date=result_obj.specification.start_date,
                    end_date=result_obj.specification.end_date,
                    starting_cash=result_obj.specification.starting_cash,
                    benchmark_security_id=result_obj.specification.benchmark_security_id,
                    parameters=result_obj.specification.parameters,
                    execution=result_obj.specification.execution,
                    metrics=result_obj.metrics,
                    costs=costs_dict,
                    warnings=result_obj.warnings,
                    dataset_version_ids=entry.get("dataset_version_ids", []),
                )
            )

        return BacktestComparisonResponse(
            items=items,
            compared_at=datetime.now(UTC).isoformat(),
        )

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
            with contextlib.suppress(ProjectNotFoundError, OSError, KeyError):
                valuations = store.list_valuations_for_security(
                    str(project_id), summary.security.security_id
                )
                runs = store.list_runs_for_security(str(project_id), summary.security.security_id)

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
        options: Annotated[WatchlistQueryOptions, Query()] = WatchlistQueryOptions(),
    ) -> WatchlistResponse:
        return _build_watchlist_response(
            str(project_id),
            store,
            market_store,
            options=options,
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
        return [_coverage_response(report) for report in market_store.list_dataset_versions()]

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

    @app.get(
        "/api/indicators",
        response_model=list[IndicatorMetadataResponse],
        tags=["indicators"],
    )
    def get_indicators() -> list[IndicatorMetadataResponse]:
        return [_indicator_meta_response(spec) for spec in list_indicators()]

    @app.get(
        "/api/indicators/{name}",
        response_model=IndicatorMetadataResponse,
        tags=["indicators"],
    )
    def get_indicator_by_name(
        name: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_]{1,64}$"),
    ) -> IndicatorMetadataResponse:
        return _indicator_meta_response(get_indicator_spec(name))

    @app.post(
        "/api/indicators/calculate",
        response_model=IndicatorSeriesResponse,
        tags=["indicators"],
    )
    def calculate_indicator_endpoint(
        request: IndicatorCalculateRequest,
    ) -> IndicatorSeriesResponse:
        bars = market_store.history(
            request.dataset_version_id,
            symbol=request.symbol,
            as_of=request.as_of,
        )
        if not bars:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No price history found for symbol '{request.symbol}' "
                    f"in dataset '{request.dataset_version_id}'."
                ),
            )
        sorted_bars = sorted(bars, key=lambda b: b.session_date)
        session_dates = [b.session_date for b in sorted_bars]
        if request.price_field == "open":
            prices = [b.open for b in sorted_bars]
        elif request.price_field == "high":
            prices = [b.high for b in sorted_bars]
        elif request.price_field == "low":
            prices = [b.low for b in sorted_bars]
        else:
            prices = [b.close for b in sorted_bars]

        series = calculate_indicator(
            name=request.name,
            session_dates=session_dates,
            prices=prices,
            parameters=request.parameters,
        )
        return _indicator_series_response(
            series,
            dataset_version_id=request.dataset_version_id,
            symbol=request.symbol,
        )

    @app.get(
        "/api/predictive-models",
        response_model=list[PredictiveModelMetadataResponse],
        tags=["predictive-models"],
    )
    def get_predictive_models() -> list[PredictiveModelMetadataResponse]:
        return [_predictive_metadata_response(metadata) for metadata in list_predictive_models()]

    @app.get(
        "/api/predictive-models/{name}",
        response_model=PredictiveModelMetadataResponse,
        tags=["predictive-models"],
    )
    def get_predictive_model_by_name(
        name: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_]{1,64}$"),
    ) -> PredictiveModelMetadataResponse:
        return _predictive_metadata_response(get_predictive_model_spec(name).metadata)

    @app.post(
        "/api/predictive-models/run",
        response_model=PredictiveModelRunResponse,
        tags=["predictive-models"],
    )
    def run_predictive_model_preview(
        request: PredictiveModelRunRequest,
    ) -> PredictiveModelRunResponse:
        calculation = _predictive_model_calculation(market_store, request)
        return _predictive_run_response(
            calculation,
            PredictiveModelResponseContext(
                symbol=request.symbol,
                dataset_version_id=request.dataset_version_id,
                as_of=request.as_of,
            ),
        )

    @app.post(
        "/api/projects/{project_id}/predictive-models/runs",
        response_model=PredictiveModelRunResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["predictive-models"],
    )
    def save_predictive_model_run(
        project_id: UUID,
        request: PredictiveModelRunRequest,
    ) -> PredictiveModelRunResponse:
        try:
            calculation = _predictive_model_calculation(market_store, request)
            definition = {
                "model": calculation.metadata.name,
                "target": calculation.metadata.target,
                "horizon": calculation.metadata.horizon,
                "features": list(calculation.metadata.features),
                "training_window": calculation.parameters["training_window"],
                "parameters": calculation.parameters,
                "output_meaning": calculation.metadata.output_meaning,
                "symbol": request.symbol,
                "dataset_version_id": request.dataset_version_id,
                "as_of": request.as_of.isoformat() if request.as_of else None,
                "seed": calculation.seed,
            }
            definition_name = f"{calculation.metadata.name} - {request.symbol}"
            revision = store.save_revision(
                str(project_id),
                kind="predictive_model",
                name=definition_name,
                definition=definition,
            )
            model_revision = f"{calculation.metadata.name}:{request.symbol}:{revision}"
        except Exception as error:
            try:
                _persist_failed_predictive_model_run(store, project_id, request, error)
            except Exception as persist_error:
                error.add_note(f"Failed to persist the Predictive Model error: {persist_error}")
            raise

        completed_at = datetime.now(UTC).isoformat()
        base_response = _predictive_run_response(
            calculation,
            PredictiveModelResponseContext(
                symbol=request.symbol,
                dataset_version_id=request.dataset_version_id,
                model_revision=model_revision,
                status="completed",
                completed_at=completed_at,
                as_of=request.as_of,
            ),
        )
        run_id = store.create_predictive_model_result(
            str(project_id),
            PredictiveModelRunRecord(
                model_revision=model_revision,
                dataset_version_ids=[request.dataset_version_id],
                parameters=calculation.parameters,
                as_of=request.as_of.isoformat() if request.as_of else None,
                completed_at=completed_at,
                artifact=calculation.artifact.to_json(),
                predictions=[prediction.to_json() for prediction in calculation.predictions],
                result=base_response.model_dump(mode="json"),
                evaluation=calculation.evaluation.to_json(),
                fold_artifacts=[
                    fold_artifact.to_json() for fold_artifact in calculation.fold_artifacts
                ],
                folds=[fold.to_json() for fold in calculation.evaluation.folds],
            ),
        )
        return base_response.model_copy(update={"run_id": run_id})

    @app.get(
        "/api/projects/{project_id}/predictive-models/runs",
        response_model=list[PredictiveModelRunResponse],
        tags=["predictive-models"],
    )
    def list_project_predictive_model_runs(
        project_id: UUID,
    ) -> list[PredictiveModelRunResponse]:
        responses: list[PredictiveModelRunResponse] = []
        for item in store.list_predictive_model_results(str(project_id)):
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            normalized_result = _normalize_predictive_model_result(result)
            responses.append(
                PredictiveModelRunResponse.model_validate(
                    {
                        **normalized_result,
                        "run_id": item.get("run_id"),
                        "model_revision": item.get("model_revision"),
                        "status": "completed",
                    }
                )
            )
        return responses

    @app.get(
        "/api/projects/{project_id}/predictive-models/runs/{run_id}",
        response_model=PredictiveModelRunResponse,
        tags=["predictive-models"],
    )
    def get_project_predictive_model_run(
        project_id: UUID,
        run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    ) -> PredictiveModelRunResponse:
        item = store.get_predictive_model_result(str(project_id), run_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Predictive Model Run not found.",
            )
        result = item.get("result")
        if not isinstance(result, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Predictive Model Run artifact is invalid.",
            )
        return PredictiveModelRunResponse.model_validate(
            {
                **_normalize_predictive_model_result(result),
                "run_id": item.get("run_id"),
                "model_revision": item.get("model_revision"),
                "status": "completed",
            }
        )

    @app.get(
        "/api/projects/{project_id}/predictive-models/runs/{run_id}/export/{format_type}",
        tags=["predictive-models"],
        responses={
            200: {
                "content": {
                    "text/html": {"schema": {"type": "string"}},
                    "text/csv": {"schema": {"type": "string"}},
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "manifest": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                                "predictive_model": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                            },
                            "required": ["manifest", "predictive_model"],
                        }
                    },
                }
            }
        },
    )
    def export_predictive_model(
        project_id: UUID,
        run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
        format_type: Literal["html", "csv", "json"] = FastAPIPath(),
    ) -> Response:
        try:
            artifact = store.get_predictive_model_export(
                str(project_id), run_id, format_type
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
        )

    @app.get(
        "/api/strategies",
        response_model=list[StrategyMetadataResponse],
        tags=["strategies"],
    )
    def get_strategies() -> list[StrategyMetadataResponse]:
        return [_strategy_meta_response(spec) for spec in list_strategies()]

    @app.get(
        "/api/strategies/{name}",
        response_model=StrategyMetadataResponse,
        tags=["strategies"],
    )
    def get_strategy_by_name(
        name: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_]{1,64}$"),
    ) -> StrategyMetadataResponse:
        return _strategy_meta_response(get_strategy_spec(name))

    @app.post(
        "/api/strategies/evaluate",
        response_model=StrategyEvaluationResponse,
        tags=["strategies"],
    )
    def evaluate_strategy_endpoint(
        request: StrategyEvaluateRequest,
    ) -> StrategyEvaluationResponse:
        if {
            "predictive_model_run_id",
            "predictive_model_evaluation",
        }.intersection(request.parameters):
            raise StrategyEvaluationError(
                "A saved Predictive Model Run reference is required before a "
                "Strategy can use model output (MOD-009)."
            )
        context = _strategy_market_view(market_store, request)
        evaluation = evaluate_strategy(
            name=request.name,
            market_view=context.market_view,
            parameters=request.parameters,
            decision_time=context.decision_time,
        )
        return _strategy_evaluation_response(
            evaluation,
            symbol=request.symbol,
            dataset_version_id=request.dataset_version_id,
        )

    @app.post(
        "/api/projects/{project_id}/strategies/evaluate",
        response_model=SavedStrategyEvaluationResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["strategies"],
    )
    def save_strategy_evaluation(
        project_id: UUID, request: StrategyEvaluateRequest
    ) -> SavedStrategyEvaluationResponse:
        model_run_id = request.parameters.get("predictive_model_run_id")
        evaluation_payload_present = "predictive_model_evaluation" in request.parameters
        if evaluation_payload_present:
            raise StrategyEvaluationError(
                "Caller-supplied Predictive Model evaluations are not accepted. "
                "Use a persisted Predictive Model Run reference (MOD-009)."
            )
        if model_run_id is not None:
            if not isinstance(model_run_id, str) or not model_run_id.strip():
                raise StrategyEvaluationError(
                    "Predictive Model Run reference must be a non-empty saved Run ID "
                    "(MOD-009)."
                )
            model_record = store.get_predictive_model_result(str(project_id), model_run_id)
            if model_record is None:
                raise StrategyEvaluationError(
                    "Predictive Model Run not found. A saved, benchmark-verified Run "
                    "is required before a Strategy can use model output (MOD-009)."
                )
            validate_model_eligibility_for_strategy(
                model_record, require_persisted_run=True
            )
        context = _strategy_market_view(market_store, request)
        evaluation = evaluate_strategy(
            name=request.name,
            market_view=context.market_view,
            parameters=request.parameters,
            decision_time=context.decision_time,
        )
        name = f"{evaluation.strategy_name} - {request.symbol}"
        revision = store.save_revision(
            str(project_id),
            kind="strategy",
            name=name,
            definition={
                "strategy": evaluation.strategy_name,
                "indicator": evaluation.indicator_name,
                "symbol": request.symbol,
                "dataset_version_id": request.dataset_version_id,
                "price_field": request.price_field,
                "parameters": evaluation.parameters,
                "decision_time": evaluation.decision_time,
                "latest_session_date": evaluation.latest_session_date,
                "targets": [
                    {
                        "security_id": target.security_id,
                        "weight": target.weight,
                        "rationale": target.rationale,
                        "indicator_state": target.indicator_state,
                    }
                    for target in evaluation.targets
                ],
            },
        )
        base = _strategy_evaluation_response(
            evaluation,
            symbol=request.symbol,
            dataset_version_id=request.dataset_version_id,
        )
        return SavedStrategyEvaluationResponse(
            **base.model_dump(),
            revision=revision,
            strategy_revision=f"{evaluation.strategy_name}:{revision}",
        )

    @app.get(
        "/api/projects/{project_id}/strategies",
        response_model=list[SavedStrategyRevisionResponse],
        tags=["strategies"],
    )
    def list_project_strategy_revisions(project_id: UUID) -> list[SavedStrategyRevisionResponse]:
        return [
            SavedStrategyRevisionResponse.model_validate(item)
            for item in store.list_strategy_revisions(str(project_id))
        ]

    @app.get(
        "/api/projects/{project_id}/strategies/enabled",
        response_model=list[EnabledStrategyResponse],
        tags=["strategies"],
    )
    def list_enabled_strategy_revisions(project_id: UUID) -> list[EnabledStrategyResponse]:
        return [
            EnabledStrategyResponse.model_validate(item)
            for item in store.list_enabled_strategies(str(project_id))
        ]

    @app.post(
        "/api/projects/{project_id}/strategies/enable",
        response_model=EnabledStrategyResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["strategies"],
    )
    def enable_strategy_revision(
        project_id: UUID, request: EnabledStrategyRequest
    ) -> EnabledStrategyResponse:
        return EnabledStrategyResponse.model_validate(
            enable_strategy_revision_domain(
                store,
                str(project_id),
                name=request.name,
                revision=request.revision,
            )
        )

    @app.post(
        "/api/projects/{project_id}/strategies/disable",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["strategies"],
    )
    def disable_strategy_revision(
        project_id: UUID, request: EnabledStrategyRequest
    ) -> Response:
        store.disable_strategy(str(project_id), name=request.name, revision=request.revision)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get(
        "/api/projects/{project_id}/alerts",
        response_model=list[SignalResponse],
        tags=["alerts"],
    )
    def list_project_signals(project_id: UUID) -> list[SignalResponse]:
        return [
            signal_response(signal) for signal in store.list_signals(str(project_id))
        ]

    @app.post(
        "/api/projects/{project_id}/alerts/refresh",
        response_model=SignalRefreshResponse,
        tags=["alerts"],
    )
    def refresh_project_alerts(project_id: UUID) -> SignalRefreshResponse:
        result: SignalRefreshResult = refresh_enabled_strategies(
            store, market_store, str(project_id)
        )
        return SignalRefreshResponse(
            signals=[signal_response(s.to_json()) for s in result.signals],
            failures=[
                SignalRefreshFailureResponse(
                    strategy_revision=failure.strategy_revision, error=failure.error
                )
                for failure in result.failures
            ],
        )

    built_interface = static_dir or repository_root / "web" / "dist"
    if built_interface.is_dir():
        app.mount("/", StaticFiles(directory=built_interface, html=True), name="interface")

    return app


app = create_app()
