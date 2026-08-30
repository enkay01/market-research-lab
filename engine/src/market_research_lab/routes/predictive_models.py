"""FastAPI router for predictive models."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi import (
    Path as FastAPIPath,
)
from pydantic import BaseModel, Field

from ..json_types import JsonValue
from ..market_data import InadequateTemporalProvenanceError, MarketDataStore
from ..predictive_models import (
    FittedModelArtifact,
    PredictiveModelCalculation,
    PredictiveModelDataError,
    PredictiveModelFold,
    PredictiveModelForecast,
    PredictiveModelMetadata,
    PredictiveModelOutput,
    PredictiveModelParameter,
    get_predictive_model_spec,
    list_predictive_models,
    run_predictive_model,
)
from ..projects import (
    FailedPredictiveModelRunRecord,
    PredictiveModelRunRecord,
    ProjectStore,
)
from .deps import (
    get_market_store,
    get_project_store,
    log_run_event,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class PredictiveModelParameterResponse(BaseModel):
    name: str
    param_type: str
    default: JsonValue
    description: str
    min_value: float | None = None
    max_value: float | None = None
    options: list[str] | None = None


class PredictiveModelMetadataResponse(BaseModel):
    name: str
    display_name: str
    description: str
    target: str
    horizon: int
    features: list[str]
    training_window: int
    parameters: list[PredictiveModelParameterResponse]
    output_meaning: str
    outputs: list[str]


class PredictiveModelRunRequest(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_]{1,64}$")
    dataset_version_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1, max_length=32)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    seed: int | None = Field(default=None, ge=0)
    as_of: datetime | None = None


class PredictiveModelArtifactResponse(BaseModel):
    model_name: str
    feature_name: str
    target_name: str
    horizon: int
    intercept: float
    coefficient: float
    training_start: str
    training_end: str
    training_observations: int
    parameters: dict[str, JsonValue]
    seed: int | None
    training_metrics: dict[str, float]
    feature_definition: dict[str, JsonValue] = Field(default_factory=dict)
    preprocessing: dict[str, JsonValue] = Field(default_factory=dict)


class PredictiveModelSplitResponse(BaseModel):
    period: Literal["training", "validation", "test"]
    start: str
    end: str
    feature_start: str
    feature_end: str
    observations: int
    labelled_observations: int
    fit_scope: str


class PredictiveModelPeriodMetricsResponse(BaseModel):
    period: Literal["training", "validation", "test"]
    observations: int
    metrics: dict[str, float]
    benchmark_metrics: dict[str, float] = Field(default_factory=dict)
    comparison: dict[str, JsonValue] = Field(default_factory=dict)
    sample_scope: Literal["in_sample", "validation", "out_of_sample"]


class NaiveBenchmarkEvaluationResponse(BaseModel):
    name: str
    display_name: str
    description: str
    period_metrics: dict[str, dict[str, float]]
    out_of_sample_comparison: dict[str, JsonValue]
    completed: bool = False


class PredictiveModelPredictionResponse(BaseModel):
    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: float
    target_date: str | None = None
    period: Literal["training", "validation", "test"] | None = None


class PredictiveModelForecastResponse(BaseModel):
    session_date: str
    feature_value: float
    predicted_value: float
    actual_target: None = None
    target_date: None = None
    period: None = None


class PredictiveModelFoldResponse(BaseModel):
    fold_index: int
    period: Literal["validation", "test"]
    prediction_session_date: str
    target_date: str | None
    training_start: str
    training_end: str
    training_observations: int
    fit_scope: str
    artifact: PredictiveModelArtifactResponse
    prediction: PredictiveModelPredictionResponse | PredictiveModelForecastResponse
    metrics: dict[str, float]


class PredictiveModelRunResponse(BaseModel):
    run_id: str | None = None
    model_revision: str | None = None
    status: Literal["preview", "completed"] = "preview"
    model_name: str
    display_name: str
    description: str
    symbol: str
    dataset_version_id: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    seed: int | None
    target: str
    horizon: int
    features: list[str]
    training_window: int
    output_meaning: str
    outputs: list[str]
    artifact: PredictiveModelArtifactResponse
    predictions: list[PredictiveModelPredictionResponse | PredictiveModelForecastResponse]
    metrics: dict[str, float]
    training_start: str
    training_end: str
    completed_at: str | None = None
    as_of: datetime | None = None
    out_of_sample_status: str
    evaluation_mode: Literal["holdout", "expanding", "rolling"] = "holdout"
    splits: list[PredictiveModelSplitResponse] = Field(default_factory=list)
    period_metrics: list[PredictiveModelPeriodMetricsResponse] = Field(default_factory=list)
    fold_artifacts: list[PredictiveModelArtifactResponse] = Field(default_factory=list)
    folds: list[PredictiveModelFoldResponse] = Field(default_factory=list)
    benchmark: NaiveBenchmarkEvaluationResponse | None = None
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    is_eligible_for_strategy: bool = False
    eligibility_reason: str = (
        "Predictive Model is not eligible for a Strategy until the naive benchmark "
        "comparison is complete."
    )


@dataclass(frozen=True)
class PredictiveModelResponseContext:
    """Run identity added when a calculation is previewed or persisted."""

    symbol: str
    dataset_version_id: str
    run_id: str = ""
    model_revision: str = ""
    status: Literal["preview", "completed"] = "preview"
    completed_at: str | None = None
    as_of: datetime | None = None


def _predictive_parameter_response(
    parameter: PredictiveModelParameter,
) -> PredictiveModelParameterResponse:
    return PredictiveModelParameterResponse(
        name=parameter.name,
        param_type=parameter.param_type,
        default=parameter.default,
        description=parameter.description,
        min_value=parameter.min_value,
        max_value=parameter.max_value,
        options=list(parameter.options) if parameter.options else None,
    )


def _predictive_metadata_response(
    metadata: PredictiveModelMetadata,
) -> PredictiveModelMetadataResponse:
    return PredictiveModelMetadataResponse(
        name=metadata.name,
        display_name=metadata.display_name,
        description=metadata.description,
        target=metadata.target,
        horizon=metadata.horizon,
        features=list(metadata.features),
        training_window=metadata.training_window,
        parameters=[_predictive_parameter_response(p) for p in metadata.parameters],
        output_meaning=metadata.output_meaning,
        outputs=list(metadata.outputs),
    )


def _predictive_artifact_response(
    artifact: FittedModelArtifact,
) -> PredictiveModelArtifactResponse:
    metrics = {
        name: float(value)
        for name, value in artifact.training_metrics.items()
        if isinstance(value, (int, float))
    }
    return PredictiveModelArtifactResponse(
        model_name=artifact.model_name,
        feature_name=artifact.feature_name,
        target_name=artifact.target_name,
        horizon=artifact.horizon,
        intercept=artifact.intercept,
        coefficient=artifact.coefficient,
        training_start=artifact.training_start,
        training_end=artifact.training_end,
        training_observations=artifact.training_observations,
        parameters=artifact.parameters,
        seed=artifact.seed,
        training_metrics=metrics,
        feature_definition=artifact.feature_definition,
        preprocessing=artifact.preprocessing,
    )


def _predictive_prediction_response(
    prediction: PredictiveModelOutput,
) -> PredictiveModelPredictionResponse | PredictiveModelForecastResponse:
    if isinstance(prediction, PredictiveModelForecast):
        return PredictiveModelForecastResponse(
            session_date=prediction.session_date,
            feature_value=prediction.feature_value,
            predicted_value=prediction.predicted_value,
            actual_target=prediction.actual_target,
            target_date=prediction.target_date,
            period=prediction.period,
        )
    return PredictiveModelPredictionResponse(
        session_date=prediction.session_date,
        feature_value=prediction.feature_value,
        predicted_value=prediction.predicted_value,
        actual_target=prediction.actual_target,
        target_date=prediction.target_date,
        period=prediction.period,
    )


def _predictive_fold_response(fold: PredictiveModelFold) -> PredictiveModelFoldResponse:
    return PredictiveModelFoldResponse(
        fold_index=fold.fold_index,
        period=fold.period,
        prediction_session_date=fold.prediction_session_date,
        target_date=fold.target_date,
        training_start=fold.training_start,
        training_end=fold.training_end,
        training_observations=fold.training_observations,
        fit_scope=fold.fit_scope,
        artifact=_predictive_artifact_response(fold.artifact),
        prediction=_predictive_prediction_response(fold.prediction),
        metrics=fold.metrics,
    )


def _predictive_run_response(
    calculation: PredictiveModelCalculation,
    context: PredictiveModelResponseContext,
) -> PredictiveModelRunResponse:
    metadata = calculation.metadata
    return PredictiveModelRunResponse(
        run_id=context.run_id or None,
        model_revision=context.model_revision or None,
        status=context.status,
        model_name=metadata.name,
        display_name=metadata.display_name,
        description=metadata.description,
        symbol=context.symbol,
        dataset_version_id=context.dataset_version_id,
        dataset_version_ids=[context.dataset_version_id],
        parameters=calculation.parameters,
        seed=calculation.seed,
        target=metadata.target,
        horizon=metadata.horizon,
        features=list(metadata.features),
        training_window=int(calculation.parameters["training_window"]),
        output_meaning=metadata.output_meaning,
        outputs=list(metadata.outputs),
        artifact=_predictive_artifact_response(calculation.artifact),
        predictions=[_predictive_prediction_response(p) for p in calculation.predictions],
        metrics=calculation.metrics,
        training_start=calculation.training_start,
        training_end=calculation.training_end,
        completed_at=context.completed_at,
        as_of=context.as_of,
        out_of_sample_status=calculation.out_of_sample_status,
        evaluation_mode=calculation.evaluation.mode,
        splits=[
            PredictiveModelSplitResponse(
                period=split.period,
                start=split.start,
                end=split.end,
                feature_start=split.feature_start,
                feature_end=split.feature_end,
                observations=split.observations,
                labelled_observations=split.labelled_observations,
                fit_scope=split.fit_scope,
            )
            for split in calculation.evaluation.splits
        ],
        period_metrics=[
            PredictiveModelPeriodMetricsResponse(
                period=period_metrics.period,
                observations=period_metrics.observations,
                metrics=period_metrics.metrics,
                benchmark_metrics=period_metrics.benchmark_metrics,
                comparison=period_metrics.comparison,
                sample_scope=period_metrics.sample_scope,
            )
            for period_metrics in calculation.evaluation.period_metrics
        ],
        fold_artifacts=[
            _predictive_artifact_response(fold_artifact)
            for fold_artifact in calculation.fold_artifacts
        ],
        folds=[_predictive_fold_response(fold) for fold in calculation.evaluation.folds],
        benchmark=(
            NaiveBenchmarkEvaluationResponse(
                name=calculation.evaluation.benchmark.name,
                display_name=calculation.evaluation.benchmark.display_name,
                description=calculation.evaluation.benchmark.description,
                period_metrics=calculation.evaluation.benchmark.period_metrics,
                out_of_sample_comparison=(
                    calculation.evaluation.benchmark.out_of_sample_comparison
                ),
                completed=calculation.evaluation.benchmark.completed,
            )
            if calculation.evaluation.benchmark
            else None
        ),
        assumptions=list(calculation.evaluation.assumptions),
        warnings=list(calculation.evaluation.warnings),
        limitations=list(calculation.evaluation.limitations),
        unsupported_claims=list(calculation.evaluation.unsupported_claims),
        is_eligible_for_strategy=calculation.evaluation.is_eligible_for_strategy,
        eligibility_reason=calculation.evaluation.eligibility_reason,
    )


def _normalize_predictive_model_result(
    result: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Fill period scope for legacy Runs without changing persisted artifacts."""
    raw_period_metrics = result.get("period_metrics")
    if not isinstance(raw_period_metrics, list):
        return result

    scopes = {
        "training": "in_sample",
        "validation": "validation",
        "test": "out_of_sample",
    }
    normalized = dict(result)
    normalized_period_metrics: list[JsonValue] = []
    for raw_metric in raw_period_metrics:
        if not isinstance(raw_metric, dict):
            normalized_period_metrics.append(raw_metric)
            continue
        metric = dict(raw_metric)
        if "sample_scope" not in metric:
            period = metric.get("period")
            scope = scopes.get(period) if isinstance(period, str) else None
            if scope is not None:
                metric["sample_scope"] = scope
        normalized_period_metrics.append(metric)
    normalized["period_metrics"] = normalized_period_metrics
    return normalized


