"""FastAPI router for indicators."""

from __future__ import annotations

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi import (
    Path as FastAPIPath,
)
from pydantic import BaseModel, Field

from ..indicators import (
    IndicatorMetadata,
    IndicatorParameter,
    IndicatorPoint,
    IndicatorSeries,
    calculate_indicator,
    get_indicator_spec,
    list_indicators,
)
from ..json_types import JsonValue
from ..market_data import MarketDataStore
from .deps import get_market_store

router = APIRouter()


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


@router.get(
    "/api/indicators",
    response_model=list[IndicatorMetadataResponse],
    tags=["indicators"],
)
def get_indicators() -> list[IndicatorMetadataResponse]:
    return [_indicator_meta_response(spec) for spec in list_indicators()]


@router.get(
    "/api/indicators/{name}",
    response_model=IndicatorMetadataResponse,
    tags=["indicators"],
)
def get_indicator_by_name(
    name: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_]{1,64}$"),
) -> IndicatorMetadataResponse:
    return _indicator_meta_response(get_indicator_spec(name))


@router.post(
    "/api/indicators/calculate",
    response_model=IndicatorSeriesResponse,
    tags=["indicators"],
)
def calculate_indicator_endpoint(
    request: IndicatorCalculateRequest,
    market_store: MarketDataStore = Depends(get_market_store),
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
