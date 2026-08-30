"""FastAPI router for alerts and signal refresh."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..alerts import (
    DataFreshnessState,
    SignalRefreshResult,
    data_freshness_state,
    refresh_enabled_strategies,
)
from ..json_types import JsonValue
from ..market_data import MarketDataStore
from ..projects import ProjectStore
from .deps import get_market_store, get_project_store

router = APIRouter()


class SignalResponse(BaseModel):
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
    data_state: DataFreshnessState = "stale-data"


def signal_response(signal: dict[str, JsonValue]) -> SignalResponse:
    """Build one Signal response with freshness classified at read time (ALT-004)."""
    body = dict(signal)
    body["data_state"] = data_freshness_state(str(body.get("data_time", "")), now=datetime.now(UTC))
    return SignalResponse.model_validate(body)


class SignalRefreshFailureResponse(BaseModel):
    strategy_revision: str
    error: str


class SignalRefreshResponse(BaseModel):
    signals: list[SignalResponse] = Field(default_factory=list)
    failures: list[SignalRefreshFailureResponse] = Field(default_factory=list)


@router.get(
    "/api/projects/{project_id}/alerts",
    response_model=list[SignalResponse],
    tags=["alerts"],
)
def list_project_signals(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[SignalResponse]:
    return [signal_response(signal) for signal in store.list_signals(str(project_id))]


@router.post(
    "/api/projects/{project_id}/alerts/refresh",
    response_model=SignalRefreshResponse,
    tags=["alerts"],
)
def refresh_project_alerts(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> SignalRefreshResponse:
    result: SignalRefreshResult = refresh_enabled_strategies(
        store, market_store, str(project_id)
    )
    return SignalRefreshResponse(
        signals=[signal_response(s.to_json()) for s in result.signals],
        failures=[
            SignalRefreshFailureResponse(
                strategy_revision=failure.strategy_revision, error=failure.error
            )
            for failure in result.failures
        ],
    )
