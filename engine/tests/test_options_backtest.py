import pytest

from market_research_lab.market_data import (
    OptionContract,
    OptionMarketData,
    OptionTrade,
    StockMinuteBar,
)
from market_research_lab.option_backtest import (
    OptionPricingInputs,
    OptionsBacktestSpecification,
    black_scholes_greeks,
    black_scholes_iv,
    run_option_backtest,
)


def _data(prices: list[tuple[float, float]], *, delayed_trade: bool = False) -> OptionMarketData:
    short = OptionContract(
        "short", "SPY", "2024-02-20", 95.0, "put", available_at="2024-01-02T14:00:00Z"
    )
    long = OptionContract(
        "long", "SPY", "2024-02-20", 90.0, "put", available_at="2024-01-02T14:00:00Z"
    )
    stocks = []
    trades = []
    for index, (short_price, long_price) in enumerate(prices):
        timestamp = f"2024-01-02T15:{index:02d}:00Z"
        stock_available_at = f"2024-01-02T15:{index + 1:02d}:00Z"
        trade_available_at = (
            "2024-01-02T16:00:00Z" if delayed_trade and index == 1 else stock_available_at
        )
        stocks.append(
            StockMinuteBar("SPY", timestamp, 100.0, 101.0, 99.0, 100.0, 1000.0, stock_available_at)
        )
        trades.extend(
            [
                OptionTrade("short", timestamp, short_price, 100.0, trade_available_at),
                OptionTrade("long", timestamp, long_price, 100.0, trade_available_at),
            ]
        )
    return OptionMarketData(
        contracts=[short, long],
        trades=trades,
        stock_bars=stocks,
        dataset_version_id="options-v1",
    )


def _spec() -> OptionsBacktestSpecification:
    return OptionsBacktestSpecification(
        dataset_version_id="options-v1",
        start_date="2024-01-02",
        end_date="2024-01-02",
        symbols=("SPY",),
        automatic_selection=False,
        fixed_short_contract_id="short",
        fixed_long_contract_id="long",
    )


def test_black_scholes_iv_and_greeks_are_local_and_typed():
    pricing = OptionPricingInputs(100.0, 100.0, 30 / 365)
    iv = black_scholes_iv(2.287, pricing)
    greeks = black_scholes_greeks(pricing, iv)

    assert iv == pytest.approx(0.2, abs=0.01)
    assert greeks.delta < 0
    assert greeks.gamma > 0
    assert greeks.vega > 0


def test_worst_and_best_paths_use_the_completed_trade_range():
    data = _data([(2.0, 0.5), (4.0, 1.0), (4.0, 1.0)])
    first_minute = data.trades[0].timestamp
    available = data.trades[0].available_at
    data = OptionMarketData(
        contracts=data.contracts,
        trades=[
            *data.trades,
            OptionTrade("short", first_minute, 2.2, 100.0, available),
            OptionTrade("long", first_minute, 0.8, 100.0, available),
        ],
        stock_bars=data.stock_bars,
        dataset_version_id="options-v1",
    )
    result = run_option_backtest(_spec(), market_data=data)
    position = result.positions[0]

    assert result.worst_net_pnl < result.best_net_pnl
    assert position.margin_required == pytest.approx(position.width * 100 * position.quantity)
    assert position.full_possible_loss == pytest.approx(
        position.margin_required - position.entry_credit
    )
    assert position.close_rule == "Stop Level"
    assert position.exit_fee == pytest.approx(1.30 * position.quantity)


def test_stop_ladder_records_each_reached_movement_and_no_reentry_after_stop():
    prices = [(2.0, 0.5), (1.6, 1.0), (1.3, 1.0), (1.1, 1.0), (4.0, 1.0), (4.0, 1.0)]
    result = run_option_backtest(_spec(), market_data=_data(prices))
    movements = result.positions[0].stop_movements

    assert [movement.trigger_rule for movement in movements] == [
        "50% profit stop move",
        "75% profit stop move",
        "87.5% profit stop move",
    ]
    assert result.summary.rejection_counts.get("same_day_stop_cooldown", 0) >= 1


def test_future_eligible_trade_is_not_used_for_an_earlier_minute():
    result = run_option_backtest(
        _spec(), market_data=_data([(2.0, 0.5), (4.0, 1.0), (4.0, 1.0)], delayed_trade=True)
    )

    assert result.positions[0].close_timestamp is None
    assert result.positions[0].missing_minutes_count > 0


def test_same_minute_without_both_legs_cannot_open():
    data = _data([(2.0, 0.5)])
    data = OptionMarketData(
        contracts=data.contracts,
        trades=data.trades[:1],
        stock_bars=data.stock_bars,
        dataset_version_id="options-v1",
    )
    result = run_option_backtest(_spec(), market_data=data)

    assert result.positions == ()
    assert result.summary.total_trades == 0
