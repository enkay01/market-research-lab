"""Tests for comparable-company Valuations."""

from __future__ import annotations

from market_research_lab.valuation import ComparableCompanyInput, evaluate_comparables

CompanyMetric = (
    float | str | tuple[str, ...] | dict[str, str] | dict[str, tuple[str, ...]] | None
)


def _as_float(value: CompanyMetric) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _as_tuple(value: CompanyMetric) -> tuple[str, ...]:
    return value if isinstance(value, tuple) else ()


def _as_dict(value: CompanyMetric) -> dict[str, str]:
    return value if isinstance(value, dict) else {}


def make_company_input(
    symbol: str = "AAPL",
    *,
    name: str | None = None,
    currency: str = "USD",
    **overrides: CompanyMetric,
) -> ComparableCompanyInput:
    sec_id = str(overrides.pop("security_id", symbol))
    default_ds = (f"bars-{sec_id.lower()}", f"fundamentals-{sec_id.lower()}")
    ds_ids = overrides.pop("dataset_version_ids", default_ds)
    default_prov = {"market_cap": ds_ids[0]} if isinstance(ds_ids, tuple) and ds_ids else {}
    default_input_ds = (
        {"market_cap": (ds_ids[0],)} if isinstance(ds_ids, tuple) and ds_ids else {}
    )

    fields: dict[str, CompanyMetric] = {
        "security_id": sec_id,
        "symbol": symbol,
        "name": name or f"{symbol} Inc.",
        "currency": currency,
        "market_cap": 300.0,
        "total_debt": 50.0,
        "cash": 20.0,
        "revenue": 100.0,
        "ebitda": 25.0,
        "net_income": 10.0,
        "free_cash_flow": 15.0,
        "dataset_version_ids": ds_ids,
        "provenance": default_prov,
        "units": {"market_cap": currency},
        "input_dataset_versions": default_input_ds,
        "input_warnings": (),
    }
    fields.update(overrides)

    return ComparableCompanyInput(
        security_id=str(fields["security_id"]),
        symbol=str(fields["symbol"]),
        name=str(fields["name"]),
        currency=str(fields["currency"]),
        market_cap=_as_float(fields["market_cap"]),
        total_debt=_as_float(fields["total_debt"]),
        cash=_as_float(fields["cash"]),
        revenue=_as_float(fields["revenue"]),
        ebitda=_as_float(fields["ebitda"]),
        net_income=_as_float(fields["net_income"]),
        free_cash_flow=_as_float(fields["free_cash_flow"]),
        dataset_version_ids=_as_tuple(fields["dataset_version_ids"]),
        provenance=_as_dict(fields["provenance"]),
        units=_as_dict(fields["units"]),
        input_dataset_versions=fields["input_dataset_versions"]
        if isinstance(fields["input_dataset_versions"], dict)
        else {},
        input_warnings=_as_tuple(fields["input_warnings"]),
    )


def test_evaluate_comparables_calculates_supported_multiples_and_peer_medians():
    target = make_company_input(
        "AAPL",
        name="Apple Inc.",
        market_cap=300.0,
        total_debt=50.0,
        cash=20.0,
        revenue=100.0,
        ebitda=25.0,
        net_income=10.0,
        free_cash_flow=15.0,
    )
    peer = make_company_input(
        "MSFT",
        name="Microsoft Corp.",
        market_cap=600.0,
        total_debt=100.0,
        cash=50.0,
        revenue=200.0,
        ebitda=50.0,
        net_income=20.0,
        free_cash_flow=30.0,
    )

    result = evaluate_comparables(target, [peer], calculated_at="2026-08-16T12:00:00Z")

    assert result.target.enterprise_value == 330.0
    assert result.target.price_to_earnings == 30.0
    assert result.target.ev_to_revenue == 3.3
    assert result.target.ev_to_ebitda == 13.2
    assert result.target.free_cash_flow_yield == 0.05
    assert result.peer_medians.price_to_earnings == 30.0
    assert result.peer_medians.ev_to_revenue == 3.25
    assert result.dataset_version_ids == [
        "bars-aapl",
        "bars-msft",
        "fundamentals-aapl",
        "fundamentals-msft",
    ]
    assert result.calculated_at == "2026-08-16T12:00:00Z"


def test_evaluate_comparables_warns_for_missing_or_incompatible_inputs():
    target = make_company_input(
        "AAPL",
        name="Apple Inc.",
        market_cap=300.0,
        total_debt=None,
        cash=None,
        revenue=100.0,
        ebitda=None,
        net_income=-10.0,
        free_cash_flow=None,
        dataset_version_ids=("bars-aapl",),
        provenance={},
        units={},
        input_dataset_versions={},
    )
    peer = make_company_input(
        "SAP",
        name="SAP SE",
        currency="EUR",
        market_cap=100.0,
        total_debt=10.0,
        cash=5.0,
        revenue=20.0,
        ebitda=5.0,
        net_income=4.0,
        free_cash_flow=3.0,
        dataset_version_ids=("bars-sap",),
        provenance={},
        units={},
        input_dataset_versions={},
    )

    result = evaluate_comparables(target, [peer], calculated_at="2026-08-16T12:00:00Z")

    assert result.target.enterprise_value is None
    assert result.target.price_to_earnings is None
    assert result.target.ev_to_ebitda is None
    assert result.target.free_cash_flow_yield is None
    assert result.peers == []
    assert "AAPL: enterprise value requires total debt and cash." in result.warnings
    assert "SAP: currency EUR is not compatible with target currency USD." in result.warnings


def test_evaluate_comparables_warns_for_non_positive_ev_and_keeps_negative_fcf_yield():
    target = make_company_input(
        symbol="CASH",
        security_id="NETCASH",
        name="Cash Rich Co.",
        market_cap=100.0,
        total_debt=10.0,
        cash=200.0,
        revenue=50.0,
        ebitda=10.0,
        net_income=5.0,
        free_cash_flow=-2.0,
        dataset_version_ids=("dataset",),
        provenance={},
        units={"market_cap": "USD", "total_debt": "USD", "cash": "USD"},
        input_dataset_versions={},
    )

    result = evaluate_comparables(target, [], calculated_at="2026-08-16T12:00:00Z")

    assert result.target.enterprise_value == -90.0
    assert result.target.ev_to_revenue is None
    assert result.target.ev_to_ebitda is None
    assert result.target.free_cash_flow_yield == -0.02
    assert "CASH: enterprise value is not positive." in result.warnings
