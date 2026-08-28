"""Validated HTTP route for local provider downloads."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from .downloads import download_provider
from .market_data import MarketDataStore
from .providers import (
    AlpacaDownloadSpec,
    JsonFetcher,
    ProviderCredentials,
    ProviderDownloadError,
    SecEdgarDownloadSpec,
    TiingoDownloadSpec,
)


class ProviderDownloadRequestBase(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "ProviderDownloadRequestBase":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        return self


class TiingoDownloadRequest(ProviderDownloadRequestBase):
    provider: Literal["tiingo"]
    symbols: list[str] = Field(min_length=1, max_length=500)

    @field_validator("symbols")
    @classmethod
    def normalise_symbols(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        if not cleaned:
            raise ValueError("At least one Tiingo symbol is required.")
        return cleaned

    def to_spec(self) -> TiingoDownloadSpec:
        return TiingoDownloadSpec(
            symbols=tuple(self.symbols),
            start_date=self.start_date,
            end_date=self.end_date,
        )


class AlpacaDownloadRequest(ProviderDownloadRequestBase):
    provider: Literal["alpaca"]
    symbol: str = Field(min_length=1, max_length=16)
    start_date: date
    end_date: date

    @field_validator("symbol")
    @classmethod
    def normalise_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("An Alpaca symbol is required.")
        return cleaned

    def to_spec(self) -> AlpacaDownloadSpec:
        return AlpacaDownloadSpec(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
        )


class SecEdgarDownloadRequest(ProviderDownloadRequestBase):
    provider: Literal["sec_edgar"]
    ciks: list[str] = Field(min_length=1, max_length=500)

    @field_validator("ciks")
    @classmethod
    def normalise_ciks(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw_cik in values:
            cik = raw_cik.strip()
            if not cik:
                continue
            if not cik.isdigit() or len(cik) > 10:
                raise ValueError("SEC EDGAR CIKs must contain up to 10 digits.")
            cleaned.append(cik.zfill(10))
        cleaned = list(dict.fromkeys(cleaned))
        if not cleaned:
            raise ValueError("At least one SEC EDGAR CIK is required.")
        return cleaned

    def to_spec(self) -> SecEdgarDownloadSpec:
        return SecEdgarDownloadSpec(
            ciks=tuple(self.ciks),
            start_date=self.start_date,
            end_date=self.end_date,
        )


ProviderDownloadRequest = Annotated[
    TiingoDownloadRequest | SecEdgarDownloadRequest | AlpacaDownloadRequest,
    Field(discriminator="provider"),
]


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
                request.to_spec(),
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
