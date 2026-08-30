"""FastAPI router for dataset version and project run cleanup."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi import Path as FastAPIPath
from pydantic import BaseModel

from ..market_data import MarketDataStore
from ..projects import ProjectStore
from .deps import DatasetVersionInUseError, get_market_store, get_project_store

router = APIRouter()


class BulkDeleteDatasetsRequest(BaseModel):
    dataset_version_ids: list[str]
    force: bool = True


class BulkDeleteDatasetsResponse(BaseModel):
    deleted_ids: list[str]


class BulkDeleteRunsRequest(BaseModel):
    run_ids: list[str]


class BulkDeleteRunsResponse(BaseModel):
    deleted_ids: list[str]


@router.delete(
    "/api/datasets/{dataset_version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["datasets"],
)
def delete_dataset(
    dataset_version_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    *,
    force: bool = Query(default=False),
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> Response:
    market_store.coverage(dataset_version_id)
    if not force:
        references = store.find_runs_referencing_dataset(dataset_version_id)
        if references:
            raise DatasetVersionInUseError(dataset_version_id, references)
    market_store.delete_dataset_version(dataset_version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/datasets/bulk-delete",
    response_model=BulkDeleteDatasetsResponse,
    tags=["datasets"],
)
def bulk_delete_datasets(
    request: BulkDeleteDatasetsRequest,
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> BulkDeleteDatasetsResponse:
    target_ids = request.dataset_version_ids
    if not request.force:
        valid_ids: list[str] = []
        for version_id in target_ids:
            if not store.find_runs_referencing_dataset(version_id):
                valid_ids.append(version_id)
        target_ids = valid_ids
    deleted = market_store.bulk_delete_dataset_versions(target_ids)
    return BulkDeleteDatasetsResponse(deleted_ids=deleted)


@router.delete(
    "/api/projects/{project_id}/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["runs"],
)
def delete_project_run(
    project_id: UUID,
    run_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    store: ProjectStore = Depends(get_project_store),
) -> Response:
    store.delete_run(str(project_id), run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/projects/{project_id}/runs/bulk-delete",
    response_model=BulkDeleteRunsResponse,
    tags=["runs"],
)
def bulk_delete_project_runs(
    project_id: UUID,
    request: BulkDeleteRunsRequest,
    store: ProjectStore = Depends(get_project_store),
) -> BulkDeleteRunsResponse:
    deleted = store.bulk_delete_runs(str(project_id), request.run_ids)
    return BulkDeleteRunsResponse(deleted_ids=deleted)
