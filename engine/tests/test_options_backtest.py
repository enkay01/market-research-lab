import pytest

from market_research_lab.market_data import (
    OptionContract,
    OptionMarketData,
    OptionTrade,
    UnderlyingMinuteBar,
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
            UnderlyingMinuteBar(
                "SPY", timestamp, 100.0, 101.0, 99.0, 100.0, 1000.0, stock_available_at
            )
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
        underlying_bars=stocks,
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
        underlying_bars=data.underlying_bars,
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
        underlying_bars=data.underlying_bars,
        dataset_version_id="options-v1",
    )
    result = run_option_backtest(_spec(), market_data=data)

    assert result.positions == ()
    assert result.summary.total_trades == 0


def test_trajectory_points_include_underlying_price_and_delta():
    data = _data([(2.0, 0.5), (1.5, 0.5)])
    result = run_option_backtest(_spec(), market_data=data)
    position = result.positions[0]

    assert len(position.trajectory_points) >= 1
    point = position.trajectory_points[0]
    assert point.underlying_price == pytest.approx(100.0)
    assert point.stock_price == pytest.approx(100.0)
    assert point.delta < 0.0


def test_mid_greeks_sampled_at_trajectory_midpoint():
    prices = [(2.0, 0.5), (1.8, 0.5), (1.6, 0.5), (1.4, 0.5), (1.2, 0.5)]
    result = run_option_backtest(_spec(), market_data=_data(prices))
    position = result.positions[0]

    assert position.greeks["entry"] is not None
    assert position.greeks["mid"] is not None
    assert position.greeks["exit"] is not None
    assert len(position.trajectory_points) >= 3


def test_contiguous_missing_minute_gap_emits_reliability_warning():
    short = OptionContract(
        "short", "SPY", "2024-02-20", 95.0, "put", available_at="2024-01-02T14:00:00Z"
    )
    long = OptionContract(
        "long", "SPY", "2024-02-20", 90.0, "put", available_at="2024-01-02T14:00:00Z"
    )
    bars = []
    trades = []
    # Entry at 15:00
    timestamp_entry = "2024-01-02T15:00:00Z"
    avail_entry = "2024-01-02T15:01:00Z"
    bars.append(
        UnderlyingMinuteBar("SPY", timestamp_entry, 100.0, 101.0, 99.0, 100.0, 1000.0, avail_entry)
    )
    trades.extend([
        OptionTrade("short", timestamp_entry, 2.0, 100.0, avail_entry),
        OptionTrade("long", timestamp_entry, 0.5, 100.0, avail_entry),
    ])
    # 7 minutes of underlying bars with no option trades (gap > 5)
    for i in range(1, 8):
        ts = f"2024-01-02T15:{i:02d}:00Z"
        av = f"2024-01-02T15:{i + 1:02d}:00Z"
        bars.append(UnderlyingMinuteBar("SPY", ts, 100.0, 101.0, 99.0, 100.0, 1000.0, av))
    # Exit at 15:08
    ts_exit = "2024-01-02T15:08:00Z"
    av_exit = "2024-01-02T15:09:00Z"
    bars.append(UnderlyingMinuteBar("SPY", ts_exit, 100.0, 101.0, 99.0, 100.0, 1000.0, av_exit))
    trades.extend([
        OptionTrade("short", ts_exit, 4.0, 100.0, av_exit),
        OptionTrade("long", ts_exit, 1.0, 100.0, av_exit),
    ])
    data = OptionMarketData(
        contracts=[short, long],
        trades=trades,
        underlying_bars=bars,
        dataset_version_id="options-v1",
    )
    result = run_option_backtest(_spec(), market_data=data)
    assert any("contiguous missing" in warning for warning in result.warnings)
    assert result.positions[0].max_missing_gap >= 7


def test_counterfactual_whipsaw_prioritized_with_correct_multiplier_scaling():
    # Stop triggers at minute 1 (spread 3.0), then spread drops to 0.5 (profitable recovery)
    prices = [(2.0, 0.5), (4.0, 1.0), (4.0, 1.0), (1.0, 0.5)]
    result = run_option_backtest(_spec(), market_data=_data(prices))
    position = result.positions[0]

    assert position.counterfactual is not None
    assert position.counterfactual.outcome == "WHIPSAWED"
    assert position.counterfactual.avoided_loss_or_missed_gain > 0.0


def test_friction_drag_attribution_preserved():
    data = _data([(2.0, 0.5), (1.5, 0.5)])
    result = run_option_backtest(_spec(), market_data=data)
    position = result.positions[0]

    assert position.bid_ask_spread_drag > 0.0
