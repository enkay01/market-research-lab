"""Example custom strategy for Market Research Lab."""

from market_research_lab.strategies import (
    MarketView,
    StrategyEvaluation,
    StrategyMetadata,
    StrategyParameter,
    StrategyTarget,
)


SPEC = StrategyMetadata(
    name="custom_momentum_filter",
    display_name="Custom Momentum Filter",
    description="Allocates 100% when the close price exceeds the lookback average, 0% otherwise.",
    parameters=[
        StrategyParameter(
            name="lookback",
            param_type="int",
            default=20,
            description="Lookback window in daily bars",
            min_value=5,
            max_value=200,
        ),
    ],
    outputs=["weight", "rationale", "indicator_state"],
)


def evaluate(
    market_view: MarketView,
    parameters: dict[str, int | float | str | bool],
    *,
    decision_time: str,
) -> StrategyEvaluation:
    """Evaluate custom strategy logic on eligible observations."""
    lookback = int(parameters.get("lookback", 20))
    prices = list(market_view.prices)

    if len(prices) < lookback:
        weight = 0.0
        state = "warmup"
        rationale = f"Insufficient history ({len(prices)} < {lookback}); holding flat."
    else:
        avg_price = sum(prices[-lookback:]) / lookback
        latest_price = prices[-1]
        if latest_price > avg_price:
            weight = 1.0
            state = "bullish"
            rationale = f"Price ({latest_price:.2f}) > {lookback}-bar average ({avg_price:.2f})."
        else:
            weight = 0.0
            state = "bearish"
            rationale = f"Price ({latest_price:.2f}) <= {lookback}-bar average ({avg_price:.2f})."

    latest_date = market_view.session_dates[-1] if market_view.session_dates else None

    return StrategyEvaluation(
        strategy_name="custom_momentum_filter",
        parameters=dict(parameters),
        decision_time=decision_time,
        targets=(
            StrategyTarget(
                security_id=market_view.security_id,
                weight=weight,
                decision_time=decision_time,
                rationale=rationale,
                indicator_state=state,
            ),
        ),
        latest_session_date=latest_date,
    )
