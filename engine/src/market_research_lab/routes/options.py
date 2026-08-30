"""FastAPI router for options credit spread backtests."""

from __future__ import annotations

import re
from datetime import date
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
from pydantic import BaseModel, Field, field_validator, model_validator

from ..json_types import JsonValue
from ..market_data import MarketDataStore, OptionMarketData
from ..option_backtest import (
    OptionBacktestError,
    OptionsBacktestSpecification,
    run_option_backtest,
)
from ..projects import (
    FailedOptionsBacktestRunRecord,
    OptionsBacktestRunRecord,
    ProjectStore,
)
from .deps import (
    get_market_store,
    get_project_store,
    log_run_event,
)

router = APIRouter()


class OptionsBacktestRunRequest(BaseModel):
    dataset_version_id: str = Field(min_length=1)
    daily_dataset_version_id: str | None = Field(default=None, min_length=1)
    strategy_name: str = Field(default="put_credit_spread", min_length=1, max_length=64)
    strategy_revision: str = Field(default="v1", min_length=1, max_length=64)
    symbol: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9._-]*$"
    )
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=20)
    watchlist: list[str] | None = Field(default=None, min_length=1, max_length=20)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    starting_cash: float = Field(default=100000.0, gt=0, allow_inf_nan=False)
    path: Literal["worst", "best"] = "worst"
    automatic_selection: bool | None = None
    fixed_short_contract_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    fixed_long_contract_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    dte_min: int = Field(default=30, ge=0, le=365)
    dte_max: int = Field(default=45, ge=0, le=365)
    delta_min: float = Field(default=0.15, ge=0, le=1)
    delta_max: float = Field(default=0.20, ge=0, le=1)
    target_delta: float = Field(default=0.175, ge=0, le=1)
    iv_min: float = Field(default=0.30, ge=0, le=5)
    iv_max: float = Field(default=0.55, ge=0, le=5)
    previous_day_volume_min: float = Field(default=100000.0, ge=0, allow_inf_nan=False)
    preferred_width: float = Field(default=2.5, gt=0, allow_inf_nan=False)
    fallback_width: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    risk_per_position: float = Field(default=0.02, gt=0, le=1)
    max_open_risk: float = Field(default=0.10, gt=0, le=1)
    max_open_securities: int = Field(default=3, ge=1, le=20)
    similarity_limit: float = Field(default=0.70, ge=-1, le=1)
    fee_per_leg: float = Field(default=0.65, ge=0, allow_inf_nan=False)
    risk_free_rate: float = Field(default=0.0, allow_inf_nan=False)
    dividend_yield: float = Field(default=0.0, allow_inf_nan=False)
    cash_interest_rate: float = Field(default=0.0, allow_inf_nan=False)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("symbols", "watchlist")
    @classmethod
    def normalize_symbol_list(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        if any(re.fullmatch(r"[A-Z][A-Z0-9._-]*", value) is None for value in cleaned):
            raise ValueError(
                "Security symbols may contain only letters, numbers, dots, underscores, "
                "and hyphens."
            )
        return cleaned

    @model_validator(mode="after")
    def validate_symbols(self) -> OptionsBacktestRunRequest:
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as error:
            raise ValueError("start_date and end_date must be valid calendar dates.") from error
        if start > end:
            raise ValueError("start_date must be on or before end_date.")
        if not self.symbol and not self.symbols and not self.watchlist:
            raise ValueError("Either 'symbol', 'symbols', or 'watchlist' must be provided.")
        if self.symbols and self.watchlist:
            raise ValueError("Use either 'symbols' or 'watchlist', not both.")
        if (
            self.dte_min > self.dte_max
            or self.delta_min > self.delta_max
            or self.iv_min > self.iv_max
        ):
            raise ValueError("Minimum selection bounds must not exceed maximum bounds.")
        if bool(self.fixed_short_contract_id) != bool(self.fixed_long_contract_id):
            raise ValueError("Both fixed contract IDs are required together.")
        return self


class OptionsBacktestResponse(BaseModel):
    run_id: str | None = None
    specification: dict[str, JsonValue]
    summary: dict[str, JsonValue]
    positions: list[dict[str, JsonValue]]
    best_positions: list[dict[str, JsonValue]] = Field(default_factory=list)
    blocked_candidates: list[dict[str, JsonValue]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest: dict[str, JsonValue]
    equity_curve: list[dict[str, JsonValue]] = Field(default_factory=list)
    benchmark_equity_curve: list[dict[str, JsonValue]] = Field(default_factory=list)


@router.post(
    "/api/projects/{project_id}/options-backtests",
    response_model=OptionsBacktestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["options-backtests"],
)
def run_project_options_backtest(
    project_id: UUID,
    request: OptionsBacktestRunRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> dict[str, JsonValue]:
    store.get_project(str(project_id))
    symbols = tuple(
        request.watchlist or request.symbols or ([request.symbol] if request.symbol else [])
    )
    automatic = request.automatic_selection
    if automatic is None:
        automatic = not bool(request.fixed_short_contract_id)
    parameters = request.model_dump(mode="json")
    input_dataset_versions = {"options_market_data": request.dataset_version_id}
    if request.daily_dataset_version_id:
        input_dataset_versions["daily_market_data"] = request.daily_dataset_version_id
    try:
        coverage = market_store.coverage(request.dataset_version_id)
        if not coverage.source.lower().startswith("alpaca"):
            raise OptionBacktestError(
                "Options Backtest Runs require an Alpaca Option Dataset Version."
            )
        market_data = market_store.option_market_data(request.dataset_version_id)
        daily_bars = market_data.daily_bars
        if request.daily_dataset_version_id:
            market_store.ensure_historical_eligibility(request.daily_dataset_version_id)
            loaded_daily = market_store.history(request.daily_dataset_version_id)
            if isinstance(loaded_daily, list):
                daily_bars = tuple(loaded_daily)
        market_data = OptionMarketData(
            contracts=market_data.contracts,
            option_trades=market_data.option_trades,
            underlying_bars=market_data.underlying_bars,
            daily_bars=daily_bars,
            earnings=market_data.earnings,
            dataset_version_id=request.dataset_version_id,
            provider=market_data.provider,
        )
        specification = OptionsBacktestSpecification(
            strategy_name=request.strategy_name,
            strategy_revision=request.strategy_revision,
            dataset_version_id=request.dataset_version_id,
            start_date=request.start_date,
            end_date=request.end_date,
            starting_cash=request.starting_cash,
            symbols=symbols,
            watchlist=tuple(request.watchlist or ()),
            path=request.path,
            automatic_selection=automatic,
            fixed_short_contract_id=request.fixed_short_contract_id,
            fixed_long_contract_id=request.fixed_long_contract_id,
            dte_min=request.dte_min,
            dte_max=request.dte_max,
            delta_min=request.delta_min,
            delta_max=request.delta_max,
            target_delta=request.target_delta,
            iv_min=request.iv_min,
            iv_max=request.iv_max,
            previous_day_volume_min=request.previous_day_volume_min,
            preferred_width=request.preferred_width,
            fallback_width=request.fallback_width,
            risk_per_position=request.risk_per_position,
            max_open_risk=request.max_open_risk,
            max_open_securities=request.max_open_securities,
            similarity_limit=request.similarity_limit,
            fee_per_leg=request.fee_per_leg,
            risk_free_rate=request.risk_free_rate,
            dividend_yield=request.dividend_yield,
            cash_interest_rate=request.cash_interest_rate,
        )
        result = run_option_backtest(specification, market_data=market_data)
    except Exception as error:
        store.create_failed_options_backtest_run(
            str(project_id),
            FailedOptionsBacktestRunRecord(
                strategy_revision=request.strategy_revision,
                dataset_version_ids=list(input_dataset_versions.values()),
                input_dataset_versions=input_dataset_versions,
                parameters=parameters,
                error_message=str(error),
            ),
        )
        raise
    result_payload = result.to_json()
    result_manifest = result_payload.get("manifest")
    if isinstance(result_manifest, dict):
        result_manifest["source_sha256"] = store.source_fingerprint()
        result_manifest["input_dataset_versions"] = input_dataset_versions
    run_id = store.create_options_backtest_result(
        str(project_id),
        OptionsBacktestRunRecord(
            strategy_revision=request.strategy_revision,
            dataset_version_ids=list(input_dataset_versions.values()),
            input_dataset_versions=input_dataset_versions,
            parameters=parameters,
            result=result_payload,
        ),
    )
    result_payload["run_id"] = run_id
    log_run_event(project_id, run_id, "Options Backtest Run completed.")
    return result_payload


@router.get(
    "/api/projects/{project_id}/options-backtests",
    response_model=list[OptionsBacktestResponse],
    tags=["options-backtests"],
)
def list_project_options_backtests(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[dict[str, JsonValue]]:
    return [item["result"] for item in store.list_options_backtest_results(str(project_id))]


@router.get(
    "/api/projects/{project_id}/options-backtests/{run_id}",
    response_model=OptionsBacktestResponse,
    tags=["options-backtests"],
)
def get_project_options_backtest(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    store: ProjectStore = Depends(get_project_store),
) -> dict[str, JsonValue]:
    item = store.get_options_backtest_result(str(project_id), run_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Options Backtest Run not found."
        )
    return item["result"]


@router.get(
    "/api/projects/{project_id}/runs/{run_id}/options_backtest",
    response_model=OptionsBacktestResponse,
    tags=["options-backtests"],
)
def get_run_options_backtest(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    store: ProjectStore = Depends(get_project_store),
) -> dict[str, JsonValue]:
    return get_project_options_backtest(project_id, run_id, store=store)


@router.get(
    "/api/projects/{project_id}/options-backtests/{run_id}/export/{format_type}",
    tags=["options-backtests"],
)
def export_options_backtest(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    format_type: Literal["json", "csv", "html"] = FastAPIPath(),
    store: ProjectStore = Depends(get_project_store),
) -> Response:
    try:
        artifact = store.get_options_backtest_export(str(project_id), run_id, format_type)
    except FileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )
