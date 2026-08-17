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


def test_evaluate_fcff_dcf_calculates_forecasts_ev_equity_and_per_share_value():
    from market_research_lab.valuation import FCFFDCFInput, evaluate_fcff_dcf

    dcf_input = FCFFDCFInput(
        security_id="AAPL",
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        base_revenue=400.0,
        revenue_growth_rate=0.08,
        operating_margin=0.30,
        tax_rate=0.20,
        reinvestment_rate=0.25,
        wacc=0.09,
        terminal_growth_rate=0.025,
        shares_outstanding=15.0,
        total_debt=100.0,
        cash=50.0,
        forecast_years=5,
        dataset_version_ids=("bars-aapl", "fundamentals-aapl"),
        provenance={"revenue": "fundamentals-aapl"},
        units={"revenue": "USD"},
    )

    result = evaluate_fcff_dcf(dcf_input, calculated_at="2026-08-16T12:00:00Z")

    assert result.symbol == "AAPL"
    assert result.forecast_years == 5
    assert len(result.forecast_cash_flows) == 5

    # Check Year 1 cash flow arithmetic
    # Rev 1 = 400 * 1.08 = 432
    # EBIT 1 = 432 * 0.30 = 129.6
    # Tax 1 = 129.6 * 0.20 = 25.92
    # NOPAT 1 = 129.6 - 25.92 = 103.68
    # Reinvest 1 = 103.68 * 0.25 = 25.92
    # FCFF 1 = 103.68 - 25.92 = 77.76
    # DF 1 = 1 / 1.09 = 0.917431
    # PV 1 = 77.76 * 0.917431 = 71.33945
    y1 = result.forecast_cash_flows[0]
    assert round(y1.revenue, 2) == 432.0
    assert round(y1.operating_income, 2) == 129.6
    assert round(y1.nopat, 2) == 103.68
    assert round(y1.free_cash_flow, 2) == 77.76
    assert round(y1.present_value, 2) == 71.34

    assert result.terminal_value is not None
    assert result.enterprise_value is not None
    assert result.equity_value is not None
    assert result.value_per_share is not None
    assert result.value_per_share > 0

    # Equity value = EV + cash - debt
    assert round(result.equity_value, 2) == round(result.enterprise_value + 50.0 - 100.0, 2)
    assert round(result.value_per_share, 2) == round(result.equity_value / 15.0, 2)
    assert result.terminal_value_contribution is not None
    assert 0 < result.terminal_value_contribution < 1.0
    assert result.dataset_version_ids == ["bars-aapl", "fundamentals-aapl"]


def test_evaluate_fcff_dcf_scenarios_and_sensitivity():
    from market_research_lab.valuation import FCFFDCFInput, evaluate_fcff_dcf

    dcf_input = FCFFDCFInput(
        security_id="MSFT",
        symbol="MSFT",
        name="Microsoft Corp.",
        currency="USD",
        base_revenue=200.0,
        revenue_growth_rate=0.10,
        operating_margin=0.40,
        tax_rate=0.20,
        reinvestment_rate=0.20,
        wacc=0.085,
        terminal_growth_rate=0.025,
        shares_outstanding=7.5,
        total_debt=50.0,
        cash=60.0,
        forecast_years=5,
    )

    result = evaluate_fcff_dcf(dcf_input, calculated_at="2026-08-16T12:00:00Z")

    assert len(result.scenarios) == 3
    names = [s.name for s in result.scenarios]
    assert names == ["Bear", "Base", "Bull"]

    bear = result.scenarios[0]
    base = result.scenarios[1]
    bull = result.scenarios[2]

    assert bear.value_per_share is not None
    assert base.value_per_share is not None
    assert bull.value_per_share is not None

    # Bull value should exceed Base which exceeds Bear
    assert bull.value_per_share > base.value_per_share > bear.value_per_share

    # Check Sensitivity Matrix structure
    assert len(result.sensitivity.wacc_values) == 5
    assert len(result.sensitivity.terminal_growth_values) == 5
    assert len(result.sensitivity.grid) == 5
    for row in result.sensitivity.grid:
        assert len(row) == 5


