"""Provider download orchestration and Composite Dataset Version persistence."""

from __future__ import annotations

import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, TypeVar
from uuid import uuid4

import pandas as pd

from .download_jobs import (
    CancellationToken,
    DatasetDownloadSpec,
    DownloadPhase,
    ProgressRecorder,
    ProviderDownloadChoice,
)
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
from .request_control import ControlledJsonFetcher, RateGate, RequestResultCache
from .security_lists import DatedSecurityList, get_security_list

T = TypeVar("T")
R = TypeVar("R")


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
    cache: RequestResultCache | None = None


@dataclass(frozen=True)
class DownloadPlanEstimate:
    logical_units: int
    minimum_paced_seconds: float
    acquisition_shape: str
    note: str = "Pagination may add HTTP requests."


def estimate_download_plan(spec: DatasetDownloadSpec, security_count: int) -> DownloadPlanEstimate:
    """Estimate logical work and minimum provider pacing before a download starts."""
    weekdays = len(_count_weekdays(spec.start_date, spec.end_date))
    units = 0
    massive_units = 0
    shapes: list[str] = []
    for choice in spec.downloads:
        for data_type in choice.data_types or ("daily_bars",):
            if (
                choice.provider == "massive"
                and data_type in ("daily_bars", "stocks_daily")
                and 0 < weekdays < security_count
            ):
                planned_units = weekdays
                shapes.append("Massive grouped daily by date")
            else:
                planned_units = security_count
                shapes.append(f"{choice.provider} per-security range")
            units += planned_units
            if choice.provider == "massive":
                massive_units += planned_units
    minimum_seconds = max(0, massive_units - 1) * 12.25
    return DownloadPlanEstimate(units, minimum_seconds, "; ".join(dict.fromkeys(shapes)))


@dataclass(frozen=True)
class _RawPartData:
    source: str
    dataset_type: str
    rows: list[dict[str, JsonValue]]
    warnings: list[str]
    retrieval_time: str


@dataclass(frozen=True)
class DatasetPublishContext:
    """Parameter object grouping inputs for dataset staging and publishing."""

    store: MarketDataStore
    spec: DatasetDownloadSpec
    security_list: DatedSecurityList
    version_id: str
    retrieval_time: str
    all_parts_data: list[_RawPartData]
    all_securities: list[Security]
    recorder: ProgressRecorder | None = None
    is_cancelled: Callable[[], bool] | None = None
    begin_publication: Callable[[], bool] | None = None


