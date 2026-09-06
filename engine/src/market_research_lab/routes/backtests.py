"""FastAPI router for equity backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self, Sequence
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
    BacktestParameterError,
    BacktestSpecification,
    ExecutionModelAssumptions,
    ReplayFillActionType,
    run_backtest,
)
from ..json_types import JsonValue
from ..market_data import (
    DATASET_TYPE_CORPORATE_ACTIONS,
    DATASET_TYPE_DAILY_BARS,
    CorporateAction,
    DailyBar,
    MarketDataStore,
    Security,
)
from ..projects import (
    BacktestRunRecord,
    FailedBacktestRunRecord,
    ProjectStore,
)
from ..strategies import RankingRecord
from ..strategy_verdict import (
    StrategyVerdictSpecification,
    evaluate_strategy_verdict,
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


class RankingResponse(BaseModel):
    session_date: str
    decision_time: str
    security_id: str
    score: float | None = None
    rank: int | None = None
    selected: bool
    target_weight: float
    rationale: str


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


class ReplayFillActionResponse(BaseModel):
    action_type: ReplayFillActionType
    quantity: float
    execution_price: float
    source_fill_id: str
    source_fill_sequence: int


class ReplayTickResponse(BaseModel):
    date: str
    price: float
    signal: float
    position_shares: float
    portfolio_value: float
    cash: float
    daily_pnl: float
    position_value: float = 0.0
    allocation_pct: float = 0.0
    fill_actions: list[ReplayFillActionResponse]


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
    rankings: list[RankingResponse] = Field(default_factory=list)
    replay_ticks: list[ReplayTickResponse] = Field(default_factory=list)


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
        [
            part.upper()
            for value in request.symbols
            for part in value.replace(";", ",").replace(",", " ").split()
            if part
        ]
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


def _require_daily_dataset(market_store: MarketDataStore, dataset_version_id: str) -> None:
    """Reject non-daily datasets before any history lookup can occur."""
    coverage = next(
        (item for item in market_store.list_dataset_versions() if item.id == dataset_version_id),
        None,
    )
    if coverage is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Backtests require a daily_bars dataset; "
                f"dataset '{dataset_version_id}' was not found."
            ),
        )
    if coverage.dataset_type != DATASET_TYPE_DAILY_BARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Backtests require dataset_type 'daily_bars'. "
                f"Dataset '{dataset_version_id}' is '{coverage.dataset_type}'."
            ),
        )


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
    _require_daily_dataset(market_store, request.dataset_version_id)
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


class StrategyBacktestRequest(BaseModel):
    """Shared request boundary for Strategy backtests and rankings."""

    strategy_name: str = Field(min_length=1, max_length=64)
    strategy_revision: str = Field(default="v1", min_length=1, max_length=64)
    dataset_version_id: str | None = Field(default=None, min_length=1, max_length=128)
    universe_preset: str | None = Field(default=None, min_length=1, max_length=64)
    symbol: str | None = Field(default=None, max_length=32)
    symbols: list[str] | None = None
    benchmark_symbol: str = Field(default="SPY", min_length=1, max_length=32)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    starting_cash: float = Field(default=100000.0, gt=0)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    execution: ExecutionModelAssumptionsRequest = Field(
        default_factory=ExecutionModelAssumptionsRequest
    )

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not self.strategy_name.strip():
            raise ValueError("strategy_name must not be blank.")
        if not self.strategy_revision.strip():
            raise ValueError("strategy_revision must not be blank.")
        if not self.benchmark_symbol.strip():
            raise ValueError("benchmark_symbol must not be blank.")
        if self.dataset_version_id is not None and not self.dataset_version_id.strip():
            raise ValueError("dataset_version_id must not be blank.")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be less than or equal to end_date.")
        if self.symbol is not None and not self.symbol.strip():
            raise ValueError("symbol must not be blank.")
        for symbol in self.symbols or ():
            clean = symbol.strip()
            if not clean or len(clean) > 32:
                raise ValueError(
                    f"Symbol '{symbol}' is invalid (must be 1-32 non-empty characters)."
                )
        return self


class StrategyVerdictRequest(StrategyBacktestRequest):
    strategy_name: str = Field(default="trend_exhaustion", min_length=1, max_length=64)
    universe_preset: str | None = Field(default="megacap", min_length=1, max_length=64)
    holdout_ratio: float = Field(default=0.25, ge=0.05, le=0.50)


class GateResultResponse(BaseModel):
    gate_number: int
    name: str
    passed: bool
    metric_label: str
    metric_value: str
    threshold_label: str
    threshold_value: str
    verdict_note: str


class FrictionTierResponse(BaseModel):
    multiplier: int
    commission_bps: float
    slippage_bps: float
    borrow_fee_bps: float
    total_return_pct: float
    net_profit_usd: float
    profit_factor: float
    max_drawdown_pct: float
    commission_paid_usd: float
    slippage_drag_usd: float
    borrow_paid_usd: float


class PartitionMetricsResponse(BaseModel):
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    benchmark_return: float
    win_rate: float
    profit_factor: float
    trades_count: int
    exposure_pct: float


class VerdictEquityPointResponse(BaseModel):
    session_date: str
    strategy_equity: float
    benchmark_equity: float
    drawdown_pct: float
    is_holdout: bool


class CandidateRankingResponse(BaseModel):
    strategy_name: str
    strategy_revision: str
    benchmark_symbol: str
    session_date: str
    decision_time: str
    rankings: list[RankingResponse]


class CandidateRankingRequest(StrategyBacktestRequest):
    universe_preset: str | None = Field(default="megacap", min_length=1, max_length=64)


@dataclass(frozen=True)
class ResolvedStrategyBacktest:
    """Point-in-time inputs shared by verdict and candidate-ranking requests."""

    dataset_version_id: str
    target_symbols: tuple[str, ...]
    benchmark_symbol: str
    start_date: str
    end_date: str
    bars: tuple[DailyBar, ...]
    corporate_actions: tuple[CorporateAction, ...]


def _resolve_daily_dataset_id(
    market_store: MarketDataStore,
    requested_dataset_version_id: str | None,
) -> str:
    if requested_dataset_version_id:
        _require_daily_dataset(market_store, requested_dataset_version_id)
        return requested_dataset_version_id

    versions = [
        version
        for version in market_store.list_dataset_versions()
        if version.dataset_type == DATASET_TYPE_DAILY_BARS and not version.is_corporate_actions
    ]
    if not versions:
        raise BacktestParameterError("No daily market bar datasets found in workspace.")
    return versions[0].id


def _requested_strategy_symbols(request: StrategyBacktestRequest) -> list[str]:
    if request.symbols:
        return sorted({symbol.strip().upper() for symbol in request.symbols})
    if request.symbol:
        return [request.symbol.strip().upper()]
    return []


def _strategy_corporate_actions(
    market_store: MarketDataStore,
    dataset_version_id: str,
    target_symbols: Sequence[str],
) -> tuple[CorporateAction, ...]:
    actions: list[CorporateAction] = []
    action_dataset_ids = [dataset_version_id]
    action_dataset_ids.extend(
        version.id
        for version in market_store.list_dataset_versions()
        if version.id != dataset_version_id
        and (
            version.dataset_type == DATASET_TYPE_CORPORATE_ACTIONS
            or version.is_corporate_actions
        )
    )
    for action_dataset_id in action_dataset_ids:
        for symbol in target_symbols:
            symbol_actions = market_store.corporate_actions(
                action_dataset_id,
                symbol=symbol,
            )
            if isinstance(symbol_actions, list):
                actions.extend(symbol_actions)
    return tuple(actions)


def _resolve_strategy_backtest(
    market_store: MarketDataStore,
    request: StrategyBacktestRequest,
) -> ResolvedStrategyBacktest:
    """Resolve one complete daily-bar universe without filtering requested symbols."""
    dataset_version_id = _resolve_daily_dataset_id(market_store, request.dataset_version_id)
    market_store.ensure_historical_eligibility(dataset_version_id)

    dataset_bars = market_store.history(dataset_version_id)
    available_symbols = sorted({bar.security_id.strip().upper() for bar in dataset_bars})
    requested_symbols = _requested_strategy_symbols(request)
    missing_symbols = sorted(set(requested_symbols).difference(available_symbols))
    if missing_symbols:
        raise BacktestParameterError(
            f"Symbols not found in dataset '{dataset_version_id}': {', '.join(missing_symbols)}."
        )

    benchmark_symbol = request.benchmark_symbol.strip().upper()
    benchmark_bars = market_store.history(dataset_version_id, symbol=benchmark_symbol)
    if not benchmark_bars:
        raise BacktestParameterError(
            f"Benchmark symbol '{benchmark_symbol}' has no price history in dataset "
            f"'{dataset_version_id}'."
        )

    target_symbols = sorted(
        set(requested_symbols or available_symbols).difference({benchmark_symbol})
    )
    if not target_symbols:
        raise BacktestParameterError(
            f"No eligible strategy symbols remain after excluding benchmark '{benchmark_symbol}'."
        )

    all_bars: list[DailyBar] = []
    for symbol in target_symbols:
        symbol_bars = market_store.history(dataset_version_id, symbol=symbol)
        if not symbol_bars:
            raise BacktestParameterError(
                f"No price history found for symbol '{symbol}' in dataset '{dataset_version_id}'."
            )
        all_bars.extend(symbol_bars)
    all_bars.extend(benchmark_bars)

    session_dates = sorted({bar.session_date for bar in all_bars})
    if not session_dates:
        raise BacktestParameterError(
            f"No price history found for the requested universe in dataset '{dataset_version_id}'."
        )

    return ResolvedStrategyBacktest(
        dataset_version_id=dataset_version_id,
        target_symbols=tuple(target_symbols),
        benchmark_symbol=benchmark_symbol,
        start_date=request.start_date or session_dates[0],
        end_date=request.end_date or session_dates[-1],
        bars=tuple(all_bars),
        corporate_actions=_strategy_corporate_actions(
            market_store,
            dataset_version_id,
            target_symbols,
        ),
    )


def _execution_model(request: StrategyBacktestRequest) -> ExecutionModelAssumptions:
    assumptions = request.execution
    return ExecutionModelAssumptions(
        schedule=assumptions.schedule,
        commission_rate=assumptions.commission_rate,
        slippage_rate=assumptions.slippage_rate,
        allow_shorting=assumptions.allow_shorting,
        borrow_fee_rate=assumptions.borrow_fee_rate,
        cash_interest_rate=assumptions.cash_interest_rate,
        unavailable_borrow=tuple(assumptions.unavailable_borrow),
        max_leverage=assumptions.max_leverage,
        margin_requirement=assumptions.margin_requirement,
        maintenance_margin=assumptions.maintenance_margin,
        leverage_mode=assumptions.leverage_mode,
    )


def _strategy_backtest_specification(
    request: StrategyBacktestRequest,
    resolved: ResolvedStrategyBacktest,
) -> BacktestSpecification:
    return BacktestSpecification(
        strategy_name=request.strategy_name,
        strategy_revision=request.strategy_revision,
        dataset_version_id=resolved.dataset_version_id,
        security_id=resolved.target_symbols[0],
        universe=resolved.target_symbols,
        start_date=resolved.start_date,
        end_date=resolved.end_date,
        starting_cash=request.starting_cash,
        parameters=request.parameters,
        execution=_execution_model(request),
        benchmark_security_id=resolved.benchmark_symbol,
    )


def _candidate_ranking_response(
    *,
    strategy_name: str,
    strategy_revision: str,
    benchmark_symbol: str,
    ranking_records: Sequence[RankingRecord],
) -> CandidateRankingResponse:
    if not ranking_records:
        raise BacktestParameterError(
            f"Strategy '{strategy_name}' does not produce cross-sectional rankings."
        )

    latest_snapshot = max(
        (record.session_date, record.decision_time) for record in ranking_records
    )
    latest_records = sorted(
        (
            record
            for record in ranking_records
            if (record.session_date, record.decision_time) == latest_snapshot
        ),
        key=lambda record: (
            record.rank is None,
            record.rank if record.rank is not None else 0,
            record.security_id,
        ),
    )
    return CandidateRankingResponse(
        strategy_name=strategy_name,
        strategy_revision=strategy_revision,
        benchmark_symbol=benchmark_symbol,
        session_date=latest_snapshot[0],
        decision_time=latest_snapshot[1],
        rankings=[
            RankingResponse(
                session_date=record.session_date,
                decision_time=record.decision_time,
                security_id=record.security_id,
                score=record.score,
                rank=record.rank,
                selected=record.selected,
                target_weight=record.target_weight,
                rationale=record.rationale,
            )
            for record in latest_records
        ],
    )


class StrategyVerdictResponse(BaseModel):
    overall_passed: bool
    headline_verdict: str
    rejection_reason: str | None = None
    confidence_score: float | None = None
    holdout_ratio: float
    gates: list[GateResultResponse]
    in_sample_metrics: PartitionMetricsResponse
    out_of_sample_metrics: PartitionMetricsResponse
    combined_metrics: PartitionMetricsResponse
    equity_curve: list[VerdictEquityPointResponse]
    friction_ladder: list[FrictionTierResponse]
    replay_ticks: list[ReplayTickResponse] = Field(default_factory=list)
    candidate_ranking: CandidateRankingResponse | None = None


@router.post(
    "/api/projects/{project_id}/backtests/verdict",
    response_model=StrategyVerdictResponse,
    tags=["backtests"],
)
def evaluate_strategy_verdict_route(
    project_id: UUID,
    request: StrategyVerdictRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> StrategyVerdictResponse:
    store.get_project(str(project_id))

    resolved = _resolve_strategy_backtest(market_store, request)

    verdict_spec = StrategyVerdictSpecification(
        strategy_name=request.strategy_name,
        strategy_revision=request.strategy_revision,
        dataset_version_id=resolved.dataset_version_id,
        universe=resolved.target_symbols,
        benchmark_security_id=resolved.benchmark_symbol,
        start_date=resolved.start_date,
        end_date=resolved.end_date,
        starting_cash=request.starting_cash,
        parameters=request.parameters,
        holdout_ratio=request.holdout_ratio,
        execution=_execution_model(request),
    )

    domain_result = evaluate_strategy_verdict(
        verdict_spec,
        bars=resolved.bars,
        corporate_actions=resolved.corporate_actions,
    )

    candidate_ranking_response = (
        _candidate_ranking_response(
            strategy_name=request.strategy_name,
            strategy_revision=request.strategy_revision,
            benchmark_symbol=resolved.benchmark_symbol,
            ranking_records=domain_result.ranking_records,
        )
        if domain_result.ranking_records
        else None
    )

    return StrategyVerdictResponse(
        overall_passed=domain_result.overall_passed,
        headline_verdict=domain_result.headline_verdict,
        rejection_reason=domain_result.rejection_reason,
        confidence_score=domain_result.confidence_score,
        holdout_ratio=verdict_spec.holdout_ratio,
        gates=[
            GateResultResponse(
                gate_number=g.gate_number,
                name=g.name,
                passed=g.passed,
                metric_label=g.metric_label,
                metric_value=g.metric_value,
                threshold_label=g.threshold_label,
                threshold_value=g.threshold_value,
                verdict_note=g.verdict_note,
            )
            for g in domain_result.gates
        ],
        in_sample_metrics=PartitionMetricsResponse(
            total_return=domain_result.in_sample_metrics.total_return,
            cagr=domain_result.in_sample_metrics.cagr,
            sharpe_ratio=domain_result.in_sample_metrics.sharpe_ratio,
            sortino_ratio=domain_result.in_sample_metrics.sortino_ratio,
            max_drawdown=domain_result.in_sample_metrics.max_drawdown,
            benchmark_return=domain_result.in_sample_metrics.benchmark_return,
            win_rate=domain_result.in_sample_metrics.win_rate,
            profit_factor=domain_result.in_sample_metrics.profit_factor,
            trades_count=domain_result.in_sample_metrics.trades_count,
            exposure_pct=domain_result.in_sample_metrics.exposure_pct,
        ),
        out_of_sample_metrics=PartitionMetricsResponse(
            total_return=domain_result.out_of_sample_metrics.total_return,
            cagr=domain_result.out_of_sample_metrics.cagr,
            sharpe_ratio=domain_result.out_of_sample_metrics.sharpe_ratio,
            sortino_ratio=domain_result.out_of_sample_metrics.sortino_ratio,
            max_drawdown=domain_result.out_of_sample_metrics.max_drawdown,
            benchmark_return=domain_result.out_of_sample_metrics.benchmark_return,
            win_rate=domain_result.out_of_sample_metrics.win_rate,
            profit_factor=domain_result.out_of_sample_metrics.profit_factor,
            trades_count=domain_result.out_of_sample_metrics.trades_count,
            exposure_pct=domain_result.out_of_sample_metrics.exposure_pct,
        ),
        combined_metrics=PartitionMetricsResponse(
            total_return=domain_result.combined_metrics.total_return,
            cagr=domain_result.combined_metrics.cagr,
            sharpe_ratio=domain_result.combined_metrics.sharpe_ratio,
            sortino_ratio=domain_result.combined_metrics.sortino_ratio,
            max_drawdown=domain_result.combined_metrics.max_drawdown,
            benchmark_return=domain_result.combined_metrics.benchmark_return,
            win_rate=domain_result.combined_metrics.win_rate,
            profit_factor=domain_result.combined_metrics.profit_factor,
            trades_count=domain_result.combined_metrics.trades_count,
            exposure_pct=domain_result.combined_metrics.exposure_pct,
        ),
        equity_curve=[
            VerdictEquityPointResponse(
                session_date=pt.session_date,
                strategy_equity=pt.strategy_equity,
                benchmark_equity=pt.benchmark_equity,
                drawdown_pct=pt.drawdown_pct,
                is_holdout=pt.is_holdout,
            )
            for pt in domain_result.equity_curve
        ],
        friction_ladder=[
            FrictionTierResponse(
                multiplier=tier.multiplier,
                commission_bps=tier.commission_bps,
                slippage_bps=tier.slippage_bps,
                borrow_fee_bps=tier.borrow_fee_bps,
                total_return_pct=tier.total_return_pct,
                net_profit_usd=tier.net_profit_usd,
                profit_factor=tier.profit_factor,
                max_drawdown_pct=tier.max_drawdown_pct,
                commission_paid_usd=tier.commission_paid_usd,
                slippage_drag_usd=tier.slippage_drag_usd,
                borrow_paid_usd=tier.borrow_paid_usd,
            )
            for tier in domain_result.friction_ladder
        ],
        replay_ticks=[
            ReplayTickResponse(
                date=tick.date,
                price=tick.price,
                signal=tick.signal,
                position_shares=tick.position_shares,
                portfolio_value=tick.portfolio_value,
                cash=tick.cash,
                daily_pnl=tick.daily_pnl,
                position_value=tick.position_value,
                allocation_pct=tick.allocation_pct,
                fill_actions=[
                    ReplayFillActionResponse(
                        action_type=fa.action_type,
                        quantity=fa.quantity,
                        execution_price=fa.execution_price,
                        source_fill_id=fa.source_fill_id,
                        source_fill_sequence=fa.source_fill_sequence,
                    )
                    for fa in tick.fill_actions
                ],
            )
            for tick in domain_result.replay_ticks
        ],
        candidate_ranking=candidate_ranking_response,
    )


@router.post(
    "/api/projects/{project_id}/backtests/candidate-ranking",
    response_model=CandidateRankingResponse,
    tags=["backtests"],
)
def evaluate_candidate_ranking_route(
    project_id: UUID,
    request: CandidateRankingRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> CandidateRankingResponse:
    store.get_project(str(project_id))
    resolved = _resolve_strategy_backtest(market_store, request)
    result = run_backtest(
        _strategy_backtest_specification(request, resolved),
        bars=resolved.bars,
        corporate_actions=resolved.corporate_actions,
    )
    return _candidate_ranking_response(
        strategy_name=result.specification.strategy_name,
        strategy_revision=result.specification.strategy_revision,
        benchmark_symbol=resolved.benchmark_symbol,
        ranking_records=result.ranking_records,
    )
