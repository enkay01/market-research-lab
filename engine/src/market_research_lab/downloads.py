"""Provider download orchestration and Composite Dataset Version persistence."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pandas as pd

from .json_types import JsonValue
from .market_data import (
    _INGESTION_VALIDATORS,
    DATASET_TYPE_CORPORATE_ACTIONS,
    DATASET_TYPE_DAILY_BARS,
    DATASET_TYPE_FUNDAMENTALS,
    DATASET_TYPE_MINUTE_BARS,
    DATASET_TYPE_OPTIONS,
    CompositePublishPlan,
    CoverageReport,
    DatasetVersion,
    IngestionRequest,
    MarketDataStore,
    Security,
    StagedDatasetPart,
    ValidationSummarySpec,
    _calculate_dataset_coverage_range,
)
from .providers import (
    AlpacaDownloadSpec,
    JsonFetcher,
    MassiveDownloadSpec,
    ProviderCredentials,
    ProviderDownloadError,
    SecEdgarDownloadSpec,
    TiingoDownloadSpec,
    download_alpaca,
    download_massive,
    download_sec_edgar,
    download_tiingo,
)
from .security_lists import DatedSecurityList, get_security_list


@dataclass(frozen=True)
class ProviderDownloadChoice:
    """Requested provider and data types within a composite download."""

    provider: Literal["tiingo", "massive", "sec_edgar", "alpaca"]
    data_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetDownloadSpec:
    """Frozen parameter object for one composite dataset download operation."""

    security_list_id: str
    start_date: date
    end_date: date
    downloads: tuple[ProviderDownloadChoice, ...]


@dataclass(frozen=True)
class ProviderDownloadContext:
    """Context holding all execution dependencies for one provider download."""

    security_list: DatedSecurityList
    spec: DatasetDownloadSpec
    choice: ProviderDownloadChoice
    credentials: ProviderCredentials
    retrieval_time: str
    fetch_json: JsonFetcher | None
    wait: Callable[[float], None]


@dataclass(frozen=True)
class CompositeDownloadContext:
    """Dependencies for orchestrating a composite download."""

    credentials: ProviderCredentials
    fetch_json: JsonFetcher | None = None
    wait: Callable[[float], None] = time.sleep


@dataclass
class _ProviderOutput:
    parts_data: list[tuple[str, str, list[dict[str, JsonValue]]]] = field(default_factory=list)
    securities: list[Security] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _RawPartData:
    source: str
    dataset_type: str
    rows: list[dict[str, JsonValue]]
    warnings: list[str]
    retrieval_time: str


def _download_tiingo_parts(ctx: ProviderDownloadContext) -> _ProviderOutput:
    symbols = tuple(m.symbol for m in ctx.security_list.members)
    downloaded = download_tiingo(
        TiingoDownloadSpec(
            symbols=symbols, start_date=ctx.spec.start_date, end_date=ctx.spec.end_date
        ),
        token=ctx.credentials.tiingo_api_token,
        retrieval_time=ctx.retrieval_time,
        fetch_json=ctx.fetch_json,
    )
    output = _ProviderOutput(securities=downloaded.securities, warnings=downloaded.warnings)
    if downloaded.daily_bars:
        output.parts_data.append(("tiingo", DATASET_TYPE_DAILY_BARS, downloaded.daily_bars))
    if downloaded.corporate_actions and (
        not ctx.choice.data_types or "corporate_actions" in ctx.choice.data_types
    ):
        output.parts_data.append(
            ("tiingo", DATASET_TYPE_CORPORATE_ACTIONS, downloaded.corporate_actions)
        )
    return output


def _download_massive_parts(ctx: ProviderDownloadContext) -> _ProviderOutput:
    output = _ProviderOutput()
    data_types = ctx.choice.data_types or ("daily_bars",)
    minute_bars: list[dict[str, JsonValue]] = []
    daily_bars: list[dict[str, JsonValue]] = []
    options_records: list[dict[str, JsonValue]] = []

    interval = ctx.credentials.massive.request_interval_seconds
    is_first_request = True
    for member in ctx.security_list.members:
        for dt in data_types:
            if not is_first_request and interval > 0:
                ctx.wait(interval)
            is_first_request = False

            massive_type: Literal["stocks_daily", "stocks_minute", "options"] = (
                "stocks_minute"
                if dt == "minute_bars"
                else ("options" if dt == "options" else "stocks_daily")
            )
            res = download_massive(
                MassiveDownloadSpec(
                    symbol=member.symbol,
                    start_date=ctx.spec.start_date,
                    end_date=ctx.spec.end_date,
                    data_type=massive_type,
                ),
                credentials=ctx.credentials.massive,
                retrieval_time=ctx.retrieval_time,
                fetch_json=ctx.fetch_json,
            )
            output.securities.extend(res.securities)
            output.warnings.extend(res.warnings)
            if dt == "minute_bars":
                minute_bars.extend(res.options_records)
            elif dt == "options":
                options_records.extend(res.options_records)
            else:
                daily_bars.extend(res.daily_bars)

    if minute_bars:
        output.parts_data.append(("massive", DATASET_TYPE_MINUTE_BARS, minute_bars))
    if daily_bars:
        output.parts_data.append(("massive", DATASET_TYPE_DAILY_BARS, daily_bars))
    if options_records:
        output.parts_data.append(("massive", DATASET_TYPE_OPTIONS, options_records))
    return output


def _download_sec_edgar_parts(ctx: ProviderDownloadContext) -> _ProviderOutput:
    output = _ProviderOutput()
    ciks: list[str] = []
    for m in ctx.security_list.members:
        if m.cik:
            ciks.append(m.cik)
        else:
            output.warnings.append(
                f"Security {m.symbol} has no CIK; skipped for SEC EDGAR fundamentals."
            )

    if not ciks:
        return output

    downloaded = download_sec_edgar(
        SecEdgarDownloadSpec(
            ciks=tuple(ciks), start_date=ctx.spec.start_date, end_date=ctx.spec.end_date
        ),
        user_agent=ctx.credentials.sec_edgar_user_agent,
        retrieval_time=ctx.retrieval_time,
        fetch_json=ctx.fetch_json,
    )
    output.securities.extend(downloaded.securities)
    output.warnings.extend(downloaded.warnings)
    if downloaded.fundamental_facts:
        output.parts_data.append(
            ("sec_edgar", DATASET_TYPE_FUNDAMENTALS, downloaded.fundamental_facts)
        )
    return output


def _download_alpaca_parts(ctx: ProviderDownloadContext) -> _ProviderOutput:
    output = _ProviderOutput()
    for member in ctx.security_list.members:
        downloaded = download_alpaca(
            AlpacaDownloadSpec(
                symbol=member.symbol,
                start_date=ctx.spec.start_date,
                end_date=ctx.spec.end_date,
            ),
            credentials=ctx.credentials.alpaca,
            retrieval_time=ctx.retrieval_time,
            fetch_json=ctx.fetch_json,
        )
        output.securities.extend(downloaded.securities)
        output.warnings.extend(downloaded.warnings)
        if downloaded.options_records:
            output.parts_data.append(
                ("alpaca", DATASET_TYPE_OPTIONS, downloaded.options_records)
            )
    return output


_PROVIDER_DISPATCH = {
    "tiingo": _download_tiingo_parts,
    "massive": _download_massive_parts,
    "sec_edgar": _download_sec_edgar_parts,
    "alpaca": _download_alpaca_parts,
}


def _stage_part(
    store: MarketDataStore,
    part_data: _RawPartData,
    temp_dir: Path,
) -> StagedDatasetPart:
    validator = _INGESTION_VALIDATORS.get(part_data.dataset_type)
    if validator is None:
        raise ValueError(f"Unsupported dataset type: {part_data.dataset_type}")

    request = IngestionRequest(source=part_data.source, retrieval_time=part_data.retrieval_time)
    df_raw = pd.DataFrame(part_data.rows)
    validation = validator(store, df_raw, request)
    valid_rows = validation.valid_rows
    if not valid_rows:
        raise ProviderDownloadError(
            f"{part_data.source} returned 0 valid rows for {part_data.dataset_type}."
        )

    part_id = str(uuid4())
    df_valid = pd.DataFrame(valid_rows)
    has_temporal = store._has_complete_temporal_provenance(df_valid, part_data.dataset_type)
    cov = _calculate_dataset_coverage_range(df_valid)

    if part_data.dataset_type == DATASET_TYPE_FUNDAMENTALS:
        numeric_values = pd.to_numeric(df_valid["value"], errors="coerce")
        if not numeric_values.notna().all():
            df_valid["value"] = df_valid["value"].astype(str)

    staged_path = temp_dir / f"{part_id}.parquet"
    df_valid.to_parquet(staged_path, engine="pyarrow", index=False)

    all_warnings = (validation.warnings + part_data.warnings)[:100]
    summary = store._build_validation_summary(
        ValidationSummarySpec(
            row_count=len(valid_rows),
            rejected_count=len(df_raw) - len(valid_rows),
            missing_fields=validation.missing_fields,
            warnings=all_warnings,
            has_temporal_provenance=has_temporal,
            dataset_type=part_data.dataset_type,
        )
    )
    return StagedDatasetPart(
        part_id=part_id,
        source=part_data.source,
        dataset_type=part_data.dataset_type,
        df_valid=df_valid,
        summary=summary,
        coverage_start=cov.coverage_start,
        coverage_end=cov.coverage_end,
        staged_path=staged_path,
        file_name=f"{part_id}.parquet",
    )


def download_composite(
    store: MarketDataStore,
    spec: DatasetDownloadSpec,
    context: CompositeDownloadContext,
) -> CoverageReport:
    """Orchestrate one atomic composite download for a Security List."""
    security_list = get_security_list(spec.security_list_id)
    retrieval_time = datetime.now(UTC).isoformat()
    version_id = str(uuid4())

    all_parts_data: list[_RawPartData] = []
    all_securities: list[Security] = []

    # 1. Fetch from providers
    for choice in spec.downloads:
        downloader = _PROVIDER_DISPATCH.get(choice.provider)
        if not downloader:
            raise ProviderDownloadError(f"Unsupported provider: {choice.provider}")
        try:
            output = downloader(
                ProviderDownloadContext(
                    security_list=security_list,
                    spec=spec,
                    choice=choice,
                    credentials=context.credentials,
                    retrieval_time=retrieval_time,
                    fetch_json=context.fetch_json,
                    wait=context.wait,
                )
            )
        except ProviderDownloadError:
            raise
        except Exception as error:
            raise ProviderDownloadError(
                f"{choice.provider} request failed ({type(error).__name__}: {error})."
            ) from error

        all_securities.extend(output.securities)
        for src, dt, rows in output.parts_data:
            all_parts_data.append(
                _RawPartData(
                    source=src,
                    dataset_type=dt,
                    rows=rows,
                    warnings=output.warnings,
                    retrieval_time=retrieval_time,
                )
            )

    if not all_parts_data:
        raise ProviderDownloadError("Providers returned no records for the requested downloads.")

    # 2. Stage and publish all parts atomically
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        staged_parts = [_stage_part(store, raw_part, temp_dir) for raw_part in all_parts_data]

        req_payload = {
            "security_list_id": spec.security_list_id,
            "start_date": spec.start_date.isoformat(),
            "end_date": spec.end_date.isoformat(),
            "downloads": [
                {"provider": c.provider, "data_types": list(c.data_types)}
                for c in spec.downloads
            ],
        }
        store.publish_composite(
            CompositePublishPlan(
                version_id=version_id,
                retrieval_time=retrieval_time,
                security_list_id=spec.security_list_id,
                security_list_as_of_date=security_list.as_of_date,
                request_payload=req_payload,
                parts=staged_parts,
                securities=all_securities,
            )
        )

    return store.coverage(version_id)


def download_provider(
    store: MarketDataStore,
    request: TiingoDownloadSpec | SecEdgarDownloadSpec | AlpacaDownloadSpec | MassiveDownloadSpec,
    *,
    credentials: ProviderCredentials,
    fetch_json: JsonFetcher | None = None,
) -> list[DatasetVersion]:
    """Fetch validated single-provider data before creating any Dataset Version."""
    retrieved_at = datetime.now(UTC).isoformat()

    if isinstance(request, MassiveDownloadSpec):
        downloaded = download_massive(
            request,
            credentials=credentials.massive,
            retrieval_time=retrieved_at,
            fetch_json=fetch_json,
        )
        record_groups = [downloaded.daily_bars, downloaded.options_records]
        source = "massive"
    elif isinstance(request, AlpacaDownloadSpec):
        downloaded = download_alpaca(
            request,
            credentials=credentials.alpaca,
            retrieval_time=retrieved_at,
            fetch_json=fetch_json,
        )
        record_groups = [downloaded.options_records]
        source = "alpaca"
    elif isinstance(request, TiingoDownloadSpec):
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
                        IngestionRequest(source=source, retrieval_time=retrieved_at),
                        rows,
                        warnings=downloaded.warnings,
                    )
                )
        store.upsert_securities(downloaded.securities, source=source, retrieval_time=retrieved_at)
    except Exception as error:
        for version in versions:
            store.discard_dataset_version(version)
        raise ProviderDownloadError(
            f"{source} data could not be persisted as a Dataset Version: {error}"
        ) from error

    if not versions:
        raise ProviderDownloadError(f"{source} returned no records.")
    return versions
