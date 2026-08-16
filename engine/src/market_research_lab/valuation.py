"""Pure, reproducible valuation calculations."""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Callable


@dataclass(frozen=True)
class ComparableCompanyInput:
    """Eligible market and fundamental inputs for one Security."""

    security_id: str
    symbol: str
    name: str
    currency: str
    market_cap: float | None
    total_debt: float | None
    cash: float | None
    revenue: float | None
    ebitda: float | None
    net_income: float | None
    free_cash_flow: float | None
    dataset_version_ids: tuple[str, ...]
    provenance: dict[str, str]
    units: dict[str, str]
    input_dataset_versions: dict[str, tuple[str, ...]]
    input_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparableCompanyResult:
    """One company row in a comparable-company Valuation."""

    security_id: str
    symbol: str
    name: str
    currency: str
    market_cap: float | None
    enterprise_value: float | None
    price_to_earnings: float | None
    ev_to_revenue: float | None
    ev_to_ebitda: float | None
    free_cash_flow_yield: float | None
    inputs: ComparableCompanyInput
    status: str = "ok"
    has_valuation: bool = True


@dataclass(frozen=True)
class ComparableValuationResult:
    """Comparable-company Valuation with complete input provenance."""

    target: ComparableCompanyResult
    peers: list[ComparableCompanyResult]
    peer_medians: ComparableCompanyResult
    warnings: list[str]
    dataset_version_ids: list[str]
    calculated_at: str
    method_revision: str | None = None
    run_id: str | None = None


# ---------------------------------------------------------------------------
# FCFF DCF Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FCFFDCFInput:
    """Forecast and balance-sheet assumptions for an FCFF DCF Valuation."""

    security_id: str
    symbol: str
    name: str
    currency: str
    base_revenue: float
    revenue_growth_rate: float
    operating_margin: float
    tax_rate: float
    reinvestment_rate: float
    wacc: float
    terminal_growth_rate: float
    shares_outstanding: float
    total_debt: float = 0.0
    cash: float = 0.0
    forecast_years: int = 5
    revenue_growth_rates: tuple[float, ...] = ()
    operating_margins: tuple[float, ...] = ()
    reinvestment_rates: tuple[float, ...] = ()
    dataset_version_ids: tuple[str, ...] = ()
    provenance: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    input_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CashFlowForecastYear:
    """One forecast year in an FCFF DCF projection."""

    year: int
    revenue: float
    revenue_growth: float
    operating_income: float
    tax: float
    nopat: float
    reinvestment: float
    free_cash_flow: float
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class ScenarioResult:
    """Valuation outcome under one scenario (Bear, Base, Bull)."""

    name: str
    wacc: float
    terminal_growth_rate: float
    revenue_growth_rate: float
    operating_margin: float
    enterprise_value: float | None
    equity_value: float | None
    value_per_share: float | None


@dataclass(frozen=True)
class SensitivityMatrix:
    """Valuation per share across a grid of WACC and terminal growth rates."""

    wacc_values: tuple[float, ...]
    terminal_growth_values: tuple[float, ...]
    grid: tuple[tuple[float | None, ...], ...]


@dataclass(frozen=True)
class FCFFDCFResult:
    """Complete Free Cash Flow to Firm DCF Valuation result."""

    security_id: str
    symbol: str
    name: str
    currency: str
    forecast_years: int
    forecast_cash_flows: list[CashFlowForecastYear]
    terminal_cash_flow: float | None
    terminal_value: float | None
    pv_terminal_value: float | None
    terminal_value_contribution: float | None
    enterprise_value: float | None
    cash: float
    total_debt: float
    equity_value: float | None
    shares_outstanding: float
    value_per_share: float | None
    scenarios: list[ScenarioResult]
    sensitivity: SensitivityMatrix
    warnings: list[str]
    dataset_version_ids: list[str]
    calculated_at: str
    inputs: FCFFDCFInput
    method_revision: str | None = None
    run_id: str | None = None


# ---------------------------------------------------------------------------
# Valuation Pure Functions
# ---------------------------------------------------------------------------


def _positive_multiple(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or numerator <= 0 or denominator <= 0:
        return None
    return numerator / denominator


def _company_result(
    company: ComparableCompanyInput, warnings: list[str]
) -> ComparableCompanyResult:
    warnings.extend(company.input_warnings)
    enterprise_value: float | None = None
    if company.market_cap is None:
        warnings.append(f"{company.symbol}: market capitalization is unavailable.")
    elif company.total_debt is None or company.cash is None:
        warnings.append(f"{company.symbol}: enterprise value requires total debt and cash.")
    else:
        enterprise_value = company.market_cap + company.total_debt - company.cash
        if enterprise_value <= 0:
            warnings.append(f"{company.symbol}: enterprise value is not positive.")

    price_to_earnings = _positive_multiple(company.market_cap, company.net_income)
    if company.market_cap is None:
        warnings.append(f"{company.symbol}: P/E requires market capitalization.")
    elif company.net_income is None or company.net_income <= 0:
        warnings.append(f"{company.symbol}: P/E requires positive net income.")

    ev_to_revenue = _positive_multiple(enterprise_value, company.revenue)
    if enterprise_value is None:
        warnings.append(f"{company.symbol}: EV/revenue requires enterprise value.")
    elif company.revenue is None or company.revenue <= 0:
        warnings.append(f"{company.symbol}: EV/revenue requires positive revenue.")

    ev_to_ebitda = _positive_multiple(enterprise_value, company.ebitda)
    if enterprise_value is None:
        warnings.append(f"{company.symbol}: EV/EBITDA requires enterprise value.")
    elif company.ebitda is None or company.ebitda <= 0:
        warnings.append(f"{company.symbol}: EV/EBITDA requires positive EBITDA.")

    free_cash_flow_yield = (
        company.free_cash_flow / company.market_cap
        if company.free_cash_flow is not None
        and company.market_cap is not None
        and company.market_cap > 0
        else None
    )
    if company.market_cap is None:
        warnings.append(f"{company.symbol}: free-cash-flow yield requires market capitalization.")
    elif company.free_cash_flow is None:
        warnings.append(f"{company.symbol}: free-cash-flow yield requires free cash flow.")

    return ComparableCompanyResult(
        security_id=company.security_id,
        symbol=company.symbol,
        name=company.name,
        currency=company.currency,
        market_cap=company.market_cap,
        enterprise_value=enterprise_value,
        price_to_earnings=price_to_earnings,
        ev_to_revenue=ev_to_revenue,
        ev_to_ebitda=ev_to_ebitda,
        free_cash_flow_yield=free_cash_flow_yield,
        inputs=company,
    )


def _median(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return median(present) if present else None


def evaluate_comparables(
    target: ComparableCompanyInput,
    peers: list[ComparableCompanyInput],
    *,
    calculated_at: str,
) -> ComparableValuationResult:
    """Calculate supported comparable-company multiples without currency conversion."""
    warnings: list[str] = []
    target_result = _company_result(target, warnings)
    compatible_peers: list[ComparableCompanyResult] = []
    for peer in peers:
        if peer.currency != target.currency:
            warnings.append(
                f"{peer.symbol}: currency {peer.currency} is not compatible with target "
                f"currency {target.currency}."
            )
            continue
        compatible_peers.append(_company_result(peer, warnings))

    peer_medians = ComparableCompanyResult(
        security_id="peer-median",
        symbol="Median",
        name="Peer median",
        currency=target.currency,
        market_cap=None,
        enterprise_value=None,
        price_to_earnings=_median([peer.price_to_earnings for peer in compatible_peers]),
        ev_to_revenue=_median([peer.ev_to_revenue for peer in compatible_peers]),
        ev_to_ebitda=_median([peer.ev_to_ebitda for peer in compatible_peers]),
        free_cash_flow_yield=_median([peer.free_cash_flow_yield for peer in compatible_peers]),
        inputs=ComparableCompanyInput(
            security_id="peer-median",
            symbol="Median",
            name="Peer median",
            currency=target.currency,
            market_cap=None,
            total_debt=None,
            cash=None,
            revenue=None,
            ebitda=None,
            net_income=None,
            free_cash_flow=None,
            dataset_version_ids=(),
            provenance={},
            units={},
            input_dataset_versions={},
        ),
    )
    dataset_version_ids = sorted(
        {
            dataset_version_id
            for company in [target, *peers]
            for dataset_version_id in company.dataset_version_ids
        }
    )
    return ComparableValuationResult(
        target=target_result,
        peers=compatible_peers,
        peer_medians=peer_medians,
        warnings=warnings,
        dataset_version_ids=dataset_version_ids,
        calculated_at=calculated_at,
    )


def _compute_dcf_values(
    base_revenue: float,
    growth_rate: float,
    operating_margin: float,
    tax_rate: float,
    reinvestment_rate: float,
    wacc: float,
    terminal_growth_rate: float,
    forecast_years: int,
    cash: float,
    total_debt: float,
    shares_outstanding: float,
) -> tuple[float | None, float | None, float | None]:
    """Helper calculating (EV, Equity Value, Value Per Share) for given parameters."""
    if wacc <= 0 or wacc <= terminal_growth_rate:
        return None, None, None

    pv_sum = 0.0
    current_revenue = base_revenue
    last_fcf = 0.0
    for year in range(1, forecast_years + 1):
        current_revenue *= 1.0 + growth_rate
        ebit = current_revenue * operating_margin
        tax = ebit * tax_rate
        nopat = ebit - tax
        reinvest = nopat * reinvestment_rate
        fcf = nopat - reinvest
        df = 1.0 / ((1.0 + wacc) ** year)
        pv_sum += fcf * df
        last_fcf = fcf

    terminal_fcf = last_fcf * (1.0 + terminal_growth_rate)
    terminal_value = terminal_fcf / (wacc - terminal_growth_rate)
    pv_terminal_value = terminal_value / ((1.0 + wacc) ** forecast_years)
    enterprise_value = pv_sum + pv_terminal_value
    equity_value = enterprise_value + cash - total_debt
    value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else None

    return enterprise_value, equity_value, value_per_share


def evaluate_fcff_dcf(
    inputs: FCFFDCFInput,
    *,
    calculated_at: str,
) -> FCFFDCFResult:
    """Calculate FCFF discounted cash flow valuation, scenarios, and sensitivity."""
    warnings: list[str] = list(inputs.input_warnings)

    if inputs.base_revenue <= 0:
        warnings.append(f"{inputs.symbol}: base revenue is non-positive ({inputs.base_revenue}).")
    if inputs.shares_outstanding <= 0:
        warnings.append(
            f"{inputs.symbol}: shares outstanding must be positive ({inputs.shares_outstanding})."
        )
    if inputs.wacc <= 0:
        warnings.append(f"{inputs.symbol}: WACC must be positive ({inputs.wacc:.1%}).")
    elif inputs.wacc <= inputs.terminal_growth_rate:
        warnings.append(
            f"{inputs.symbol}: WACC ({inputs.wacc:.1%}) must exceed terminal growth rate "
            f"({inputs.terminal_growth_rate:.1%})."
        )

    forecast_years = max(1, inputs.forecast_years)

    # Build year-by-year projections
    forecast_cash_flows: list[CashFlowForecastYear] = []
    current_revenue = inputs.base_revenue
    pv_fcff_sum = 0.0
    last_fcff = 0.0

    for year in range(1, forecast_years + 1):
        idx = year - 1
        growth = (
            inputs.revenue_growth_rates[idx]
            if idx < len(inputs.revenue_growth_rates)
            else inputs.revenue_growth_rate
        )
        margin = (
            inputs.operating_margins[idx]
            if idx < len(inputs.operating_margins)
            else inputs.operating_margin
        )
        reinvest_rate = (
            inputs.reinvestment_rates[idx]
            if idx < len(inputs.reinvestment_rates)
            else inputs.reinvestment_rate
        )

        current_revenue *= 1.0 + growth
        ebit = current_revenue * margin
        tax = ebit * inputs.tax_rate
        nopat = ebit - tax
        reinvestment = nopat * reinvest_rate
        fcff = nopat - reinvestment

        df = 1.0 / ((1.0 + inputs.wacc) ** year) if inputs.wacc > 0 else 0.0
        pv = fcff * df
        pv_fcff_sum += pv
        last_fcff = fcff

        forecast_cash_flows.append(
            CashFlowForecastYear(
                year=year,
                revenue=current_revenue,
                revenue_growth=growth,
                operating_income=ebit,
                tax=tax,
                nopat=nopat,
                reinvestment=reinvestment,
                free_cash_flow=fcff,
                discount_factor=df,
                present_value=pv,
            )
        )

    terminal_cash_flow: float | None = None
    terminal_value: float | None = None
    pv_terminal_value: float | None = None
    enterprise_value: float | None = None
    terminal_value_contribution: float | None = None
    equity_value: float | None = None
    value_per_share: float | None = None

    if inputs.wacc > 0 and inputs.wacc > inputs.terminal_growth_rate:
        terminal_cash_flow = last_fcff * (1.0 + inputs.terminal_growth_rate)
        terminal_value = terminal_cash_flow / (inputs.wacc - inputs.terminal_growth_rate)
        pv_terminal_value = terminal_value / ((1.0 + inputs.wacc) ** forecast_years)
        enterprise_value = pv_fcff_sum + pv_terminal_value
        if enterprise_value > 0:
            terminal_value_contribution = pv_terminal_value / enterprise_value
        equity_value = enterprise_value + inputs.cash - inputs.total_debt
        if equity_value < 0:
            warnings.append(
                f"{inputs.symbol}: calculated equity value is negative ({equity_value:.2f} {inputs.currency})."
            )
        if inputs.shares_outstanding > 0:
            value_per_share = equity_value / inputs.shares_outstanding

    # Calculate Scenarios (Bear, Base, Bull)
    scenarios: list[ScenarioResult] = []

    # Bear scenario
    bear_wacc = inputs.wacc + 0.01
    bear_g = max(0.0, inputs.terminal_growth_rate - 0.005)
    bear_rev_g = inputs.revenue_growth_rate - 0.02
    bear_margin = max(0.0, inputs.operating_margin - 0.03)
    bear_ev, bear_eq, bear_vps = _compute_dcf_values(
        inputs.base_revenue,
        bear_rev_g,
        bear_margin,
        inputs.tax_rate,
        inputs.reinvestment_rate,
        bear_wacc,
        bear_g,
        forecast_years,
        inputs.cash,
        inputs.total_debt,
        inputs.shares_outstanding,
    )
    scenarios.append(
        ScenarioResult(
            name="Bear",
            wacc=bear_wacc,
            terminal_growth_rate=bear_g,
            revenue_growth_rate=bear_rev_g,
            operating_margin=bear_margin,
            enterprise_value=bear_ev,
            equity_value=bear_eq,
            value_per_share=bear_vps,
        )
    )

    # Base scenario
    scenarios.append(
        ScenarioResult(
            name="Base",
            wacc=inputs.wacc,
            terminal_growth_rate=inputs.terminal_growth_rate,
            revenue_growth_rate=inputs.revenue_growth_rate,
            operating_margin=inputs.operating_margin,
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            value_per_share=value_per_share,
        )
    )

    # Bull scenario
    bull_wacc = max(0.02, inputs.wacc - 0.01)
    bull_g = inputs.terminal_growth_rate + 0.005
    bull_rev_g = inputs.revenue_growth_rate + 0.02
    bull_margin = inputs.operating_margin + 0.03
    bull_ev, bull_eq, bull_vps = _compute_dcf_values(
        inputs.base_revenue,
        bull_rev_g,
        bull_margin,
        inputs.tax_rate,
        inputs.reinvestment_rate,
        bull_wacc,
        bull_g,
        forecast_years,
        inputs.cash,
        inputs.total_debt,
        inputs.shares_outstanding,
    )
    scenarios.append(
        ScenarioResult(
            name="Bull",
            wacc=bull_wacc,
            terminal_growth_rate=bull_g,
            revenue_growth_rate=bull_rev_g,
            operating_margin=bull_margin,
            enterprise_value=bull_ev,
            equity_value=bull_eq,
            value_per_share=bull_vps,
        )
    )

    # Build Sensitivity Matrix (WACC vs Terminal Growth)
    wacc_steps = (
        round(inputs.wacc - 0.010, 4),
        round(inputs.wacc - 0.005, 4),
        round(inputs.wacc, 4),
        round(inputs.wacc + 0.005, 4),
        round(inputs.wacc + 0.010, 4),
    )
    growth_steps = (
        round(inputs.terminal_growth_rate - 0.010, 4),
        round(inputs.terminal_growth_rate - 0.005, 4),
        round(inputs.terminal_growth_rate, 4),
        round(inputs.terminal_growth_rate + 0.005, 4),
        round(inputs.terminal_growth_rate + 0.010, 4),
    )

    grid: list[tuple[float | None, ...]] = []
    for w in wacc_steps:
        row: list[float | None] = []
        for g in growth_steps:
            if w > g and w > 0:
                _, _, vps = _compute_dcf_values(
                    inputs.base_revenue,
                    inputs.revenue_growth_rate,
                    inputs.operating_margin,
                    inputs.tax_rate,
                    inputs.reinvestment_rate,
                    w,
                    g,
                    forecast_years,
                    inputs.cash,
                    inputs.total_debt,
                    inputs.shares_outstanding,
                )
                row.append(vps)
            else:
                row.append(None)
        grid.append(tuple(row))

    sensitivity = SensitivityMatrix(
        wacc_values=wacc_steps,
        terminal_growth_values=growth_steps,
        grid=tuple(grid),
    )

    dataset_version_ids = sorted(set(inputs.dataset_version_ids))

    return FCFFDCFResult(
        security_id=inputs.security_id,
        symbol=inputs.symbol,
        name=inputs.name,
        currency=inputs.currency,
        forecast_years=forecast_years,
        forecast_cash_flows=forecast_cash_flows,
        terminal_cash_flow=terminal_cash_flow,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        terminal_value_contribution=terminal_value_contribution,
        enterprise_value=enterprise_value,
        cash=inputs.cash,
        total_debt=inputs.total_debt,
        equity_value=equity_value,
        shares_outstanding=inputs.shares_outstanding,
        value_per_share=value_per_share,
        scenarios=scenarios,
        sensitivity=sensitivity,
        warnings=warnings,
        dataset_version_ids=dataset_version_ids,
        calculated_at=calculated_at,
        inputs=inputs,
    )


# ---------------------------------------------------------------------------
# Method Registry & Domain Evaluator
# ---------------------------------------------------------------------------

ValuationMethod = Callable[..., Any]
VALUATION_METHODS: dict[str, ValuationMethod] = {
    "trading_comparables": evaluate_comparables,
    "fcff_dcf": evaluate_fcff_dcf,
}


def evaluate(
    method: str,
    *args: Any,
    calculated_at: str,
    **kwargs: Any,
) -> Any:
    """Evaluate a named Valuation method through the domain registry."""
    evaluator = VALUATION_METHODS.get(method)
    if evaluator is None:
        raise ValueError(f"Unknown Valuation method '{method}'.")
    return evaluator(*args, calculated_at=calculated_at, **kwargs)


from .reporting import generate_valuation_csv, generate_valuation_html_report

__all__ = [
    "ComparableCompanyInput",
    "ComparableCompanyResult",
    "ComparableCompanyValuation",
    "FCFFDCFInput",
    "CashFlowForecastYear",
    "ScenarioResult",
    "SensitivityMatrix",
    "FCFFDCFResult",
    "ValuationMethod",
    "VALUATION_METHODS",
    "evaluate",
    "evaluate_comparable_companies",
    "evaluate_fcff_dcf",
    "generate_valuation_html_report",
    "generate_valuation_csv",
]

