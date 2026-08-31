"""Dynamic auto-discovery and loading for custom Python trading strategies."""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .json_types import JsonValue
    from .strategies import MarketView, StrategyEvaluation, StrategyMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredStrategy:
    metadata: StrategyMetadata
    evaluator: Callable[..., StrategyEvaluation]

CUSTOM_STRATEGY_TEMPLATE = '''"""Example custom strategy for Market Research Lab."""

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
'''


def get_custom_strategies_directories() -> list[Path]:
    """Return candidates for custom strategy directories."""
    repo_root = Path(__file__).resolve().parents[3]
    dirs = [
        repo_root / "engine" / "src" / "market_research_lab" / "custom_strategies",
        repo_root / "workspace" / "custom_strategies",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def ensure_sample_strategy() -> None:
    """Ensure at least one sample custom strategy file exists for guidance."""
    custom_dirs = get_custom_strategies_directories()
    sample_file = custom_dirs[0] / "custom_momentum.py"
    if not sample_file.exists():
        sample_file.write_text(CUSTOM_STRATEGY_TEMPLATE, encoding="utf-8")


def discover_custom_strategies() -> dict[str, DiscoveredStrategy]:
    """Scan custom strategy folders and load valid strategy modules."""
    ensure_sample_strategy()
    discovered: dict[str, DiscoveredStrategy] = {}

    for directory in get_custom_strategies_directories():
        if not directory.is_dir():
            continue
        for py_file in directory.glob("*.py"):
            if py_file.name.startswith((".", "_")):
                continue
            module_name = f"custom_strategy_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                strategy_spec = getattr(module, "SPEC", None)
                eval_func = getattr(module, "evaluate", None)

                if strategy_spec is not None and callable(eval_func):
                    def make_runner(fn: Callable[..., StrategyEvaluation]) -> Callable[..., StrategyEvaluation]:
                        def runner(
                            market_view: MarketView,
                            parameters: dict[str, JsonValue],
                            *,
                            decision_time: str,
                        ) -> StrategyEvaluation:
                            return fn(market_view, parameters, decision_time=decision_time)

                        return runner

                    discovered[strategy_spec.name] = DiscoveredStrategy(
                        metadata=strategy_spec,
                        evaluator=make_runner(eval_func),
                    )
            except Exception:
                logger.exception("Failed to load custom strategy from %s", py_file)

    return discovered
