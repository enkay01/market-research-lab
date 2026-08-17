"""Domain tests for Signal evaluation and the enabled-Strategy refresh flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_research_lab.alerts import (
    InvalidStrategyDefinitionError,
    evaluate_signal,
    refresh_enabled_strategies,
    validate_strategy_definition,
)
from market_research_lab.json_types import JsonValue
from market_research_lab.market_data import IngestionRequest, MarketDataStore
from market_research_lab.projects import (
    ProjectStore,
    RevisionNotFoundError,
    RevisionNotImmutableError,
)
from market_research_lab.strategies import MarketView

STRATEGY_NAME = "long_flat_moving_average"


def _bullish_bars() -> list[dict[str, JsonValue]]:
    return [
        {
            "symbol": "AAPL",
            "session_date": "2024-01-02",
            "open": 100,
            "high": 105,
            "low": 99,
            "close": 102,
            "volume": 1000,
            "available_at": "2024-01-02T20:00:00Z",
        },
        {
            "symbol": "AAPL",
            "session_date": "2024-01-03",
            "open": 102,
            "high": 108,
            "low": 101,
            "close": 106,
            "volume": 1200,
            "available_at": "2024-01-03T20:00:00Z",
        },
        {
            "symbol": "AAPL",
            "session_date": "2024-01-04",
            "open": 106,
            "high": 110,
            "low": 105,
            "close": 108,
            "volume": 1100,
            "available_at": "2024-01-04T20:00:00Z",
        },
        {
            "symbol": "AAPL",
            "session_date": "2024-01-05",
            "open": 108,
            "high": 112,
            "low": 107,
            "close": 110,
            "volume": 1300,
            "available_at": "2024-01-05T20:00:00Z",
        },
        {
            "symbol": "AAPL",
            "session_date": "2024-01-08",
            "open": 110,
            "high": 114,
            "low": 109,
            "close": 112,
            "volume": 1500,
            "available_at": "2024-01-08T20:00:00Z",
        },
        {
            "symbol": "AAPL",
            "session_date": "2024-01-09",
            "open": 112,
            "high": 116,
            "low": 111,
            "close": 114,
            "volume": 1400,
            "available_at": "2024-01-09T20:00:00Z",
        },
        {
            "symbol": "AAPL",
            "session_date": "2024-01-10",
            "open": 114,
            "high": 118,
            "low": 113,
            "close": 116,
            "volume": 1600,
            "available_at": "2024-01-10T20:00:00Z",
        },
    ]


def _ingest(store: MarketDataStore, rows: list[dict[str, JsonValue]]) -> str:
    version = store.ingest_records(
        IngestionRequest(source="test", retrieval_time="2024-01-10T20:00:00Z"),
        rows,
    )
    return version.id


def _save_and_enable(store: ProjectStore, project_id: str, dataset_version_id: str) -> None:
    definition = {
        "strategy": STRATEGY_NAME,
        "symbol": "AAPL",
        "dataset_version_id": dataset_version_id,
        "price_field": "close",
        "parameters": {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
    }
    store.save_revision(
        project_id,
        kind="strategy",
        name=f"{STRATEGY_NAME} - AAPL",
        definition=definition,
    )
    store.enable_strategy(project_id, name=f"{STRATEGY_NAME} - AAPL", revision="v1")


def test_validate_strategy_definition_accepts_valid_and_rejects_missing_fields() -> None:
    valid = {
        "strategy": STRATEGY_NAME,
        "symbol": "AAPL",
        "dataset_version_id": "ds-1",
    }
    validate_strategy_definition(valid)

    with pytest.raises(InvalidStrategyDefinitionError, match="symbol"):
        validate_strategy_definition({"strategy": STRATEGY_NAME, "dataset_version_id": "ds-1"})

    with pytest.raises(InvalidStrategyDefinitionError, match="dataset_version_id"):
        validate_strategy_definition({"strategy": STRATEGY_NAME, "symbol": "AAPL"})

    with pytest.raises(InvalidStrategyDefinitionError, match="Unknown Strategy"):
        validate_strategy_definition(
            {"strategy": "mystery", "symbol": "AAPL", "dataset_version_id": "ds-1"}
        )


def test_evaluate_signal_builds_action_data_time_and_rationale() -> None:
    view = MarketView(
        security_id="AAPL",
        session_dates=(
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-08",
            "2024-01-09",
            "2024-01-10",
        ),
        prices=(100.0, 102.0, 106.0, 108.0, 110.0, 114.0, 116.0),
    )
    signal = evaluate_signal(
        STRATEGY_NAME,
        view,
        {"fast_period": 2, "slow_period": 4, "ma_type": "sma"},
        strategy_revision=f"{STRATEGY_NAME}:v1",
        dataset_version_id="ds-1",
        decision_time="2024-01-10T21:00:00Z",
        data_time="2024-01-10T20:00:00Z",
    )

    assert signal.strategy_revision == f"{STRATEGY_NAME}:v1"
    assert signal.security_id == "AAPL"
    assert signal.action == "long"
    assert signal.weight == 1.0
    assert signal.decision_time == "2024-01-10T21:00:00Z"
    assert signal.data_time == "2024-01-10T20:00:00Z"
    assert "long" in signal.rationale
    assert signal.signal_id


def test_only_immutable_revisions_can_be_enabled(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Signals")
    name = f"{STRATEGY_NAME} - AAPL"

    with pytest.raises(RevisionNotImmutableError):
        store.enable_strategy(project.id, name=name, revision="draft")

    with pytest.raises(RevisionNotFoundError):
        store.enable_strategy(project.id, name=name, revision="v9")

    with pytest.raises(RevisionNotImmutableError):
        store.read_revision(project.id, kind="strategy", name=name, revision="draft")


def test_refresh_produces_a_persisted_signal_with_provenance(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    market_store = MarketDataStore(tmp_path)
    project = store.create_project("Signals")

    dataset_version_id = _ingest(market_store, _bullish_bars())
    _save_and_enable(store, project.id, dataset_version_id)

    result = refresh_enabled_strategies(
        store, market_store, project.id, decision_time="2024-01-10T21:00:00Z"
    )

    assert result.failures == ()
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.security_id == "AAPL"
    assert signal.action == "long"
    assert signal.weight == 1.0
    assert signal.strategy_revision == f"{STRATEGY_NAME} - AAPL:v1"
    assert signal.decision_time == "2024-01-10T21:00:00Z"
    assert signal.data_time == "2024-01-10T20:00:00Z"
    assert signal.rationale
    assert signal.dataset_version_id == dataset_version_id

    persisted = store.list_signals(project.id)
    assert len(persisted) == 1
    assert persisted[0]["signal_id"] == signal.signal_id
    assert persisted[0]["action"] == "long"


def test_refresh_preserves_validation_failure_without_partial_signal(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    market_store = MarketDataStore(tmp_path)
    project = store.create_project("Signals")

    # Bars without available_at lack point-in-time provenance.
    no_provenance = [
        {key: value for key, value in row.items() if key != "available_at"}
        for row in _bullish_bars()
    ]
    dataset_version_id = _ingest(market_store, no_provenance)
    _save_and_enable(store, project.id, dataset_version_id)

    result = refresh_enabled_strategies(
        store, market_store, project.id, decision_time="2024-01-10T21:00:00Z"
    )

    assert result.signals == ()
    assert len(result.failures) == 1
    assert result.failures[0].strategy_revision == f"{STRATEGY_NAME} - AAPL:v1"
    assert "available_at" in result.failures[0].error
    assert store.list_signals(project.id) == []


def test_refresh_with_no_enabled_strategies_is_empty(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    market_store = MarketDataStore(tmp_path)
    project = store.create_project("Signals")

    result = refresh_enabled_strategies(store, market_store, project.id)

    assert result.signals == ()
    assert result.failures == ()
