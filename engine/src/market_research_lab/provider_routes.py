"""Validated HTTP route for local provider downloads."""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .downloads import download_provider
from .market_data import MarketDataStore
from .providers import (
    JsonFetcher,
    ProviderCredentials,
    ProviderDownloadError,
    ProviderDownloadRequest,
)


class ProviderDownloadResponse(BaseModel):
    dataset_version_id: str
    dataset_version_ids: list[str]


def register_provider_download_route(
    app: FastAPI,
    *,
    market_store: MarketDataStore,
    credentials: ProviderCredentials,
    provider_fetch_json: JsonFetcher | None,
) -> None:
    @app.post(
        "/api/datasets/download",
        response_model=ProviderDownloadResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["datasets"],
    )
    def download_dataset(
        request: ProviderDownloadRequest,
    ) -> ProviderDownloadResponse | JSONResponse:
        try:
            versions = download_provider(
                market_store,
                request,
                credentials=credentials,
                fetch_json=provider_fetch_json,
            )
        except ProviderDownloadError as error:
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"code": "provider_error", "message": str(error), "details": {}},
            )
        except ValueError as error:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"code": "import_error", "message": str(error), "details": {}},
            )
        return ProviderDownloadResponse(
            dataset_version_id=versions[0].id,
            dataset_version_ids=[version.id for version in versions],
        )