def map_bounded(
    fn: Callable[[T], R],
    items: Sequence[T],
    max_workers: int = 4,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[tuple[T, R]]:
    """Execute a function across items with bounded worker concurrency and bounded replenishment."""
    if not items:
        return []

    results: list[tuple[T, R]] = []
    item_iter = iter(items)
    executor = ThreadPoolExecutor(max_workers=max_workers)
    cancelled = False
    try:
        in_flight: dict[Future[R], T] = {}

        for item in item_iter:
            if is_cancelled and is_cancelled():
                cancelled = True
                raise TimeoutError("Download cancelled.")
            future = executor.submit(fn, item)
            in_flight[future] = item
            if len(in_flight) >= max_workers:
                break

        while in_flight:
            if is_cancelled and is_cancelled():
                for f in in_flight:
                    f.cancel()
                cancelled = True
                raise TimeoutError("Download cancelled.")

            done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
            for completed_future in done:
                item = in_flight.pop(completed_future)
                res = completed_future.result()
                results.append((item, res))

                try:
                    next_item = next(item_iter)
                    if is_cancelled and is_cancelled():
                        for f in in_flight:
                            f.cancel()
                        cancelled = True
                        raise TimeoutError("Download cancelled.")
                    new_future = executor.submit(fn, next_item)
                    in_flight[new_future] = next_item
                except StopIteration:
                    pass

        return results
    finally:
        executor.shutdown(wait=not cancelled, cancel_futures=cancelled)


def _count_weekdays(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:  # Monday to Friday
            days.append(curr)
        curr += timedelta(days=1)
    return days


class ProviderDriver(Protocol):
    """Driver protocol planning and executing work items for one provider."""

    def plan(
        self,
        p_idx: int,
        choice: ProviderDownloadChoice,
        security_list: DatedSecurityList,
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder | None = None,
    ) -> list[ProviderWorkItem]: ...

    def execute(
        self,
        item: ProviderWorkItem,
        credentials: ProviderCredentials,
        fetchers: dict[str, ControlledJsonFetcher],
        retrieval_time: str,
    ) -> ProviderDownload: ...


class TiingoDriver:
    def plan(
        self,
        p_idx: int,
        choice: ProviderDownloadChoice,
        security_list: DatedSecurityList,
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder | None = None,
    ) -> list[ProviderWorkItem]:
        return [
            ProviderWorkItem(
                ordinal=WorkItemOrdinal(p_idx, s_idx, 0, 0),
                provider="tiingo",
                dataset_type=DATASET_TYPE_DAILY_BARS,
                symbol=member.symbol,
                start_date=spec.start_date,
                end_date=spec.end_date,
            )
            for s_idx, member in enumerate(security_list.members)
        ]

    def execute(
        self,
        item: ProviderWorkItem,
        credentials: ProviderCredentials,
        fetchers: dict[str, ControlledJsonFetcher],
        retrieval_time: str,
    ) -> ProviderDownload:
        return fetch_tiingo_symbol(
            item.symbol,
            start_date=item.start_date,
            end_date=item.end_date,
            token=credentials.tiingo_api_token,
            retrieval_time=retrieval_time,
            fetch_json=fetchers["tiingo"],
        )


class SecEdgarDriver:
    def plan(
        self,
        p_idx: int,
        choice: ProviderDownloadChoice,
        security_list: DatedSecurityList,
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder | None = None,
    ) -> list[ProviderWorkItem]:
        items: list[ProviderWorkItem] = []
        for s_idx, member in enumerate(security_list.members):
            if member.cik:
                items.append(
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
        return items

    def execute(
        self,
        item: ProviderWorkItem,
        credentials: ProviderCredentials,
        fetchers: dict[str, ControlledJsonFetcher],
        retrieval_time: str,
    ) -> ProviderDownload:
        return fetch_sec_edgar_cik(
            item.cik,
            start_date=item.start_date,
            end_date=item.end_date,
            user_agent=credentials.sec_edgar_user_agent,
            retrieval_time=retrieval_time,
            fetch_json=fetchers["sec_edgar"],
        )


class AlpacaDriver:
    def plan(
        self,
        p_idx: int,
        choice: ProviderDownloadChoice,
        security_list: DatedSecurityList,
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder | None = None,
    ) -> list[ProviderWorkItem]:
        return [
            ProviderWorkItem(
                ordinal=WorkItemOrdinal(p_idx, s_idx, 0, 0),
                provider="alpaca",
                dataset_type=DATASET_TYPE_OPTIONS,
                symbol=member.symbol,
                start_date=spec.start_date,
                end_date=spec.end_date,
            )
            for s_idx, member in enumerate(security_list.members)
        ]

    def execute(
        self,
        item: ProviderWorkItem,
        credentials: ProviderCredentials,
        fetchers: dict[str, ControlledJsonFetcher],
        retrieval_time: str,
    ) -> ProviderDownload:
        return download_alpaca(
            AlpacaDownloadSpec(
                symbol=item.symbol,
                start_date=item.start_date or date.today(),
                end_date=item.end_date or date.today(),
            ),
            credentials=credentials.alpaca,
            retrieval_time=retrieval_time,
            fetch_json=fetchers["alpaca"],
        )


class MassiveDriver:
    def plan(
        self,
        p_idx: int,
        choice: ProviderDownloadChoice,
        security_list: DatedSecurityList,
        spec: DatasetDownloadSpec,
        recorder: ProgressRecorder | None = None,
    ) -> list[ProviderWorkItem]:
        items: list[ProviderWorkItem] = []
        weekdays = _count_weekdays(spec.start_date, spec.end_date)
        d_count = len(weekdays)
        s_count = len(security_list.members)
        all_symbols = tuple(m.symbol for m in security_list.members)
        data_types = choice.data_types or ("daily_bars",)

        for dt_idx, dt in enumerate(data_types):
            use_grouped_daily = (
                dt in ("daily_bars", "stocks_daily")
                and d_count < s_count
                and d_count > 0
            )

            if use_grouped_daily:
                if recorder:
                    saved_requests = s_count - d_count
                    recorder.record_progress(
                        message=(
                            f"Massive planner selected Grouped Daily: {d_count} date requests "
                            f"instead of {s_count} per-security range requests "
                            f"(saving {saved_requests} requests)."
                        )
                    )
                for day_idx, day in enumerate(weekdays):
                    items.append(
                        ProviderWorkItem(
                            ordinal=WorkItemOrdinal(p_idx, 0, dt_idx, day_idx),
                            provider="massive",
                            dataset_type="stocks_daily_grouped",
                            target_date=day,
                            is_grouped_daily=True,
                            selected_symbols=all_symbols,
                        )
                    )
            else:
                for s_idx, member in enumerate(security_list.members):
                    items.append(
                        ProviderWorkItem(
                            ordinal=WorkItemOrdinal(p_idx, s_idx, dt_idx, 0),
                            provider="massive",
                            dataset_type=dt,
                            symbol=member.symbol,
                            start_date=spec.start_date,
                            end_date=spec.end_date,
                        )
                    )
        return items

    def execute(
        self,
        item: ProviderWorkItem,
        credentials: ProviderCredentials,
        fetchers: dict[str, ControlledJsonFetcher],
        retrieval_time: str,
    ) -> ProviderDownload:
        if item.is_grouped_daily and item.target_date:
            return fetch_massive_grouped_daily(
                item.target_date,
                selected_symbols=item.selected_symbols,
                credentials=credentials.massive,
                retrieval_time=retrieval_time,
                fetch_json=fetchers["massive_stocks"],
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
        fetcher = (
            fetchers["massive_options"]
            if massive_type == "options"
            else fetchers["massive_stocks"]
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


PROVIDER_DRIVERS: dict[str, ProviderDriver] = {
    "tiingo": TiingoDriver(),
    "sec_edgar": SecEdgarDriver(),
    "alpaca": AlpacaDriver(),
    "massive": MassiveDriver(),
}


def _plan_work_items(
    spec: DatasetDownloadSpec,
    security_list: DatedSecurityList,
    recorder: ProgressRecorder | None = None,
) -> list[ProviderWorkItem]:
    """Construct all ordered ProviderWorkItem units for the composite request."""
    work_items: list[ProviderWorkItem] = []
    for p_idx, choice in enumerate(spec.downloads):
        driver = PROVIDER_DRIVERS.get(choice.provider)
        if driver is None:
            raise ProviderDownloadError(f"Unsupported provider: {choice.provider}")
        work_items.extend(driver.plan(p_idx, choice, security_list, spec, recorder))
    return work_items


def _create_provider_gates(
    credentials: ProviderCredentials,
    wait_fn: Callable[[float], None],
    on_wait: Callable[[float], None] | None = None,
) -> dict[str, RateGate]:
    """Build rate limiter gates per provider policy."""
    massive_cred = credentials.massive

    # Massive Stocks Gate
    if massive_cred.stocks_plan_profile == "paid":
        massive_stocks_gate = RateGate(
            min_interval_seconds=1.0 / 95.0,  # 95 req/s safety margin under 100/s
            max_requests_per_window=None,
            sleep=wait_fn,
            on_wait=on_wait,
        )
    else:
        massive_stocks_gate = RateGate(
            min_interval_seconds=12.25,  # 12.25s safety margin for 5 req/min window
            max_requests_per_window=5,
            window_seconds=60.0,
            sleep=wait_fn,
            on_wait=on_wait,
        )

    # Massive Options Gate
    if massive_cred.options_plan_profile == "paid":
        massive_options_gate = RateGate(
            min_interval_seconds=1.0 / 95.0,
            max_requests_per_window=None,
            sleep=wait_fn,
            on_wait=on_wait,
        )
    else:
        massive_options_gate = RateGate(
            min_interval_seconds=12.25,
            max_requests_per_window=5,
            window_seconds=60.0,
            sleep=wait_fn,
            on_wait=on_wait,
        )

    tiingo_gate = RateGate(min_interval_seconds=0.0, sleep=wait_fn, on_wait=on_wait)
    sec_gate = RateGate(min_interval_seconds=0.1, sleep=wait_fn, on_wait=on_wait)  # 10 req/s limit
    alpaca_gate = RateGate(min_interval_seconds=0.0, sleep=wait_fn, on_wait=on_wait)

    return {
        "massive_stocks": massive_stocks_gate,
        "massive_options": massive_options_gate,
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
    """Execute exactly one work item using the appropriate provider driver."""
    driver = PROVIDER_DRIVERS.get(item.provider)
    if driver is None:
        raise ProviderDownloadError(f"Unsupported provider: {item.provider}")
    return driver.execute(item, credentials, fetchers, retrieval_time)


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


def _stage_and_publish_dataset(context: DatasetPublishContext) -> None:
    """Stage validated Parquet parts and atomically publish to MarketDataStore."""
    if context.recorder:
        context.recorder.transition_phase(
            DownloadPhase.STAGING,
            message=f"Staging {len(context.all_parts_data)} dataset parts.",
        )

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        staged_parts = [
            _stage_part(context.store, raw_part, temp_dir)
            for raw_part in context.all_parts_data
        ]

        if context.is_cancelled and context.is_cancelled():
            raise TimeoutError("Download was cancelled before publishing.")

        if context.begin_publication and not context.begin_publication():
            raise TimeoutError("Download was cancelled before publishing.")
        if context.recorder:
            context.recorder.transition_phase(
                DownloadPhase.PUBLISHING,
                message="Publishing Composite Dataset Version to storage.",
            )

        req_payload = {
            "security_list_id": context.spec.security_list_id,
            "start_date": context.spec.start_date.isoformat(),
            "end_date": context.spec.end_date.isoformat(),
            "downloads": [
                {"provider": c.provider, "data_types": list(c.data_types)}
                for c in context.spec.downloads
            ],
        }
        context.store.publish_composite(
            CompositePublishPlan(
                version_id=context.version_id,
                retrieval_time=context.retrieval_time,
                security_list_id=context.security_list.id,
                security_list_as_of_date=context.security_list.as_of_date,
                request_payload=req_payload,
                parts=staged_parts,
                securities=context.all_securities,
            )
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
            total_requests=0,
            completed_logical_units=0,
            completed_requests=0,
        )
        recorder.transition_phase(
            DownloadPhase.FETCHING,
            message=f"Starting fetch of {total_units} work items.",
        )

    # 2. Setup Controlled Fetchers with Provider Rate Gates
    base_fetch = context.fetch_json or _fetch_json
    on_wait_cb = (
        (lambda s: recorder.record_progress(rate_limit_wait_seconds=s))
        if recorder
        else None
    )
    gates = _create_provider_gates(context.credentials, context.wait, on_wait=on_wait_cb)
    completed_requests = 0
    started_requests = 0
    request_lock = threading.Lock()

    def on_req_start(url: str) -> None:
        nonlocal started_requests
        with request_lock:
            started_requests += 1
            observed_total = started_requests
        if recorder:
            recorder.record_progress(
                total_requests=observed_total,
                active_operation=f"Fetching {url[:60]}...",
            )

    def on_req_end(url: str, size_bytes: int) -> None:
        nonlocal completed_requests
        with request_lock:
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
            cache=context.cache,
        )
        for name, gate in gates.items()
    }

    # 3. Execution Phase with bounded worker concurrency and progress streaming
    completed_units = 0

    def run_item(item: ProviderWorkItem) -> ProviderDownload:
        nonlocal completed_units
        if recorder:
            item_desc = f"{item.provider} [{item.dataset_type}]"
            if item.symbol:
                item_desc += f" {item.symbol}"
            elif item.target_date:
                item_desc += f" {item.target_date.isoformat()}"
            recorder.record_progress(
                active_provider=item.provider,
                active_operation=item_desc,
            )

        result = _execute_work_item(item, context.credentials, fetchers, retrieval_time)

        with request_lock:
            completed_units += 1
            observed_completed_units = completed_units
        if recorder:
            recorder.record_progress(
                completed_logical_units=observed_completed_units,
            )
        return result

    raw_results = map_bounded(
        run_item,
        work_items,
        max_workers=4,
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
    pub_context = DatasetPublishContext(
        store=store,
        spec=spec,
        security_list=security_list,
        version_id=version_id,
        retrieval_time=retrieval_time,
        all_parts_data=all_parts_data,
        all_securities=all_securities,
        recorder=recorder,
        is_cancelled=is_cancelled,
        begin_publication=(token.begin_publication if token else None),
    )
    _stage_and_publish_dataset(pub_context)

    if recorder:
        recorder.finish_success(
            dataset_version_id=version_id,
            message=f"Composite dataset version '{version_id}' successfully created.",
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
