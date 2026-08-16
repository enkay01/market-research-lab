"""Deterministic calculation and parameter tests for technical indicators."""

from __future__ import annotations

import pytest

from market_research_lab.indicators import (
    IndicatorCalculationError,
    MaCrossoverParams,
    ParameterValidationError,
    calculate_ema,
    calculate_indicator,
    calculate_ma_crossover,
    calculate_sma,
    get_indicator_spec,
    list_indicators,
)


def test_list_indicators_exposes_typed_parameter_metadata():
    specs = list_indicators()
    names = {spec.name for spec in specs}
    assert "sma" in names
    assert "ema" in names
    assert "moving_average_crossover" in names

    crossover_spec = get_indicator_spec("moving_average_crossover")
    assert crossover_spec.display_name == "Moving Average Crossover"
    param_names = {p.name for p in crossover_spec.parameters}
    assert "fast_period" in param_names
    assert "slow_period" in param_names
    assert "ma_type" in param_names

    fast_param = next(p for p in crossover_spec.parameters if p.name == "fast_period")
    assert fast_param.param_type == "int"
    assert fast_param.default == 20
    assert fast_param.min_value == 1


def test_sma_calculation_warmup_and_accuracy():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    period = 3
    result = calculate_sma(prices, period=period)

    assert len(result) == 5
    # First 2 (period - 1) points must be None (warm-up)
    assert result[0] is None
    assert result[1] is None
    # Subsequent points: exact arithmetic means
    assert result[2] == pytest.approx(11.0)
    assert result[3] == pytest.approx(12.0)
    assert result[4] == pytest.approx(13.0)


def test_sma_rejects_invalid_period():
    with pytest.raises(ParameterValidationError):
        calculate_sma([10.0, 12.0], period=0)

    with pytest.raises(ParameterValidationError):
        calculate_sma([10.0, 12.0], period=-5)


def test_ema_calculation_warmup_and_accuracy():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    period = 3
    # Multiplier k = 2 / (3 + 1) = 0.5
    # Seed at index 2 (period 3): SMA = (10 + 11 + 12) / 3 = 11.0
    # Index 3 (13.0): 13.0 * 0.5 + 11.0 * 0.5 = 12.0
    # Index 4 (14.0): 14.0 * 0.5 + 12.0 * 0.5 = 13.0
    result = calculate_ema(prices, period=period)

    assert len(result) == 5
    assert result[0] is None
    assert result[1] is None
    assert result[2] == pytest.approx(11.0)
    assert result[3] == pytest.approx(12.0)
    assert result[4] == pytest.approx(13.0)


def test_ma_crossover_calculation_and_signals():
    dates = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
    ]
    prices = [10.0, 12.0, 14.0, 16.0, 12.0, 10.0, 8.0]

    series = calculate_ma_crossover(
        session_dates=dates,
        prices=prices,
        config=MaCrossoverParams(fast_period=2, slow_period=4, ma_type="sma"),
    )

    assert len(series.points) == 7
    assert series.warmup_period == 3
    assert series.total_bars == 7
    assert series.valid_bars == 4

    # Check warm-up points (index 0, 1, 2)
    for i in range(3):
        assert series.points[i].is_warmup is True
        assert series.points[i].values.get("slow_ma") is None
        assert series.points[i].session_date == dates[i]
        assert series.points[i].price == prices[i]

    # Index 3: First valid point
    p3 = series.points[3]
    assert p3.is_warmup is False
    assert p3.values["fast_ma"] == pytest.approx(15.0)
    assert p3.values["slow_ma"] == pytest.approx(13.0)
    assert p3.values["spread"] == pytest.approx(2.0)
    assert p3.values["state"] == "bullish_above"

    # Index 4: Remains bullish above
    p4 = series.points[4]
    assert p4.is_warmup is False
    assert p4.values["fast_ma"] == pytest.approx(14.0)
    assert p4.values["slow_ma"] == pytest.approx(13.5)
    assert p4.values["spread"] == pytest.approx(0.5)
    assert p4.values["state"] == "bullish_above"

    # Index 5: Crossed below
    p5 = series.points[5]
    assert p5.is_warmup is False
    assert p5.values["fast_ma"] == pytest.approx(11.0)
    assert p5.values["slow_ma"] == pytest.approx(13.0)
    assert p5.values["spread"] == pytest.approx(-2.0)
    assert p5.values["state"] == "bearish_cross"

    # Index 6: Stays bearish below
    p6 = series.points[6]
    assert p6.is_warmup is False
    assert p6.values["fast_ma"] == pytest.approx(9.0)
    assert p6.values["slow_ma"] == pytest.approx(11.5)
    assert p6.values["spread"] == pytest.approx(-2.5)
    assert p6.values["state"] == "bearish_below"


def test_ma_crossover_validates_periods():
    dates = ["2024-01-02", "2024-01-03"]
    prices = [10.0, 11.0]

    with pytest.raises(ParameterValidationError, match="fast_period must be strictly less than"):
        calculate_ma_crossover(
            session_dates=dates,
            prices=prices,
            config=MaCrossoverParams(fast_period=5, slow_period=5, ma_type="sma"),
        )

    with pytest.raises(ParameterValidationError, match="fast_period must be strictly less than"):
        calculate_ma_crossover(
            session_dates=dates,
            prices=prices,
            config=MaCrossoverParams(fast_period=10, slow_period=5, ma_type="sma"),
        )


def test_calculate_indicator_dispatcher():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    prices = [100.0, 102.0, 104.0, 106.0]

    # Dispatch SMA
    sma_series = calculate_indicator(
        name="sma",
        session_dates=dates,
        prices=prices,
        parameters={"period": 2},
    )
    assert sma_series.indicator_name == "sma"
    assert len(sma_series.points) == 4
    assert sma_series.points[0].is_warmup is True
    assert sma_series.points[1].values["sma"] == pytest.approx(101.0)
    assert sma_series.points[2].values["sma"] == pytest.approx(103.0)

    # Dispatch EMA
    ema_series = calculate_indicator(
        name="ema",
        session_dates=dates,
        prices=prices,
        parameters={"period": 2},
    )
    assert ema_series.indicator_name == "ema"
    assert len(ema_series.points) == 4
    assert ema_series.points[0].is_warmup is True
    assert ema_series.points[1].values["ema"] == pytest.approx(101.0)

    # Dispatch unknown
    with pytest.raises(IndicatorCalculationError, match="Unknown indicator"):
        calculate_indicator(
            name="unknown_indicator",
            session_dates=dates,
            prices=prices,
            parameters={},
        )
