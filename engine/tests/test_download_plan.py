"""Download planning estimates for broad-market acquisition."""

from datetime import date

from market_research_lab.download_jobs import DatasetDownloadSpec, ProviderDownloadChoice
from market_research_lab.downloads import estimate_download_plan


def _spec(*data_types: str, start: str, end: str) -> DatasetDownloadSpec:
    return DatasetDownloadSpec(
        security_list_id="sp-500",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        downloads=(ProviderDownloadChoice("massive", data_types),),
    )


def test_daily_plan_uses_grouped_dates_when_they_require_fewer_calls():
    estimate = estimate_download_plan(
        _spec("daily_bars", start="2024-01-01", end="2024-01-05"),
        security_count=500,
    )

    assert estimate.logical_units == 5
    assert estimate.minimum_paced_seconds == 49.0
    assert estimate.acquisition_shape == "Massive grouped daily by date"


def test_long_daily_plan_and_minute_plan_use_one_range_call_per_security():
    estimate = estimate_download_plan(
        _spec("daily_bars", "minute_bars", start="2020-01-01", end="2024-12-31"),
        security_count=500,
    )

    assert estimate.logical_units == 1_000
    assert estimate.minimum_paced_seconds == 12_237.75
    assert estimate.acquisition_shape == "massive per-security range"
