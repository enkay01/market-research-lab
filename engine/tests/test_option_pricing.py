import pytest

from market_research_lab.option_pricing import (
    OptionPricingInputs,
    black_scholes_greeks,
    black_scholes_iv,
    black_scholes_price,
)


def test_black_scholes_price_matches_known_call_and_put_values():
    call = OptionPricingInputs(100.0, 100.0, 1.0, rate=0.05, right="call")
    put = OptionPricingInputs(100.0, 100.0, 1.0, rate=0.05, right="put")

    assert black_scholes_price(call, 0.2) == pytest.approx(10.45058357)
    assert black_scholes_price(put, 0.2) == pytest.approx(5.57352602)


def test_implied_volatility_recovers_known_input():
    inputs = OptionPricingInputs(100.0, 95.0, 45 / 365, rate=0.03)
    price = black_scholes_price(inputs, 0.35)

    assert black_scholes_iv(price, inputs) == pytest.approx(0.35, abs=1e-8)


def test_greeks_match_known_at_the_money_call_values():
    inputs = OptionPricingInputs(100.0, 100.0, 1.0, rate=0.05, right="call")

    greeks = black_scholes_greeks(inputs, 0.2)

    assert greeks.delta == pytest.approx(0.63683065)
    assert greeks.gamma == pytest.approx(0.01876202)
    assert greeks.vega == pytest.approx(0.37524035)


def test_price_uses_intrinsic_value_at_expiration():
    expired_put = OptionPricingInputs(90.0, 100.0, 0.0)
    expired_call = OptionPricingInputs(110.0, 100.0, 0.0, right="call")

    assert black_scholes_price(expired_put, 0.2) == 10.0
    assert black_scholes_price(expired_call, 0.2) == 10.0


def test_invalid_inputs_have_zero_iv_and_greeks():
    inputs = OptionPricingInputs(0.0, 100.0, 1.0)

    assert black_scholes_iv(1.0, inputs) == 0.0
    assert black_scholes_greeks(inputs, 0.2).delta == 0.0


def test_non_finite_inputs_do_not_produce_non_finite_outputs():
    inputs = OptionPricingInputs(float("nan"), 100.0, 1.0)

    assert black_scholes_price(inputs, 0.2) == 0.0
    assert black_scholes_iv(1.0, inputs) == 0.0
    assert black_scholes_greeks(inputs, float("nan")).implied_volatility == 0.0
