"""Provider download orchestration and Composite Dataset Version persistence."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, TypeVar
from uuid import uuid4

import pandas as pd

from .download_jobs import CancellationToken, DownloadPhase, ProgressRecorder
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
    ProviderDownload,
    ProviderDownloadError,
    SecEdgarDownloadSpec,
    TiingoDownloadSpec,
    _fetch_json,
    download_alpaca,
    download_massive,
    download_sec_edgar,
    download_tiingo,
    fetch_massive_grouped_daily,
    fetch_sec_edgar_cik,
    fetch_tiingo_symbol,
)
from .request_control import ControlledJsonFetcher, RateGate
from .security_lists import DatedSecurityList, get_security_list

T = TypeVar("T")
R = TypeVar("R")


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
class WorkItemOrdinal:
    provider_idx: int
    security_idx: int
    datatype_idx: int
    subpart_idx: int

    def __lt__(self, other: WorkItemOrdinal) -> bool:
        return (
            self.provider_idx,
            self.security_idx,
            self.datatype_idx,
            self.subpart_idx,
        ) < (
            other.provider_idx,
            other.security_idx,
            other.datatype_idx,
            other.subpart_idx,
        )


@dataclass(frozen=True)
class ProviderWorkItem:
    """Discrete, ordered fetch task for a single provider work unit."""

    ordinal: WorkItemOrdinal
    provider: Literal["tiingo", "massive", "sec_edgar", "alpaca"]
    dataset_type: str
    symbol: str = ""
    cik: str = ""
    target_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_grouped_daily: bool = False
    selected_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositeDownloadContext:
    """Dependencies for orchestrating a composite download."""

    credentials: ProviderCredentials
    fetch_json: JsonFetcher | None = None
    wait: Callable[[float], None] = time.sleep
    recorder: ProgressRecorder | None = None
    token: CancellationToken | None = None


@dataclass(frozen=True)
class _RawPartData:
    source: str
    dataset_type: str
    rows: list[dict[str, JsonValue]]
    warnings: list[str]
    retrieval_time: str


def map_bounded(
    fn: Callable[[T], R],
    items: Sequence[T],
    max_workers: int = 16,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[tuple[T, R]]:
    """Execute a function across items with bounded worker concurrency."""
    if not items:
        return []

    results: list[tuple[T, R]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(fn, item): item for item in items}
        for future in as_completed(future_to_item):
            if is_cancelled and is_cancelled():
                for f in future_to_item:
                    f.cancel()
                raise TimeoutError("Download cancelled.")
            item = future_to_item[future]
            res = future.result()
            results.append((item, res))
    return results


def _count_weekdays(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:  # Monday to Friday
            days.append(curr)
        curr += timedelta(days=1)
    return days


def _plan_work_items(
    spec: DatasetDownloadSpec,
    security_list: DatedSecurityList,
    recorder: ProgressRecorder | None = None,
) -> list[ProviderWorkItem]:
    """Construct all ordered ProviderWorkItem units for the composite request."""
    work_items: list[ProviderWorkItem] = []
    weekdays = _count_weekdays(spec.start_date, spec.end_date)
    d_count = len(weekdays)
    s_count = len(security_list.members)
    all_symbols = tuple(m.symbol for m in security_list.members)

    for p_idx, choice in enumerate(spec.downloads):
        provider = choice.provider
        data_types = choice.data_types or (
            ("daily_bars",) if provider in ("tiingo", "massive") else ("fundamentals",)
        )

        if provider == "tiingo":
            for s_idx, member in enumerate(security_list.members):
                work_items.append(
                    ProviderWorkItem(
                        ordinal=WorkItemOrdinal(p_idx, s_idx, 0, 0),
                        provider="tiingo",
                        dataset_type=DATASET_TYPE_DAILY_BARS,
                        symbol=member.symbol,
                        start_date=spec.start_date,
                        end_date=spec.end_date,
                    )
                )
        elif provider == "sec_edgar":
            for s_idx, member in enumerate(security_list.members):
                if member.cik:
                    work_items.append(
                        ProviderWorkItem(
                            ordinal=WorkItemOrdinal(p_idx, s_idx, 0, 0),
                            provider="sec_edgar",
                            dataset_type=DATASET_TYPE_FUNDAMENTALS,
                            symbol=member.symbol,
                            cik=member.cik,
                            start_date=spec.start_date,
                            end_date=spec.end_date,
                        )
                    )
        elif provider == "alpaca":
            for s_idx, member in enumerate(security_list.members):
                work_items.append(
                    ProviderWorkItem(
                        ordinal=WorkItemOrdinal(p_idx, s_idx, 0, 0),
                        provider="alpaca",
                        dataset_type=DATASET_TYPE_OPTIONS,
                        symbol=member.symbol,
                        start_date=spec.start_date,
                        end_date=spec.end_date,
                    )
                )
        elif provider == "massive":
            for dt_idx, dt in enumerate(data_types):
                # Massive Daily Request Planning (D < S guard)
                # Static estimate: grouped daily ~500 KB per day, per-ticker ~15 KB per ticker
                use_grouped_daily = (
                    dt in ("daily_bars", "stocks_daily")
                    and d_count < s_count
                    and (d_count * 500_000 <= 50_000_000)  # Max 50 MB payload threshold
                )

                if recorder:
                    shape_desc = "grouped_daily" if use_grouped_daily else "per_ticker"
                    est_reqs = d_count if use_grouped_daily else s_count
                    est_bytes = (
                        d_count * 500_000 if use_grouped_daily else s_count * 15_000
                    )
                    recorder.record_progress(
                        message=(
                            f"Massive planner selected {shape_desc} for {dt} "
                            f"(D={d_count}, S={s_count}, est_requests={est_reqs}, "
                            f"est_bytes={est_bytes})."
                        ),
                        details={
                            "strategy": shape_desc,
                            "estimated_requests": est_reqs,
                            "estimated_bytes": est_bytes,
                        },
                    )

                if use_grouped_daily:
                    for sub_idx, day in enumerate(weekdays):
                        work_items.append(
                            ProviderWorkItem(
                                ordinal=WorkItemOrdinal(p_idx, 0, dt_idx, sub_idx),
                                provider="massive",
                                dataset_type=DATASET_TYPE_DAILY_BARS,
                                target_date=day,
                                is_grouped_daily=True,
                                selected_symbols=all_symbols,
                            )
                        )
                else:
                    for s_idx, member in enumerate(security_list.members):
                        work_items.append(
                            ProviderWorkItem(
                                ordinal=WorkItemOrdinal(p_idx, s_idx, dt_idx, 0),
                                provider="massive",
                                dataset_type=dt,
                                symbol=member.symbol,
                                start_date=spec.start_date,
                                end_date=spec.end_date,
                            )
                        )

    return work_items


def _create_provider_gates(
    credentials: ProviderCredentials,
    wait_fn: Callable[[float], None],
) -> dict[str, RateGate]:
    """Build rate limiter gates per provider policy."""
    massive_cred = credentials.massive
    is_massive_paid = (
        massive_cred.stocks_plan_profile == "paid"
        or massive_cred.options_plan_profile == "paid"
    )

    interval_sec = (
        0.01 if is_massive_paid else max(12.0, massive_cred.request_interval_seconds)
    )
    massive_gate = RateGate(
        min_interval_seconds=interval_sec,
        max_requests_per_window=None if is_massive_paid else 5,
        window_seconds=60.0,
        sleep=wait_fn,
    )
    tiingo_gate = RateGate(min_interval_seconds=0.0, sleep=wait_fn)
    sec_gate = RateGate(min_interval_seconds=0.1, sleep=wait_fn)  # SEC 10 req/s limit
    alpaca_gate = RateGate(min_interval_seconds=0.0, sleep=wait_fn)

    return {
        "massive": massive_gate,
        "tiingo": tiingo_gate,
        "sec_edgar": sec_gate,
        "alpaca": alpaca_gate,
    }


def _execute_work_item(
    item: ProviderWorkItem,
    credentials: ProviderCredentials,
    fetchers: dict[str, ControlledJsonFetcher],
    retrieval_time: str,
) -> ProviderDownload:
    """Execute exactly one work item using the appropriate provider adapter."""
    fetcher = fetchers[item.provider]
    if item.provider == "tiingo":
        return fetch_tiingo_symbol(
            item.symbol,
            start_date=item.start_date,
            end_date=item.end_date,
            token=credentials.tiingo_api_token,
            retrieval_time=retrieval_time,
            fetch_json=fetcher,
        )
    if item.provider == "sec_edgar":
        return fetch_sec_edgar_cik(
            item.cik,
            start_date=item.start_date,
            end_date=item.end_date,
            user_agent=credentials.sec_edgar_user_agent,
            retrieval_time=retrieval_time,
            fetch_json=fetcher,
        )
    if item.provider == "alpaca":
        return download_alpaca(
            AlpacaDownloadSpec(
                symbol=item.symbol,
                start_date=item.start_date or date.today(),
                end_date=item.end_date or date.today(),
            ),
            credentials=credentials.alpaca,
            retrieval_time=retrieval_time,
            fetch_json=fetcher,
        )
    if item.provider == "massive":
        if item.is_grouped_daily and item.target_date:
            return fetch_massive_grouped_daily(
                item.target_date,
                selected_symbols=set(item.selected_symbols),
                credentials=credentials.massive,
                retrieval_time=retrieval_time,
                fetch_json=fetcher,
            )
        massive_type: Literal["stocks_daily", "stocks_minute", "options"] = (
            "stocks_minute"
            if item.dataset_type in ("minute_bars", DATASET_TYPE_MINUTE_BARS)
            else (
                "options"
                if item.dataset_type in ("options", DATASET_TYPE_OPTIONS)
                else "stocks_daily"
            )
        )
        return download_massive(
            MassiveDownloadSpec(
                symbol=item.symbol,
                start_date=item.start_date or date.today(),
                end_date=item.end_date or date.today(),
                data_type=massive_type,
            ),
            credentials=credentials.massive,
            retrieval_time=retrieval_time,
            fetch_json=fetcher,
        )

    raise ProviderDownloadError(f"Unsupported provider: {item.provider}")


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


def _aggregate_download_results(
    raw_results: list[tuple[ProviderWorkItem, ProviderDownload]],
    retrieval_time: str,
) -> tuple[list[_RawPartData], list[Security]]:
    """Bucket ordered results by (provider, dataset_type) and deduplicate securities."""
    part_buckets: dict[tuple[str, str], list[dict[str, JsonValue]]] = {}
    all_warnings: list[str] = []
    all_securities: list[Security] = []
    seen_sec_ids: set[str] = set()

    for item, download_res in raw_results:
        all_warnings.extend(download_res.warnings)
        for s in download_res.securities:
            if s.security_id not in seen_sec_ids:
                seen_sec_ids.add(s.security_id)
                all_securities.append(s)

        if download_res.daily_bars:
            bucket = part_buckets.setdefault((item.provider, DATASET_TYPE_DAILY_BARS), [])
            bucket.extend(download_res.daily_bars)
        if download_res.corporate_actions:
            bucket = part_buckets.setdefault((item.provider, DATASET_TYPE_CORPORATE_ACTIONS), [])
            bucket.extend(download_res.corporate_actions)
        if download_res.fundamental_facts:
            bucket = part_buckets.setdefault((item.provider, DATASET_TYPE_FUNDAMENTALS), [])
            bucket.extend(download_res.fundamental_facts)
        if download_res.options_records:
            dt_name = (
                DATASET_TYPE_MINUTE_BARS
                if item.dataset_type in ("minute_bars", DATASET_TYPE_MINUTE_BARS)
                else DATASET_TYPE_OPTIONS
            )
            bucket = part_buckets.setdefault((item.provider, dt_name), [])
            bucket.extend(download_res.options_records)

    all_parts_data = [
        _RawPartData(
            source=src,
            dataset_type=dt,
            rows=rows,
            warnings=all_warnings,
            retrieval_time=retrieval_time,
        )
        for (src, dt), rows in part_buckets.items()
        if rows
    ]
    return all_parts_data, all_securities


def _stage_and_publish_dataset(
    store: MarketDataStore,
    spec: DatasetDownloadSpec,
    security_list: DatedSecurityList,
    version_id: str,
    retrieval_time: str,
    all_parts_data: list[_RawPartData],
    all_securities: list[Security],
    recorder: ProgressRecorder | None,
    is_cancelled: Callable[[], bool] | None,
) -> None:
    """Stage validated Parquet parts and atomically publish to MarketDataStore."""
    if recorder:
        recorder.transition_phase(
            DownloadPhase.STAGING,
            message=f"Staging {len(all_parts_data)} dataset parts.",
        )

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        staged_parts = [_stage_part(store, raw_part, temp_dir) for raw_part in all_parts_data]

        if is_cancelled and is_cancelled():
            raise TimeoutError("Download was cancelled before publishing.")

        if recorder:
            recorder.transition_phase(
                DownloadPhase.PUBLISHING,
                message="Publishing Composite Dataset Version to storage.",
            )

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

    if recorder:
        recorder.finish_success(
            dataset_version_id=version_id,
            message="Composite dataset published successfully.",
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
    recorder = context.recorder
    token = context.token
    is_cancelled = token.is_cancelled if token else None

    # 1. Planning phase
    if recorder:
        sec_count = len(security_list.members)
        recorder.transition_phase(
            DownloadPhase.PLANNING,
            message=f"Planning download for {security_list.name} ({sec_count} securities).",
        )

    work_items = _plan_work_items(spec, security_list, recorder=recorder)
    total_units = len(work_items)

    if recorder:
        recorder.record_progress(
            total_logical_units=total_units,
            total_requests=total_units,
            completed_logical_units=0,
            completed_requests=0,
        )
        recorder.transition_phase(
            DownloadPhase.FETCHING,
            message=f"Starting fetch of {total_units} work items.",
        )

    # 2. Setup Controlled Fetchers with Provider Rate Gates
    base_fetch = context.fetch_json or _fetch_json
    gates = _create_provider_gates(context.credentials, context.wait)
    completed_requests = 0

    def on_req_start(url: str) -> None:
        if recorder:
            recorder.record_progress(
                active_operation=f"Fetching {url[:60]}...",
            )

    def on_req_end(url: str, size_bytes: int) -> None:
        nonlocal completed_requests
        completed_requests += 1
        if recorder:
            recorder.record_progress(
                completed_requests=completed_requests,
                message=f"Fetched response ({size_bytes} bytes).",
            )

    fetchers = {
        name: ControlledJsonFetcher(
            fetch=base_fetch,
            gate=gate,
            is_cancelled=is_cancelled,
            on_request_start=on_req_start,
            on_request_end=on_req_end,
        )
        for name, gate in gates.items()
    }

    # 3. Concurrent execution with map_bounded
    completed_units = 0

    def run_item(item: ProviderWorkItem) -> ProviderDownload:
        nonlocal completed_units
        if recorder:
            recorder.record_progress(
                active_provider=item.provider,
                active_operation=f"Downloading {item.symbol or item.cik or item.target_date}",
            )
        res = _execute_work_item(item, context.credentials, fetchers, retrieval_time)
        completed_units += 1
        if recorder:
            recorder.record_progress(
                completed_logical_units=completed_units,
            )
        return res

    raw_results = map_bounded(
        run_item,
        work_items,
        max_workers=16,
        is_cancelled=is_cancelled,
    )

    # 4. Ordinal Merge: Sort completed items strictly by work item ordinal
    raw_results.sort(key=lambda pair: pair[0].ordinal)

    if recorder:
        recorder.transition_phase(
            DownloadPhase.VALIDATING,
            message="Merging and validating downloaded parts.",
        )

    all_parts_data, all_securities = _aggregate_download_results(raw_results, retrieval_time)

    if not all_parts_data:
        raise ProviderDownloadError("Providers returned no records for the requested downloads.")

    # 5. Staging & Publishing Phase
    _stage_and_publish_dataset(
        store=store,
        spec=spec,
        security_list=security_list,
        version_id=version_id,
        retrieval_time=retrieval_time,
        all_parts_data=all_parts_data,
        all_securities=all_securities,
        recorder=recorder,
        is_cancelled=is_cancelled,
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