def _predictive_model_calculation(
    market_store: MarketDataStore,
    request: PredictiveModelRunRequest,
) -> PredictiveModelCalculation:
    try:
        bars = market_store.history(
            request.dataset_version_id,
            symbol=request.symbol,
            as_of=request.as_of,
        )
    except InadequateTemporalProvenanceError:
        raise
    except ValueError as error:
        raise PredictiveModelDataError(str(error)) from error
    if not bars:
        raise PredictiveModelDataError(
            f"No price history found for symbol '{request.symbol}' "
            f"in dataset '{request.dataset_version_id}'."
        )
    return run_predictive_model(
        request.name,
        bars,
        request.parameters,
        request.seed,
    )


def _persist_failed_predictive_model_run(
    store: ProjectStore,
    project_id: UUID,
    request: PredictiveModelRunRequest,
    error: Exception,
) -> str:
    """Preserve a failed saved-model request before returning its original error."""
    return store.create_failed_predictive_model_run(
        str(project_id),
        FailedPredictiveModelRunRecord(
            model_revision=f"{request.name}:{request.symbol}:failed",
            dataset_version_ids=[request.dataset_version_id],
            parameters=dict(request.parameters),
            as_of=request.as_of.isoformat() if request.as_of else None,
            error_message=str(error),
        ),
    )


