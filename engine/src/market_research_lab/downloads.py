"""Provider download orchestration and Dataset Version persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .market_data import DatasetVersion, IngestionRequest, MarketDataStore
from .providers import (
    JsonFetcher,
    ProviderCredentials,
    ProviderDownloadError,
    download_sec_edgar,
    download_tiingo,
)


def download_provider(
    store: MarketDataStore,
    *,
    provider: str,
    symbols: list[str] | tuple[str, ...] = (),
    ciks: list[str] | tuple[str, ...] = (),
    start_date: str | None = None,
    end_date: str | None = None,
    retrieval_time: str | None = None,
    credentials: ProviderCredentials,
    fetch_json: JsonFetcher | None = None,
) -> list[DatasetVersion]:
    """Fetch all requested provider data before creating any Dataset Version."""
    retrieved_at = retrieval_time or datetime.now(UTC).isoformat()
    fetch_kwargs = {"fetch_json": fetch_json} if fetch_json is not None else {}

    if provider == "tiingo":
        downloaded = download_tiingo(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            retrieval_time=retrieved_at,
            token=credentials.tiingo_api_token,
            **fetch_kwargs,
        )
        record_groups = [downloaded.daily_bars, downloaded.corporate_actions]
        source = "tiingo"
    elif provider == "sec_edgar":
        downloaded = download_sec_edgar(
            ciks=ciks,
            retrieval_time=retrieved_at,
            user_agent=credentials.sec_edgar_user_agent,
            start_date=start_date,
            end_date=end_date,
            **fetch_kwargs,
        )
        record_groups = [downloaded.fundamental_facts]
        source = "sec_edgar"
    else:
        raise ProviderDownloadError(f"Unsupported data provider '{provider}'.")

    versions: list[DatasetVersion] = []
    try:
        for rows in record_groups:
            if rows:
                versions.append(
                    store.ingest_records(
                        IngestionRequest(
                            source=source,
                            file_path=Path(),
                            retrieval_time=retrieved_at,
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
            f"{provider} data could not be persisted as a Dataset Version: {error}"
        ) from error

    if not versions:
        raise ProviderDownloadError(f"{provider} returned no records.")
    return versions