def test_evaluate_fcff_dcf_warns_for_invalid_inputs_and_growth_exceeding_wacc():
    from market_research_lab.valuation import FCFFDCFInput, evaluate_fcff_dcf

    dcf_input = FCFFDCFInput(
        security_id="BAD",
        symbol="BAD",
        name="Bad Parameters Co.",
        currency="USD",
        base_revenue=-100.0,
        revenue_growth_rate=0.05,
        operating_margin=0.20,
        tax_rate=0.20,
        reinvestment_rate=0.20,
        wacc=0.02,
        terminal_growth_rate=0.03,  # terminal growth > WACC
        shares_outstanding=-10.0,
        total_debt=100.0,
        cash=0.0,
        input_warnings=("Initial data warning.",),
    )

    result = evaluate_fcff_dcf(dcf_input, calculated_at="2026-08-16T12:00:00Z")

    assert result.terminal_value is None
    assert result.enterprise_value is None
    assert result.equity_value is None
    assert result.value_per_share is None

    assert "Initial data warning." in result.warnings
    assert "BAD: base revenue is non-positive (-100.0)." in result.warnings
    assert "BAD: shares outstanding must be positive (-10.0)." in result.warnings
    assert "BAD: WACC (2.0%) must exceed terminal growth rate (3.0%)." in result.warnings


def test_valuation_html_report_and_csv_generation():
    from market_research_lab.valuation import (
        FCFFDCFInput,
        evaluate_fcff_dcf,
        generate_valuation_csv,
        generate_valuation_html_report,
    )

    dcf_input = FCFFDCFInput(
        security_id="AAPL",
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        base_revenue=400.0,
        revenue_growth_rate=0.08,
        operating_margin=0.30,
        tax_rate=0.20,
        reinvestment_rate=0.25,
        wacc=0.09,
        terminal_growth_rate=0.025,
        shares_outstanding=15.0,
        total_debt=100.0,
        cash=50.0,
        dataset_version_ids=("bars-aapl",),
    )

    res = evaluate_fcff_dcf(dcf_input, calculated_at="2026-08-16T12:00:00Z")
    res_dict = {
        "security_id": res.security_id,
        "symbol": res.symbol,
        "name": res.name,
        "currency": res.currency,
        "forecast_years": res.forecast_years,
        "forecast_cash_flows": [
            {
                "year": cf.year,
                "revenue": cf.revenue,
                "revenue_growth": cf.revenue_growth,
                "operating_income": cf.operating_income,
                "tax": cf.tax,
                "nopat": cf.nopat,
                "reinvestment": cf.reinvestment,
                "free_cash_flow": cf.free_cash_flow,
                "discount_factor": cf.discount_factor,
                "present_value": cf.present_value,
            }
            for cf in res.forecast_cash_flows
        ],
        "terminal_value": res.terminal_value,
        "terminal_value_contribution": res.terminal_value_contribution,
        "enterprise_value": res.enterprise_value,
        "equity_value": res.equity_value,
        "value_per_share": res.value_per_share,
        "scenarios": [
            {
                "name": sc.name,
                "wacc": sc.wacc,
                "terminal_growth_rate": sc.terminal_growth_rate,
                "revenue_growth_rate": sc.revenue_growth_rate,
                "operating_margin": sc.operating_margin,
                "value_per_share": sc.value_per_share,
            }
            for sc in res.scenarios
        ],
        "warnings": res.warnings,
        "dataset_version_ids": res.dataset_version_ids,
        "calculated_at": res.calculated_at,
        "method_revision": "fcff_dcf:v1",
        "run_id": "test-run-123",
    }

    manifest = {"id": "test-run-123"}
    html_report = generate_valuation_html_report(res_dict, manifest)
    assert "<!DOCTYPE html>" in html_report
    assert "Valuation Report: AAPL — Apple Inc." in html_report
    assert "fcff_dcf:v1" in html_report
    assert "Forecast Cash Flows" in html_report

    csv_data = generate_valuation_csv(res_dict)
    assert "Value Per Share" in csv_data
    assert "Forecast Year,Revenue,Growth" in csv_data
