"""FastAPI router for DCF and comparable company valuations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi import (
    Path as FastAPIPath,
)
from pydantic import BaseModel, Field, field_validator

from ..json_types import JsonValue
from ..market_data import MarketDataStore
from ..projects import ProjectStore, ValuationRunRecord
from ..valuation import (
    ComparableCompanyInput,
    ComparableValuationResult,
    FCFFDCFInput,
    FCFFDCFResult,
    evaluate,
)
from .deps import (
    SecurityNotFoundError,
    get_market_store,
    get_project_store,
    log_run_event,
)

router = APIRouter()

_FUNDAMENTAL_FIELDS = {
    "shares_outstanding": ("shares_outstanding", "common_stock_shares_outstanding"),
    "total_debt": ("total_debt", "debt"),
    "cash": ("cash", "cash_and_cash_equivalents"),
    "revenue": ("revenue", "total_revenue", "us-gaap:Revenues"),
    "ebitda": ("ebitda", "operating_income", "us-gaap:OperatingIncomeLoss"),
    "net_income": ("net_income", "us-gaap:NetIncomeLoss"),
    "free_cash_flow": ("free_cash_flow",),
}


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


def _fact_value(
    facts: dict[str, tuple[float, tuple[int, str], str, str]], field_name: str
) -> float | None:
    fact = facts.get(field_name)
    return fact[0] if fact else None


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


def _comparable_valuation_response(
    result: ComparableValuationResult,
    *,
    method_revision: str | None = None,
    run_id: str | None = None,
) -> ComparableValuationResponse:
    response = ComparableValuationResponse.model_validate(result, from_attributes=True)
    return response.model_copy(update={"method_revision": method_revision, "run_id": run_id})


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


@router.post(
    "/api/valuations/comparables",
    response_model=ComparableValuationResponse,
    tags=["valuations"],
)
def calculate_comparable_valuation(
    request: ComparableValuationRequest,
    market_store: MarketDataStore = Depends(get_market_store),
) -> ComparableValuationResponse:
    return _comparable_valuation_response(_calculate_comparable_result(market_store, request))


@router.post(
    "/api/projects/{project_id}/valuations/comparables",
    response_model=ComparableValuationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["valuations"],
)
def save_comparable_valuation(
    project_id: UUID,
    request: ComparableValuationRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> ComparableValuationResponse:
    result = _calculate_comparable_result(market_store, request)
    definition: dict[str, JsonValue] = {
        "method": "trading_comparables",
        "target_security_id": request.target_security_id,
        "peer_security_ids": list(request.peer_security_ids),
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
    log_run_event(project_id, run_id, "Valuation Run completed.")
    return _comparable_valuation_response(
        result, method_revision=method_revision, run_id=run_id
    )


@router.get(
    "/api/projects/{project_id}/valuations/seed/{security_id}",
    response_model=FCFFDCFSeedResponse,
    tags=["valuations"],
)
def seed_dcf_valuation(
    project_id: UUID,
    security_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> FCFFDCFSeedResponse:
    store.get_project(str(project_id))
    return _dcf_company_seed(market_store, security_id)


@router.post(
    "/api/valuations/dcf",
    response_model=FCFFDCFValuationResponse,
    tags=["valuations"],
)
def calculate_dcf_valuation(
    request: FCFFDCFRequest,
    market_store: MarketDataStore = Depends(get_market_store),
) -> FCFFDCFValuationResponse:
    return _dcf_valuation_response(_calculate_dcf_result(market_store, request))


@router.post(
    "/api/projects/{project_id}/valuations/dcf",
    response_model=FCFFDCFValuationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["valuations"],
)
def save_dcf_valuation(
    project_id: UUID,
    request: FCFFDCFRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> FCFFDCFValuationResponse:
    result = _calculate_dcf_result(market_store, request)
    definition: dict[str, JsonValue] = {
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
    log_run_event(project_id, run_id, "Valuation Run completed.")
    return _dcf_valuation_response(result, method_revision=method_revision, run_id=run_id)


@router.post(
    "/api/projects/{project_id}/valuations/compare",
    response_model=ValuationComparisonResponse,
    tags=["valuations"],
)
def compare_valuations(
    project_id: UUID,
    request: ValuationComparisonRequest,
    store: ProjectStore = Depends(get_project_store),
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
                "message": (
                    "Cannot compare incompatible valuation methods side by side: "
                    f"{', '.join(sorted(methods_present))}."
                ),
                "details": {"methods": sorted(methods_present)},
            },
        )

    return ValuationComparisonResponse(
        items=items,
        compared_at=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/api/projects/{project_id}/valuations/{run_id}/export/{format_type}",
    tags=["valuations"],
)
def export_valuation(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    format_type: str = FastAPIPath(pattern=r"^(html|csv|json)$"),
    store: ProjectStore = Depends(get_project_store),
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


@router.get(
    "/api/projects/{project_id}/valuations",
    response_model=list[SavedValuationResponse],
    tags=["valuations"],
)
def list_saved_valuations(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[SavedValuationResponse]:
    results = store.list_valuation_results(str(project_id))
    return [SavedValuationResponse.model_validate(item) for item in results]
