"""Pure Black-Scholes calculations for Option Contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OptionPricingInputs:
    spot: float
    strike: float
    years: float
    rate: float = 0.0
    dividend: float = 0.0
    right: Literal["put", "call"] = "put"


@dataclass(frozen=True)
class OptionGreeks:
    delta: float
    theta: float
    gamma: float
    vega: float
    implied_volatility: float


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def black_scholes_price(inputs: OptionPricingInputs, volatility: float) -> float:
    """Calculate one European option price."""
    if (
        not all(
            math.isfinite(value)
            for value in (
                inputs.spot,
                inputs.strike,
                inputs.years,
                inputs.rate,
                inputs.dividend,
                volatility,
            )
        )
        or inputs.spot <= 0.0
        or inputs.strike <= 0.0
        or inputs.years < 0.0
        or inputs.right not in ("put", "call")
    ):
        return 0.0
    if inputs.years <= 0.0:
        return max(
            0.0,
            inputs.spot - inputs.strike if inputs.right == "call" else inputs.strike - inputs.spot,
        )
    discount = math.exp(-inputs.rate * inputs.years)
    carry = math.exp(-inputs.dividend * inputs.years)
    if volatility <= 0.0 or inputs.spot <= 0.0 or inputs.strike <= 0.0:
        deterministic_value = inputs.spot * carry - inputs.strike * discount
        return max(
            0.0,
            deterministic_value if inputs.right == "call" else -deterministic_value,
        )

    root = volatility * math.sqrt(inputs.years)
    d1 = (
        math.log(inputs.spot / inputs.strike)
        + (inputs.rate - inputs.dividend + 0.5 * volatility * volatility) * inputs.years
    ) / root
    d2 = d1 - root
    if inputs.right == "call":
        return inputs.spot * carry * _normal_cdf(d1) - inputs.strike * discount * _normal_cdf(d2)
    return inputs.strike * discount * _normal_cdf(-d2) - inputs.spot * carry * _normal_cdf(-d1)


def black_scholes_iv(option_price: float, inputs: OptionPricingInputs) -> float:
    """Solve European Black-Scholes implied volatility by bisection."""
    if (
        not math.isfinite(option_price)
        or option_price <= 0.0
        or not all(
            math.isfinite(value)
            for value in (inputs.spot, inputs.strike, inputs.years, inputs.rate, inputs.dividend)
        )
        or inputs.spot <= 0.0
        or inputs.strike <= 0.0
        or inputs.years <= 0.0
        or inputs.right not in ("put", "call")
    ):
        return 0.0
    low, high = 1e-6, 5.0
    low_price = black_scholes_price(inputs, low)
    high_price = black_scholes_price(inputs, high)
    if option_price < low_price - 1e-8 or option_price > high_price + 1e-8:
        return 0.0
    for _ in range(80):
        middle = (low + high) / 2.0
        if black_scholes_price(inputs, middle) < option_price:
            low = middle
        else:
            high = middle
    return round((low + high) / 2.0, 10)


def black_scholes_greeks(inputs: OptionPricingInputs, volatility: float) -> OptionGreeks:
    """Calculate local European Black-Scholes Greeks."""
    if (
        not all(
            math.isfinite(value)
            for value in (
                inputs.spot,
                inputs.strike,
                inputs.years,
                inputs.rate,
                inputs.dividend,
                volatility,
            )
        )
        or min(inputs.spot, inputs.strike, inputs.years, volatility) <= 0.0
        or inputs.right not in ("put", "call")
    ):
        safe_volatility = volatility if math.isfinite(volatility) else 0.0
        return OptionGreeks(0.0, 0.0, 0.0, 0.0, max(safe_volatility, 0.0))
    root = volatility * math.sqrt(inputs.years)
    d1 = (
        math.log(inputs.spot / inputs.strike)
        + (inputs.rate - inputs.dividend + 0.5 * volatility**2) * inputs.years
    ) / root
    d2 = d1 - root
    discount = math.exp(-inputs.rate * inputs.years)
    carry = math.exp(-inputs.dividend * inputs.years)
    gamma = carry * _normal_pdf(d1) / (inputs.spot * root)
    vega = inputs.spot * carry * _normal_pdf(d1) * math.sqrt(inputs.years) / 100.0
    if inputs.right == "call":
        delta = carry * _normal_cdf(d1)
        theta = (
            -inputs.spot * carry * _normal_pdf(d1) * volatility / (2.0 * math.sqrt(inputs.years))
            - inputs.rate * inputs.strike * discount * _normal_cdf(d2)
            + inputs.dividend * inputs.spot * carry * _normal_cdf(d1)
        ) / 365.0
    else:
        delta = carry * (_normal_cdf(d1) - 1.0)
        theta = (
            -inputs.spot * carry * _normal_pdf(d1) * volatility / (2.0 * math.sqrt(inputs.years))
            + inputs.rate * inputs.strike * discount * _normal_cdf(-d2)
            - inputs.dividend * inputs.spot * carry * _normal_cdf(-d1)
        ) / 365.0
    return OptionGreeks(
        delta=round(delta, 8),
        theta=round(theta, 8),
        gamma=round(gamma, 8),
        vega=round(vega, 8),
        implied_volatility=round(volatility, 8),
    )


black_scholes_implied_volatility = black_scholes_iv
calculate_option_greeks = black_scholes_greeks
