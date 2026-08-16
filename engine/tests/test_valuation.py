"""Tests for comparable-company Valuations."""

from __future__ import annotations

from market_research_lab.valuation import ComparableCompanyInput, evaluate_comparables


def test_evaluate_comparables_calculates_supported_multiples_and_peer_medians() -> None:
    target = ComparableCompanyInput(
        security_id="AAPL",
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        market_cap=300.0,
        total_debt=50.0,
        cash=20.0,
        revenue=100.0,
        ebitda=25.0,
        net_income=10.0,
        free_cash_flow=15.0,
        dataset_version_ids=("bars-aapl", "fundamentals-aapl"),
        provenance={"market_cap": "bars-aapl"},
        units={"market_cap": "USD"},
    )
    peer = ComparableCompanyInput(
        security_id="MSFT",
        symbol="MSFT",
        name="Microsoft Corp.",
        currency="USD",
        market_cap=600.0,
        total_debt=100.0,
        cash=50.0,
        revenue=200.0,
        ebitda=50.0,
        net_income=20.0,
        free_cash_flow=30.0,
        dataset_version_ids=("bars-msft", "fundamentals-msft"),
        provenance={"market_cap": "bars-msft"},
        units={"market_cap": "USD"},
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


def test_evaluate_comparables_warns_for_missing_or_incompatible_inputs() -> None:
    target = ComparableCompanyInput(
        security_id="AAPL",
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
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
    )
    peer = ComparableCompanyInput(
        security_id="SAP",
        symbol="SAP",
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
    )

    result = evaluate_comparables(target, [peer], calculated_at="2026-08-16T12:00:00Z")

    assert result.target.enterprise_value is None
    assert result.target.price_to_earnings is None
    assert result.target.ev_to_ebitda is None
    assert result.target.free_cash_flow_yield is None
    assert result.peers == []
    assert "AAPL: enterprise value requires total debt and cash." in result.warnings
    assert "SAP: currency EUR is not compatible with target currency USD." in result.warnings