@router.get(
    "/api/predictive-models",
    response_model=list[PredictiveModelMetadataResponse],
    tags=["predictive-models"],
)
def get_predictive_models() -> list[PredictiveModelMetadataResponse]:
    return [_predictive_metadata_response(metadata) for metadata in list_predictive_models()]


@router.get(
    "/api/predictive-models/{name}",
    response_model=PredictiveModelMetadataResponse,
    tags=["predictive-models"],
)
def get_predictive_model_by_name(
    name: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_]{1,64}$"),
) -> PredictiveModelMetadataResponse:
    return _predictive_metadata_response(get_predictive_model_spec(name).metadata)


@router.post(
    "/api/predictive-models/run",
    response_model=PredictiveModelRunResponse,
    tags=["predictive-models"],
)
def run_predictive_model_preview(
    request: PredictiveModelRunRequest,
    market_store: MarketDataStore = Depends(get_market_store),
) -> PredictiveModelRunResponse:
    calculation = _predictive_model_calculation(market_store, request)
    return _predictive_run_response(
        calculation,
        PredictiveModelResponseContext(
            symbol=request.symbol,
            dataset_version_id=request.dataset_version_id,
            as_of=request.as_of,
        ),
    )


@router.post(
    "/api/projects/{project_id}/predictive-models/runs",
    response_model=PredictiveModelRunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["predictive-models"],
)
def save_predictive_model_run(
    project_id: UUID,
    request: PredictiveModelRunRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> PredictiveModelRunResponse:
    try:
        calculation = _predictive_model_calculation(market_store, request)
        definition = {
            "model": calculation.metadata.name,
            "target": calculation.metadata.target,
            "horizon": calculation.metadata.horizon,
            "features": list(calculation.metadata.features),
            "training_window": calculation.parameters["training_window"],
            "parameters": calculation.parameters,
            "output_meaning": calculation.metadata.output_meaning,
            "symbol": request.symbol,
            "dataset_version_id": request.dataset_version_id,
            "as_of": request.as_of.isoformat() if request.as_of else None,
            "seed": calculation.seed,
        }
        definition_name = f"{calculation.metadata.name} - {request.symbol}"
        revision = store.save_revision(
            str(project_id),
            kind="predictive_model",
            name=definition_name,
            definition=definition,
        )
        model_revision = f"{calculation.metadata.name}:{request.symbol}:{revision}"
    except Exception as error:
        try:
            run_id = _persist_failed_predictive_model_run(store, project_id, request, error)
            log_run_event(project_id, run_id, f"Predictive Model Run failed: {error}")
        except Exception as persist_error:
            error.add_note(f"Failed to persist the Predictive Model error: {persist_error}")
        raise

    completed_at = datetime.now(UTC).isoformat()
    base_response = _predictive_run_response(
        calculation,
        PredictiveModelResponseContext(
            symbol=request.symbol,
            dataset_version_id=request.dataset_version_id,
            model_revision=model_revision,
            status="completed",
            completed_at=completed_at,
            as_of=request.as_of,
        ),
    )
    run_id = store.create_predictive_model_result(
        str(project_id),
        PredictiveModelRunRecord(
            model_revision=model_revision,
            dataset_version_ids=[request.dataset_version_id],
            parameters=calculation.parameters,
            as_of=request.as_of.isoformat() if request.as_of else None,
            completed_at=completed_at,
            artifact=calculation.artifact.to_json(),
            predictions=[prediction.to_json() for prediction in calculation.predictions],
            result=base_response.model_dump(mode="json"),
            evaluation=calculation.evaluation.to_json(),
            fold_artifacts=[
                fold_artifact.to_json() for fold_artifact in calculation.fold_artifacts
            ],
            folds=[fold.to_json() for fold in calculation.evaluation.folds],
        ),
    )
    log_run_event(project_id, run_id, "Predictive Model Run completed.")
    return base_response.model_copy(update={"run_id": run_id})


@router.get(
    "/api/projects/{project_id}/predictive-models/runs",
    response_model=list[PredictiveModelRunResponse],
    tags=["predictive-models"],
)
def list_project_predictive_model_runs(
    project_id: UUID,
    store: ProjectStore = Depends(get_project_store),
) -> list[PredictiveModelRunResponse]:
    responses: list[PredictiveModelRunResponse] = []
    for item in store.list_predictive_model_results(str(project_id)):
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        normalized_result = _normalize_predictive_model_result(result)
        responses.append(
            PredictiveModelRunResponse.model_validate(
                {
                    **normalized_result,
                    "run_id": item.get("run_id"),
                    "model_revision": item.get("model_revision"),
                    "status": "completed",
                }
            )
        )
    return responses


@router.get(
    "/api/projects/{project_id}/predictive-models/runs/{run_id}",
    response_model=PredictiveModelRunResponse,
    tags=["predictive-models"],
)
def get_project_predictive_model_run(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    store: ProjectStore = Depends(get_project_store),
) -> PredictiveModelRunResponse:
    item = store.get_predictive_model_result(str(project_id), run_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Predictive Model Run not found.",
        )
    result = item.get("result")
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Predictive Model Run artifact is invalid.",
        )
    return PredictiveModelRunResponse.model_validate(
        {
            **_normalize_predictive_model_result(result),
            "run_id": item.get("run_id"),
            "model_revision": item.get("model_revision"),
            "status": "completed",
        }
    )


@router.get(
    "/api/projects/{project_id}/predictive-models/runs/{run_id}/export/{format_type}",
    tags=["predictive-models"],
    responses={
        200: {
            "content": {
                "text/html": {"schema": {"type": "string"}},
                "text/csv": {"schema": {"type": "string"}},
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "manifest": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            "predictive_model": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["manifest", "predictive_model"],
                    }
                },
            }
        }
    },
)
def export_predictive_model(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
    format_type: Literal["html", "csv", "json"] = FastAPIPath(),
    store: ProjectStore = Depends(get_project_store),
) -> Response:
    try:
        artifact = store.get_predictive_model_export(str(project_id), run_id, format_type)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )
