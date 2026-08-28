"""Tests for the combined predictive model Strategy (MOD-008)."""

from market_research_lab.strategies import (
    MarketView,
    evaluate_strategy,
    get_strategy_spec,
    list_strategies,
)


def test_combined_strategy_registered():
    """Verify combined_predictive_model is registered with proper metadata."""
    strategies = list_strategies()
    names = [s.name for s in strategies]
    assert "combined_predictive_model" in names

    spec = get_strategy_spec("combined_predictive_model")
    assert spec.display_name == "Combined Predictive Model"
    param_names = [p.name for p in spec.parameters]
    assert "threshold" in param_names
    assert "momentum_weight" in param_names
    assert "potts_weight" in param_names
    assert "lookback_window" in param_names


def test_combined_strategy_warmup():
    """Verify combined strategy returns flat weight during warmup with insufficient observations."""
    market_view = MarketView(
        security_id="AAPL",
        session_dates=("2024-01-02", "2024-01-03", "2024-01-04"),
        prices=(100.0, 101.0, 102.0),
    )
    result = evaluate_strategy(
        "combined_predictive_model",
        market_view,
        parameters={"lookback_window": 60, "momentum_period": 20},
        decision_time="2024-01-04T20:00:00Z",
    )
    assert len(result.targets) == 1
    target = result.targets[0]
    assert target.weight == 0.0
    assert target.indicator_state == "warmup"


def test_combined_strategy_long_short_evaluation():
    """Verify combined strategy produces directional signals on sufficient data."""
    # Generate 80 daily price observations with upward trend
    prices = [100.0 * (1.002 ** i) for i in range(80)]
    dates = [f"2024-01-{i+1:02d}" if i < 30 else f"2024-02-{i-29:02d}" for i in range(80)]

    market_view = MarketView(
        security_id="AAPL",
        session_dates=tuple(dates),
        prices=tuple(prices),
    )

    result = evaluate_strategy(
        "combined_predictive_model",
        market_view,
        parameters={
            "threshold": 0.0001,
            "momentum_weight": 0.5,
            "potts_weight": 0.5,
            "lookback_window": 30,
            "momentum_period": 10,
            "mode": "long_short",
        },
        decision_time="2024-02-50T20:00:00Z",
    )

    assert result.strategy_name == "combined_predictive_model"
    assert len(result.targets) == 1
    target = result.targets[0]
    assert target.weight == 1.0
    assert target.indicator_state == "bullish_combined"
    assert "exceeds threshold" in target.rationale
