"""Pure, reproducible valuation calculations."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Callable


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
        if company.free_cash_flow is not None and company.market_cap is not None
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


ValuationMethod = Callable[..., ComparableValuationResult]
VALUATION_METHODS: dict[str, ValuationMethod] = {
    "trading_comparables": evaluate_comparables,
}


def evaluate(
    method: str,
    target: ComparableCompanyInput,
    peers: list[ComparableCompanyInput],
    *,
    calculated_at: str,
) -> ComparableValuationResult:
    """Evaluate a named Valuation method through the domain registry."""
    evaluator = VALUATION_METHODS.get(method)
    if evaluator is None:
        raise ValueError(f"Unknown Valuation method '{method}'.")
    return evaluator(target, peers, calculated_at=calculated_at)
