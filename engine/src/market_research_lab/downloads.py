"""Provider download orchestration and Dataset Version persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .market_data import DatasetVersion, IngestionRequest, MarketDataStore
from .providers import (
    JsonFetcher,
    ProviderCredentials,
    ProviderDownloadError,
    SecEdgarDownloadOptions,
    TiingoDownloadOptions,
    download_sec_edgar,
    download_tiingo,
)


@dataclass(frozen=True)
class ProviderDownloadOptions:
    provider: str
    credentials: ProviderCredentials
    symbols: list[str] | tuple[str, ...] = ()
    ciks: list[str] | tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    retrieval_time: str | None = None
    fetch_json: JsonFetcher | None = None


def download_provider(
    store: MarketDataStore,
    options: ProviderDownloadOptions,
) -> list[DatasetVersion]:
    """Fetch all requested provider data before creating any Dataset Version."""
    retrieved_at = options.retrieval_time or datetime.now(UTC).isoformat()

    if options.provider == "tiingo":
        downloaded = download_tiingo(
            TiingoDownloadOptions(
                symbols=options.symbols,
                start_date=options.start_date,
                end_date=options.end_date,
                retrieval_time=retrieved_at,
                token=options.credentials.tiingo_api_token,
                fetch_json=options.fetch_json,
            )
        )
        record_groups = [downloaded.daily_bars, downloaded.corporate_actions]
        source = "tiingo"
    elif options.provider == "sec_edgar":
        downloaded = download_sec_edgar(
            SecEdgarDownloadOptions(
                ciks=options.ciks,
                retrieval_time=retrieved_at,
                user_agent=options.credentials.sec_edgar_user_agent,
                start_date=options.start_date,
                end_date=options.end_date,
                fetch_json=options.fetch_json,
            )
        )
        record_groups = [downloaded.fundamental_facts]
        source = "sec_edgar"
    else:
        raise ProviderDownloadError(f"Unsupported data provider '{options.provider}'.")

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
            f"{options.provider} data could not be persisted as a Dataset Version: {error}"
        ) from error

    if not versions:
        raise ProviderDownloadError(f"{options.provider} returned no records.")
    return versions
