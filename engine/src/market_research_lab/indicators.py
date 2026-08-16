"""Deterministic calculation engine and registry for technical indicators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from pydantic import BaseModel, Field

from .json_types import JsonValue


class ParameterValidationError(ValueError):
    """Raised when an indicator parameter fails validation constraints."""


class IndicatorCalculationError(Exception):
    """Raised when an indicator cannot be calculated or is unknown."""


@dataclass(frozen=True)
class IndicatorParameter:
    """Typed specification for an indicator configuration parameter."""

    name: str
    param_type: Literal["int", "float", "str", "bool"]
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: list[str] | None = None


@dataclass(frozen=True)
class IndicatorMetadata:
    """Descriptor and parameter contract for a technical indicator."""

    name: str
    display_name: str
    description: str
    parameters: list[IndicatorParameter]
    outputs: list[str]


@dataclass(frozen=True)
class IndicatorPoint:
    """Time-aligned point in an indicator output series."""

    session_date: str
    price: float
    values: dict[str, JsonValue]
    is_warmup: bool


@dataclass(frozen=True)
class IndicatorSeries:
    """Complete immutable indicator series aligned to market observation dates."""

    indicator_name: str
    parameters: dict[str, JsonValue]
    total_bars: int
    warmup_period: int
    valid_bars: int
    points: list[IndicatorPoint]


class SmaParams(BaseModel):
    """Validated boundary parameters for Simple Moving Average."""

    period: int = Field(default=20, ge=1, le=500)


class EmaParams(BaseModel):
    """Validated boundary parameters for Exponential Moving Average."""

    period: int = Field(default=20, ge=1, le=500)


class MaCrossoverParams(BaseModel):
    """Validated boundary parameters for Moving Average Crossover."""

    fast_period: int = Field(default=20, ge=1, le=250)
    slow_period: int = Field(default=50, ge=2, le=500)
    ma_type: Literal["sma", "ema"] = "sma"


def calculate_sma(prices: Sequence[float], *, period: int) -> list[float | None]:
    """Calculate simple moving average with explicit warmup None values."""
    if period < 1:
        raise ParameterValidationError(f"period must be >= 1, got {period}.")

    n = len(prices)
    if n == 0:
        return []

    result: list[float | None] = [None] * n
    if n < period:
        return result

    window_sum = sum(prices[:period])
    result[period - 1] = window_sum / period

    for i in range(period, n):
        window_sum += prices[i] - prices[i - period]
        result[i] = window_sum / period

    return result


def calculate_ema(prices: Sequence[float], *, period: int) -> list[float | None]:
    """Calculate exponential moving average with explicit warmup None values."""
    if period < 1:
        raise ParameterValidationError(f"period must be >= 1, got {period}.")

    n = len(prices)
    if n == 0:
        return []

    result: list[float | None] = [None] * n
    if n < period:
        return result

    multiplier = 2.0 / (period + 1.0)
    seed = sum(prices[:period]) / period
    result[period - 1] = seed

    prev_ema = seed
    for i in range(period, n):
        current_ema = (prices[i] * multiplier) + (prev_ema * (1.0 - multiplier))
        result[i] = current_ema
        prev_ema = current_ema

    return result


def calculate_ma_crossover(
    session_dates: Sequence[str],
    prices: Sequence[float],
    *,
    config: MaCrossoverParams = MaCrossoverParams(),
) -> IndicatorSeries:
    """Calculate moving average crossover with spread and directional cross signals."""
    actual_fast = config.fast_period
    actual_slow = config.slow_period
    actual_type = config.ma_type

    if actual_fast >= actual_slow:
        raise ParameterValidationError(
            f"fast_period must be strictly less than slow_period "
            f"(got fast={actual_fast}, slow={actual_slow})."
        )

    n = len(prices)
    if len(session_dates) != n:
        raise ParameterValidationError(
            f"session_dates length ({len(session_dates)}) must match prices length ({n})."
        )

    if actual_type == "sma":
        fast_vals = calculate_sma(prices, period=actual_fast)
        slow_vals = calculate_sma(prices, period=actual_slow)
    else:
        fast_vals = calculate_ema(prices, period=actual_fast)
        slow_vals = calculate_ema(prices, period=actual_slow)

    points: list[IndicatorPoint] = []
    prev_spread: float | None = None

    for i in range(n):
        f_val = fast_vals[i]
        s_val = slow_vals[i]
        date_str = session_dates[i]
        price_val = prices[i]

        if f_val is None or s_val is None:
            points.append(
                IndicatorPoint(
                    session_date=date_str,
                    price=price_val,
                    values={
                        "fast_ma": f_val,
                        "slow_ma": s_val,
                        "spread": None,
                        "state": "warmup",
                    },
                    is_warmup=True,
                )
            )
            continue

        spread = f_val - s_val
        if prev_spread is None:
            if spread > 0:
                state = "bullish_above"
            elif spread < 0:
                state = "bearish_below"
            else:
                state = "neutral"
        else:
            if prev_spread <= 0 and spread > 0:
                state = "bullish_cross"
            elif prev_spread >= 0 and spread < 0:
                state = "bearish_cross"
            elif spread > 0:
                state = "bullish_above"
            elif spread < 0:
                state = "bearish_below"
            else:
                state = "neutral"

        prev_spread = spread
        points.append(
            IndicatorPoint(
                session_date=date_str,
                price=price_val,
                values={
                    "fast_ma": round(f_val, 4),
                    "slow_ma": round(s_val, 4),
                    "spread": round(spread, 4),
                    "state": state,
                },
                is_warmup=False,
            )
        )

    warmup_count = actual_slow - 1 if n >= actual_slow else n
    valid_count = max(0, n - warmup_count)

    return IndicatorSeries(
        indicator_name="moving_average_crossover",
        parameters={
            "fast_period": actual_fast,
            "slow_period": actual_slow,
            "ma_type": actual_type,
        },
        total_bars=n,
        warmup_period=warmup_count,
        valid_bars=valid_count,
        points=points,
    )


def _calculate_sma_series(
    session_dates: Sequence[str],
    prices: Sequence[float],
    config: SmaParams,
) -> IndicatorSeries:
    period = config.period
    sma_vals = calculate_sma(prices, period=period)
    n = len(prices)
    points: list[IndicatorPoint] = []
    for i in range(n):
        val = sma_vals[i]
        points.append(
            IndicatorPoint(
                session_date=session_dates[i],
                price=prices[i],
                values={"sma": round(val, 4) if val is not None else None},
                is_warmup=val is None,
            )
        )
    warmup_count = period - 1 if n >= period else n
    return IndicatorSeries(
        indicator_name="sma",
        parameters={"period": period},
        total_bars=n,
        warmup_period=warmup_count,
        valid_bars=max(0, n - warmup_count),
        points=points,
    )


def _calculate_ema_series(
    session_dates: Sequence[str],
    prices: Sequence[float],
    config: EmaParams,
) -> IndicatorSeries:
    period = config.period
    ema_vals = calculate_ema(prices, period=period)
    n = len(prices)
    points: list[IndicatorPoint] = []
    for i in range(n):
        val = ema_vals[i]
        points.append(
            IndicatorPoint(
                session_date=session_dates[i],
                price=prices[i],
                values={"ema": round(val, 4) if val is not None else None},
                is_warmup=val is None,
            )
        )
    warmup_count = period - 1 if n >= period else n
    return IndicatorSeries(
        indicator_name="ema",
        parameters={"period": period},
        total_bars=n,
        warmup_period=warmup_count,
        valid_bars=max(0, n - warmup_count),
        points=points,
    )


INDICATOR_REGISTRY: dict[str, IndicatorMetadata] = {
    "sma": IndicatorMetadata(
        name="sma",
        display_name="Simple Moving Average",
        description="Arithmetic mean of prices over a trailing lookback window.",
        parameters=[
            IndicatorParameter(
                name="period",
                param_type="int",
                default=20,
                description="Lookback window size in daily bars",
                min_value=1,
                max_value=500,
            )
        ],
        outputs=["sma"],
    ),
    "ema": IndicatorMetadata(
        name="ema",
        display_name="Exponential Moving Average",
        description="Exponentially weighted moving average giving higher weight to recent prices.",
        parameters=[
            IndicatorParameter(
                name="period",
                param_type="int",
                default=20,
                description="Lookback window size in daily bars",
                min_value=1,
                max_value=500,
            )
        ],
        outputs=["ema"],
    ),
    "moving_average_crossover": IndicatorMetadata(
        name="moving_average_crossover",
        display_name="Moving Average Crossover",
        description=(
            "Dual moving-average system comparing fast and slow trends "
            "to identify direction and crossovers."
        ),
        parameters=[
            IndicatorParameter(
                name="fast_period",
                param_type="int",
                default=20,
                description="Fast lookback period in daily bars",
                min_value=1,
                max_value=250,
            ),
            IndicatorParameter(
                name="slow_period",
                param_type="int",
                default=50,
                description="Slow lookback period in daily bars",
                min_value=2,
                max_value=500,
            ),
            IndicatorParameter(
                name="ma_type",
                param_type="str",
                default="sma",
                description="Moving average calculation method ('sma' or 'ema')",
                options=["sma", "ema"],
            ),
        ],
        outputs=["fast_ma", "slow_ma", "spread", "state"],
    ),
}


def list_indicators() -> list[IndicatorMetadata]:
    """Return list of all registered indicator metadata descriptors."""
    return list(INDICATOR_REGISTRY.values())


def get_indicator_spec(name: str) -> IndicatorMetadata:
    """Retrieve metadata descriptor for a named indicator."""
    spec = INDICATOR_REGISTRY.get(name)
    if spec is None:
        raise IndicatorCalculationError(f"Unknown indicator '{name}'.")
    return spec


def calculate_indicator(
    name: str,
    session_dates: Sequence[str],
    prices: Sequence[float],
    parameters: dict[str, JsonValue],
) -> IndicatorSeries:
    """Dispatch and calculate an indicator series deterministically."""
    if name == "sma":
        cfg_sma = SmaParams.model_validate(parameters)
        return _calculate_sma_series(session_dates, prices, cfg_sma)
    if name == "ema":
        cfg_ema = EmaParams.model_validate(parameters)
        return _calculate_ema_series(session_dates, prices, cfg_ema)
    if name == "moving_average_crossover":
        cfg_cross = MaCrossoverParams.model_validate(parameters)
        return calculate_ma_crossover(session_dates, prices, config=cfg_cross)

    raise IndicatorCalculationError(
        f"Unknown indicator '{name}'. Available: {list(INDICATOR_REGISTRY.keys())}"
    )
