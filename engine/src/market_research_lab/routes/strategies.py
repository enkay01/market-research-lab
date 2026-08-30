"""FastAPI router for strategies and evaluations."""

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

from ..alerts import enable_strategy_revision as enable_strategy_revision_domain
from ..json_types import JsonValue
from ..market_data import MarketDataStore
from ..projects import ProjectStore
from ..strategies import (
    MarketView,
    StrategyEvaluation,
    StrategyEvaluationError,
    StrategyMetadata,
    StrategyParameter,
    StrategyTarget,
    evaluate_strategy,
    get_strategy_spec,
    list_strategies,
    validate_model_eligibility_for_strategy,
)
from .deps import get_market_store, get_project_store, non_blank_name

router = APIRouter()


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
        return non_blank_name(value)


class EnabledStrategyResponse(BaseModel):
    name: str
    revision: str
    enabled_at: str


class StrategyRequestContext(NamedTuple):
    """Eligible Market View and decision time resolved for a Strategy request."""

    market_view: MarketView
    decision_time: str


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


@router.get(
    "/api/strategies",
    response_model=list[StrategyMetadataResponse],
    tags=["strategies"],
)
def get_strategies() -> list[StrategyMetadataResponse]:
    return [_strategy_meta_response(spec) for spec in list_strategies()]


@router.get(
    "/api/strategies/{name}",
    response_model=StrategyMetadataResponse,
    tags=["strategies"],
)
def get_strategy_by_name(
    name: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_]{1,64}$"),
) -> StrategyMetadataResponse:
    return _strategy_meta_response(get_strategy_spec(name))


@router.post(
    "/api/strategies/evaluate",
    response_model=StrategyEvaluationResponse,
    tags=["strategies"],
)
def evaluate_strategy_endpoint(
    request: StrategyEvaluateRequest,
    market_store: MarketDataStore = Depends(get_market_store),
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


@router.post(
    "/api/projects/{project_id}/strategies/evaluate",
    response_model=SavedStrategyEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["strategies"],
)
def save_strategy_evaluation(
    project_id: UUID,
    request: StrategyEvaluateRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
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
                "Predictive Model Run reference must be a non-empty saved Run ID (MOD-009)."
            )
        model_record = store.get_predictive_model_result(str(project_id), model_run_id)
        if model_record is None:
            raise StrategyEvaluationError(
                "Predictive Model Run not found. A saved, benchmark-verified Run "
                "is required before a Strategy can use model output (MOD-009)."
            )
        validate_model_eligibility_for_strategy(model_record, require_persisted_run=True)
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


@router.get(
    "/api/projects/{project_id}/strategies",
    response_model=list[SavedStrategyRevisionResponse],
    tags=["strategies"],
)
def list_project_strategy_revisions(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[SavedStrategyRevisionResponse]:
    return [
        SavedStrategyRevisionResponse.model_validate(item)
        for item in store.list_strategy_revisions(str(project_id))
    ]


@router.get(
    "/api/projects/{project_id}/strategies/enabled",
    response_model=list[EnabledStrategyResponse],
    tags=["strategies"],
)
def list_enabled_strategy_revisions(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[EnabledStrategyResponse]:
    return [
        EnabledStrategyResponse.model_validate(item)
        for item in store.list_enabled_strategies(str(project_id))
    ]


@router.post(
    "/api/projects/{project_id}/strategies/enable",
    response_model=EnabledStrategyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["strategies"],
)
def enable_strategy_revision(
    project_id: UUID,
    request: EnabledStrategyRequest,
    store: ProjectStore = Depends(get_project_store),
) -> EnabledStrategyResponse:
    return EnabledStrategyResponse.model_validate(
        enable_strategy_revision_domain(
            store,
            str(project_id),
            name=request.name,
            revision=request.revision,
        )
    )


@router.post(
    "/api/projects/{project_id}/strategies/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["strategies"],
)
def disable_strategy_revision(
    project_id: UUID,
    request: EnabledStrategyRequest,
    store: ProjectStore = Depends(get_project_store),
) -> Response:
    store.disable_strategy(str(project_id), name=request.name, revision=request.revision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
