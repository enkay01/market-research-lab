"""FastAPI router for dataset version and project run cleanup."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi import Path as FastAPIPath

from ..market_data import MarketDataStore
from ..projects import ProjectStore
from .deps import DatasetVersionInUseError, get_market_store, get_project_store

router = APIRouter()


@router.delete(
    "/api/datasets/{dataset_version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["datasets"],
)
def delete_dataset(
    dataset_version_id: str = FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,128}$"),
    store: ProjectStore = Depends(get_project_store),
    market_store: MarketDataStore = Depends(get_market_store),
) -> Response:
    market_store.coverage(dataset_version_id)
    references = store.find_runs_referencing_dataset(dataset_version_id)
    if references:
        raise DatasetVersionInUseError(dataset_version_id, references)
    market_store.delete_dataset_version(dataset_version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
