"""FastAPI router for equity backtests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
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
from pydantic import BaseModel, Field, model_validator

from ..backtest import (
    BacktestSpecification,
    ExecutionModelAssumptions,
    run_backtest,
)
from ..json_types import JsonValue
from ..market_data import DATASET_TYPE_CORPORATE_ACTIONS, MarketDataStore, Security
from ..projects import (
    BacktestRunRecord,
    FailedBacktestRunRecord,
    ProjectStore,
)
from .deps import (
    SecurityNotFoundError,
    get_market_store,
    get_project_store,
    log_failed_run,
    log_run_event,
)
from .strategies import StrategyTargetResponse

router = APIRouter()


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
    maintenance_margin: float = Field(default=0.25, ge=0, le=1)
    leverage_mode: Literal["reject", "clamp"] = "reject"


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


def _resolve_target_securities(
    market_store: MarketDataStore,
    request: BacktestRunRequest,
) -> list[Security]:
    """Resolve target securities from request parameters or dataset history."""
    target_symbols = (
        [s.strip().upper() for s in request.symbols if s.strip()]
        if request.symbols
        else ([request.symbol.strip().upper()] if request.symbol and request.symbol.strip() else [])
    )
    if not target_symbols:
        bars = market_store.history(request.dataset_version_id)
        seen: set[str] = set()
        for b in bars:
            if b.security_id not in seen:
                seen.add(b.security_id)
                target_symbols.append(b.security_id)
        if not target_symbols:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"No securities found in dataset '{request.dataset_version_id}'.",
            )

    resolved: list[Security] = []
    for sym in target_symbols:
        sec = market_store.get_security(sym)
        if not sec:
            market_store.upsert_securities(
                [Security(security_id=sym, symbol=sym, name=sym, exchange="UNKNOWN")]
            )
            sec = market_store.get_security(sym)
        if sec:
            resolved.append(sec)
    return resolved


@router.post(
    "/api/projects/{project_id}/backtests",
    response_model=BacktestResultResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["backtests"],
)
def run_project_backtest(
    project_id: UUID,
    request: BacktestRunRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> BacktestResultResponse:
    store.get_project(str(project_id))
    if request.start_date > request.end_date:
        run_id = store.create_failed_backtest_run(
            str(project_id),
            FailedBacktestRunRecord(
                strategy_revision=request.strategy_revision,
                dataset_version_ids=[request.dataset_version_id],
                parameters=dict(request.parameters),
                error_message="start_date must not be after end_date.",
            ),
        )
        log_failed_run(
            project_id,
            run_id,
            "Backtest Run failed: start date must not be after end date.",
            diagnostic_id=None,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must not be after end_date.",
        )
    resolved_securities = _resolve_target_securities(market_store, request)

    bench_sec = None
    if request.benchmark_symbol:
        bench_sec = market_store.get_security(request.benchmark_symbol)
        if not bench_sec:
            run_id = store.create_failed_backtest_run(
                str(project_id),
                FailedBacktestRunRecord(
                    strategy_revision=request.strategy_revision,
                    dataset_version_ids=[request.dataset_version_id],
                    parameters=dict(request.parameters),
                    error_message=f"Benchmark security not found: {request.benchmark_symbol}",
                ),
            )
            message = (
                f"Backtest Run failed: Benchmark security not found: {request.benchmark_symbol}"
            )
            log_failed_run(
                project_id,
                run_id,
                message,
                diagnostic_id=None,
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
                ver_cov.dataset_type == DATASET_TYPE_CORPORATE_ACTIONS
                or ver_cov.is_corporate_actions
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
        run_id = store.create_failed_backtest_run(
            str(project_id),
            FailedBacktestRunRecord(
                strategy_revision=request.strategy_revision,
                dataset_version_ids=[request.dataset_version_id],
                parameters=dict(request.parameters),
                error_message=str(error),
            ),
        )
        log_failed_run(
            project_id,
            run_id,
            f"Backtest Run failed: {error}",
            diagnostic_id=None,
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
    log_run_event(project_id, run_id, "Backtest Run completed.")
    return _backtest_result_response(
        result.to_json(),
        run_id=run_id,
        strategy_revision=request.strategy_revision,
    )


@router.get(
    "/api/projects/{project_id}/backtests",
    response_model=list[BacktestResultResponse],
    tags=["backtests"],
)
def list_project_backtests(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[BacktestResultResponse]:
    results = store.list_backtest_results(str(project_id))
    return [
        _backtest_result_response(
            item["result"],
            run_id=item["run_id"],
            strategy_revision=item["strategy_revision"],
        )
        for item in results
    ]


@router.get(
    "/api/projects/{project_id}/backtests/{run_id}",
    response_model=BacktestResultResponse,
    tags=["backtests"],
)
def get_project_backtest(
    project_id: UUID,
    run_id: str,
    store: ProjectStore = Depends(get_project_store),
) -> BacktestResultResponse:
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


@router.get(
    "/api/projects/{project_id}/backtests/{run_id}/export/{format_type}",
    tags=["backtests"],
)
def export_backtest(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    format_type: str = FastAPIPath(pattern=r"^(html|csv|json)$"),
    store: ProjectStore = Depends(get_project_store),
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


@router.post(
    "/api/projects/{project_id}/backtests/compare",
    response_model=BacktestComparisonResponse,
    tags=["backtests"],
)
def compare_backtests(
    project_id: UUID,
    request: BacktestComparisonRequest,
    store: ProjectStore = Depends(get_project_store),
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
