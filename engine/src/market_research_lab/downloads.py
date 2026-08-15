"""Provider download orchestration and Dataset Version persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .market_data import DatasetVersion, IngestionRequest, MarketDataStore
from .providers import (
    JsonFetcher,
    ProviderCredentials,
    ProviderDownloadError,
    SecEdgarDownloadSpec,
    TiingoDownloadSpec,
    download_sec_edgar,
    download_tiingo,
)


def download_provider(
    store: MarketDataStore,
    request: TiingoDownloadSpec | SecEdgarDownloadSpec,
    *,
    credentials: ProviderCredentials,
    fetch_json: JsonFetcher | None = None,
) -> list[DatasetVersion]:
    """Fetch validated provider data before creating any Dataset Version."""
    retrieved_at = datetime.now(UTC).isoformat()

    if request.provider == "tiingo":
        downloaded = download_tiingo(
            request,
            token=credentials.tiingo_api_token,
            retrieval_time=retrieved_at,
            fetch_json=fetch_json,
        )
        record_groups = [downloaded.daily_bars, downloaded.corporate_actions]
        source = "tiingo"
    else:
        downloaded = download_sec_edgar(
            request,
            user_agent=credentials.sec_edgar_user_agent,
            retrieval_time=retrieved_at,
            fetch_json=fetch_json,
        )
        record_groups = [downloaded.fundamental_facts]
        source = "sec_edgar"

    versions: list[DatasetVersion] = []
    try:
        for rows in record_groups:
            if rows:
                versions.append(
                    store.ingest_records(
                        IngestionRequest(
                            source=source, file_path=Path(), retrieval_time=retrieved_at
                        ),
                        rows,
                        warnings=downloaded.warnings,
                    )
                )
        store.upsert_securities(downloaded.securities, source=source, retrieval_time=retrieved_at)
    except Exception as error:
        for version in versions:
            store.discard_dataset_version(version)
        raise ProviderDownloadError(
            f"{request.provider} data could not be persisted as a Dataset Version: {error}"
        ) from error

    if not versions:
        raise ProviderDownloadError(f"{request.provider} returned no records.")
    return versions
