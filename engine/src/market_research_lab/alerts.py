"""Evaluate enabled Strategies and persist local Signals without order execution.

This module owns the Signal domain type and the refresh flow that turns an
enabled, validated Strategy revision into a traceable Signal. It never connects
to a broker and never produces an order (CORE-009, ALT-005).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from .json_types import JsonValue
from .market_data import InadequateTemporalProvenanceError
from .projects import RevisionNotFoundError, RevisionNotImmutableError
from .strategies import (
    MarketView,
    StrategyEvaluationError,
    StrategyParameterValidationError,
    evaluate_strategy,
    get_strategy_spec,
)

if TYPE_CHECKING:
    from .market_data import DailyBar, MarketDataStore
    from .projects import ProjectStore


class InvalidStrategyDefinitionError(ValueError):
    """Raised when a Strategy revision definition cannot be enabled."""


_REFRESH_ERRORS = (
    InvalidStrategyDefinitionError,
    StrategyEvaluationError,
    StrategyParameterValidationError,
    InadequateTemporalProvenanceError,
    RevisionNotFoundError,
    RevisionNotImmutableError,
    ValueError,
)


@dataclass(frozen=True)
class Signal:
    """A time-stamped Strategy output identifying an intended action, never an order."""

    signal_id: str
    strategy_name: str
    strategy_revision: str
    security_id: str
    action: str
    weight: float
    decision_time: str
    data_time: str
    dataset_version_id: str
    rationale: str
    indicator_state: str | None = None
    created_at: str = ""

    def to_json(self) -> dict[str, JsonValue]:
        return asdict(self)


@dataclass(frozen=True)
class SignalRefreshFailure:
    """A failed Strategy refresh whose error is preserved without a partial Signal."""

    strategy_revision: str
    error: str


@dataclass(frozen=True)
class SignalRefreshResult:
    """Outcome of one refresh pass: successful Signals plus preserved failures."""

    signals: tuple[Signal, ...]
    failures: tuple[SignalRefreshFailure, ...]


def validate_strategy_definition(definition: dict[str, JsonValue]) -> None:
    """Reject a Strategy definition that is not a validated, enableable revision."""
    if not isinstance(definition, dict):
        raise InvalidStrategyDefinitionError("The Strategy definition must be an object.")
    strategy_name = definition.get("strategy")
    if not isinstance(strategy_name, str) or not strategy_name.strip():
        raise InvalidStrategyDefinitionError(
            "The Strategy definition is missing its 'strategy' name."
        )
    symbol = definition.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise InvalidStrategyDefinitionError(
            "The Strategy definition is missing its target 'symbol'."
        )
    dataset_version_id = definition.get("dataset_version_id")
    if not isinstance(dataset_version_id, str) or not dataset_version_id.strip():
        raise InvalidStrategyDefinitionError(
            "The Strategy definition is missing its 'dataset_version_id'."
        )
    try:
        get_strategy_spec(strategy_name)
    except StrategyEvaluationError as error:
        raise InvalidStrategyDefinitionError(str(error)) from error


def _price_for_field(bar: DailyBar, price_field: str) -> float:
    if price_field == "open":
        return bar.open
    if price_field == "high":
        return bar.high
    if price_field == "low":
        return bar.low
    return bar.close


def _action_for_weight(weight: float) -> str:
    return "long" if weight > 0 else "flat"


def evaluate_signal(
    strategy_name: str,
    market_view: MarketView,
    parameters: dict[str, JsonValue],
    *,
    strategy_revision: str,
    dataset_version_id: str,
    decision_time: str,
    data_time: str,
) -> Signal:
    """Evaluate a Strategy at one decision time and build a traceable Signal."""
    evaluation = evaluate_strategy(
        strategy_name,
        market_view,
        parameters,
        decision_time=decision_time,
    )
    if not evaluation.targets:
        raise StrategyEvaluationError(
            f"Strategy '{strategy_name}' produced no target at decision time {decision_time}."
        )
    target = evaluation.targets[0]
    return Signal(
        signal_id=uuid4().hex,
        strategy_name=strategy_name,
        strategy_revision=strategy_revision,
        security_id=target.security_id,
        action=_action_for_weight(target.weight),
        weight=target.weight,
        decision_time=decision_time,
        data_time=data_time,
        dataset_version_id=dataset_version_id,
        rationale=target.rationale,
        indicator_state=target.indicator_state,
        created_at=datetime.now(UTC).isoformat(),
    )


def refresh_enabled_strategies(
    store: ProjectStore,
    market_store: MarketDataStore,
    project_id: str,
    *,
    decision_time: str | None = None,
) -> SignalRefreshResult:
    """Refresh and evaluate every enabled Strategy, preserving failures (CORE-008)."""
    resolved_decision_time = decision_time or datetime.now(UTC).isoformat()
    signals: list[Signal] = []
    failures: list[SignalRefreshFailure] = []

    for enabled in store.list_enabled_strategies(project_id):
        name = str(enabled["name"])
        revision = str(enabled["revision"])
        strategy_revision = f"{name}:{revision}"
        try:
            wrapped = store.read_revision(
                project_id, kind="strategy", name=name, revision=revision
            )
            definition = wrapped.get("definition")
            if not isinstance(definition, dict):
                raise InvalidStrategyDefinitionError(
                    f"Strategy revision '{strategy_revision}' has no definition."
                )
            validate_strategy_definition(definition)
            strategy_name = str(definition["strategy"])
            symbol = str(definition["symbol"])
            dataset_version_id = str(definition["dataset_version_id"])
            price_field = str(definition.get("price_field", "close"))
            parameters = (
                dict(definition["parameters"])
                if isinstance(definition.get("parameters"), dict)
                else {}
            )

            bars = market_store.history(
                dataset_version_id,
                symbol=symbol,
                as_of=resolved_decision_time,
            )
            if not bars:
                raise StrategyEvaluationError(
                    f"No eligible price history for '{symbol}' in "
                    f"dataset '{dataset_version_id}'."
                )

            sorted_bars = sorted(bars, key=lambda bar: bar.session_date)
            latest_bar = sorted_bars[-1]
            data_time = latest_bar.available_at or latest_bar.session_date
            market_view = MarketView(
                security_id=symbol,
                session_dates=tuple(bar.session_date for bar in sorted_bars),
                prices=tuple(_price_for_field(bar, price_field) for bar in sorted_bars),
            )

            signal = evaluate_signal(
                strategy_name,
                market_view,
                parameters,
                strategy_revision=strategy_revision,
                dataset_version_id=dataset_version_id,
                decision_time=resolved_decision_time,
                data_time=data_time,
            )
            store.save_signal(project_id, signal.to_json())
            signals.append(signal)
        except _REFRESH_ERRORS as error:
            failures.append(
                SignalRefreshFailure(strategy_revision=strategy_revision, error=str(error))
            )

    signals.sort(key=lambda signal: signal.decision_time, reverse=True)
    return SignalRefreshResult(signals=tuple(signals), failures=tuple(failures))
