"""Deterministic evaluation and parameter tests for long/flat Strategies."""

from __future__ import annotations

import pytest

from market_research_lab.strategies import (
    MarketView,
    StrategyEvaluationError,
    StrategyParameterValidationError,
    evaluate_strategy,
    get_strategy_spec,
    list_strategies,
)


def _view(prices: list[float]) -> MarketView:
    dates = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
    ][: len(prices)]
    return MarketView(security_id="AAPL", session_dates=tuple(dates), prices=tuple(prices))


def test_list_strategies_exposes_typed_parameter_metadata():
    specs = list_strategies()
    names = {spec.name for spec in specs}
    assert "long_flat_moving_average" in names

    spec = get_strategy_spec("long_flat_moving_average")
    assert spec.display_name == "Long/Flat Moving Average"
    param_names = {p.name for p in spec.parameters}
    assert param_names == {"fast_period", "slow_period", "ma_type"}

    fast = next(p for p in spec.parameters if p.name == "fast_period")
    assert fast.param_type == "int"
    assert fast.default == 20
    assert fast.min_value == 1


def test_long_flat_ma_emits_long_when_bullish():
    # Prices climb so the fast SMA(2) stays above the slow SMA(4).
    view = _view([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0])
    result = evaluate_strategy(
        "long_flat_moving_average",
        view,
        {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        decision_time="2024-01-10T21:00:00Z",
    )

    assert result.strategy_name == "long_flat_moving_average"
    assert result.indicator_name == "moving_average_crossover"
    assert result.latest_session_date == "2024-01-10"
    assert len(result.targets) == 1

    target = result.targets[0]
    assert target.security_id == "AAPL"
    assert target.weight == 1.0
    assert target.decision_time == "2024-01-10T21:00:00Z"
    assert target.indicator_state == "bullish_above"
    assert "long" in target.rationale


def test_long_flat_ma_emits_flat_when_bearish():
    # Prices fall so the fast SMA(2) drops below the slow SMA(4).
    view = _view([16.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0])
    result = evaluate_strategy(
        "long_flat_moving_average",
        view,
        {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        decision_time="2024-01-10T21:00:00Z",
    )

    target = result.targets[0]
    assert target.weight == 0.0
    assert target.indicator_state == "bearish_below"
    assert "flat" in target.rationale


def test_long_flat_ma_emits_flat_during_warmup():
    # Too few observations for the slow SMA(4) to be valid.
    view = _view([10.0, 11.0, 12.0])
    result = evaluate_strategy(
        "long_flat_moving_average",
        view,
        {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        decision_time="2024-01-04T21:00:00Z",
    )

    target = result.targets[0]
    assert target.weight == 0.0
    assert target.indicator_state == "warmup"
    assert "flat" in target.rationale


def test_long_flat_ma_supports_ema_ma_type():
    view = _view([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0])
    result = evaluate_strategy(
        "long_flat_moving_average",
        view,
        {"fast_period": 2, "slow_period": 4, "ma_type": "ema"},
        decision_time="2024-01-10T21:00:00Z",
    )

    assert result.targets[0].weight == 1.0
    assert result.parameters["ma_type"] == "ema"


def test_long_flat_ma_rejects_fast_not_less_than_slow():
    view = _view([10.0, 11.0, 12.0, 13.0])
    with pytest.raises(
        StrategyParameterValidationError, match="fast_period must be strictly less than"
    ):
        evaluate_strategy(
            "long_flat_moving_average",
            view,
            {"fast_period": 5, "slow_period": 5, "ma_type": "sma"},
            decision_time="2024-01-05T21:00:00Z",
        )


def test_long_flat_ma_rejects_misaligned_market_view():
    view = MarketView(
        security_id="AAPL",
        session_dates=("2024-01-02", "2024-01-03", "2024-01-04"),
        prices=(10.0, 11.0),
    )
    with pytest.raises(StrategyParameterValidationError, match="must match"):
        evaluate_strategy(
            "long_flat_moving_average",
            view,
            {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
            decision_time="2024-01-05T21:00:00Z",
        )


def test_evaluate_strategy_unknown_name_raises():
    view = _view([10.0, 11.0, 12.0, 13.0])
    with pytest.raises(StrategyEvaluationError, match="Unknown Strategy"):
        evaluate_strategy(
            "mystery_strategy",
            view,
            {},
            decision_time="2024-01-05T21:00:00Z",
        )


def test_rsi_mean_reversion_strategy():
    from market_research_lab.strategies import MarketView, evaluate_strategy, get_strategy_spec

    spec = get_strategy_spec("rsi_mean_reversion")
    assert spec is not None
    assert spec.name == "rsi_mean_reversion"

    prices = (100.0, 95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0)
    dates = tuple(f"2024-01-{i:02d}" for i in range(1, len(prices) + 1))
    market_view = MarketView(security_id="AAPL", session_dates=dates, prices=prices)

    evaluation = evaluate_strategy(
        "rsi_mean_reversion",
        market_view=market_view,
        parameters={"period": 14, "oversold": 30.0, "overbought": 70.0},
        decision_time="2024-01-16T16:00:00Z",
    )
    assert len(evaluation.targets) == 1
    assert evaluation.targets[0].weight == 1.0
    assert evaluation.targets[0].indicator_state == "oversold_buy"



def test_put_credit_spread_strategy_evaluation():
    from market_research_lab.strategies import MarketView, evaluate_strategy, get_strategy_spec

    spec = get_strategy_spec("put_credit_spread_strategy")
    assert spec is not None
    assert spec.name == "put_credit_spread_strategy"

    prices = (100.0, 102.0, 105.0, 103.0, 107.0, 110.0, 112.0)
    dates = tuple(f"2024-01-{i:02d}" for i in range(1, len(prices) + 1))
    market_view = MarketView(security_id="SPY", session_dates=dates, prices=prices)

    evaluation = evaluate_strategy(
        "put_credit_spread_strategy",
        market_view=market_view,
        parameters={"short_delta": 0.20, "spread_width": 5.0, "target_dte": 30},
        decision_time="2024-01-07T16:00:00Z",
    )
    assert len(evaluation.targets) == len(prices)



