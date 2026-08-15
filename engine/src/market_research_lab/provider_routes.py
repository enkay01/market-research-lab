"""Validated HTTP route for local provider downloads."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from .downloads import ProviderDownloadOptions, download_provider
from .market_data import MarketDataStore
from .providers import JsonFetcher, ProviderCredentials, ProviderDownloadError


class ProviderDownloadRequest(BaseModel):
    provider: Literal["tiingo", "sec_edgar"]
    symbols: list[str] = Field(default_factory=list, max_length=500)
    ciks: list[str] = Field(default_factory=list, max_length=500)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("symbols", "ciks")
    @classmethod
    def normalise_identifiers(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if len(cleaned) > 500:
            raise ValueError("A provider download accepts at most 500 identifiers.")
        return cleaned

    @model_validator(mode="after")
    def validate_provider_inputs(self) -> ProviderDownloadRequest:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        if self.provider == "tiingo" and not self.symbols:
            raise ValueError("At least one Tiingo symbol is required.")
        if self.provider == "sec_edgar" and not self.ciks:
            raise ValueError("At least one SEC EDGAR CIK is required.")
        return self


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
                ProviderDownloadOptions(
                    provider=request.provider,
                    symbols=request.symbols,
                    ciks=request.ciks,
                    start_date=request.start_date.isoformat() if request.start_date else None,
                    end_date=request.end_date.isoformat() if request.end_date else None,
                    credentials=credentials,
                    fetch_json=provider_fetch_json,
                ),
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
