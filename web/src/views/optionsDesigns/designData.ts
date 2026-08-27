export interface PriceCandle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StopRatchetEvent {
  timestamp: string;
  previous_stop: number;
  new_stop: number;
  trigger_rule: string;
  underlying_price: number;
}

export interface SpreadPositionDetail {
  id: string;
  security_id: string;
  spread_type: "Bull Put" | "Bear Call" | "Iron Condor";
  short_strike: number;
  long_strike: number;
  expiration: string;
  width: number;
  entry_credit: number;
  margin_required: number; // Max risk per share (Width - Credit)
  short_delta: number;
  implied_volatility: number;
  open_timestamp: string;
  open_rule: string;
  close_timestamp: string;
  close_rule: string;
  days_held: number;
  status: "Closed Profit Target" | "Closed Stop Level" | "Expired Worthless" | "Closed Early Risk";

  // Financial Return & Margin
  worst_net_pnl: number;
  best_net_pnl: number;
  return_on_margin_pct: number; // Net PnL / (Margin Required * 100)
  annualized_rom_pct: number;

  // Execution Friction Drag
  bid_ask_spread_drag: number; // Friction lost to bid-ask spread
  slippage_cost: number;
  execution_mode: "Multi-Leg Complex Ticket" | "Sequential Legging";

  // Greeks Progression
  greeks: {
    entry: { delta: number; theta: number; gamma: string; vega: number };
    mid: { delta: number; theta: number; gamma: string; vega: number };
    exit: { delta: number; theta: number; gamma: string; vega: number };
  };

  // Stop Ratchet History
  stop_movements: StopRatchetEvent[];

  // Post-Exit Counterfactual (Whipsaw Diagnostic)
  counterfactual: {
    outcome: "STOP_SAVED" | "WHIPSAW_SHAKEDOWN" | "NORMAL_PROFIT";
    value_at_expiration: number;
    difference_amount: number;
    explanation: string;
  };

  // Data Health & Gaps
  missing_minutes_count: number;
  gaps: { start: string; end: string; duration_minutes: number; reason: string }[];
  reliability_pct: number;

  // Underlying Stock Price Trajectory for Chart Overlay
  candles: PriceCandle[];
  trajectory_points: {
    minute: string;
    underlying: number;
    spread_worst: number;
    spread_best: number;
    stop_level: number;
    counterfactual_spread?: number;
  }[];
}

export interface BlockedSpreadCandidate {
  id: string;
  security_id: string;
  candidate_type: string;
  timestamp: string;
  rule_id: "EARNINGS_BLACKOUT" | "FINAL_SEVEN_DAY_RULE" | "PORTFOLIO_LIMIT" | "SIMILARITY_LIMIT";
  reason: string;
  details: string;
}

export interface OptionsPortfolioDataset {
  run_id: string;
  provider: "Alpaca";
  date_range: { start: string; end: string };
  strategy_name: string;
  strategy_revision: string;
  dataset_version: string;
  engine_source_fingerprint: string;

  // Pulse Strip Summary
  summary: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate_pct: number;
    worst_net_pnl: number;
    worst_return_pct: number;
    best_net_pnl: number;
    best_return_pct: number;
    total_margin_allocated: number;
    portfolio_rom_pct: number;
    max_drawdown_pct: number;
    sharpe_ratio: number;
    profit_factor: number;
    expectancy_per_trade: number;
    total_slippage_drag: number;
    total_bid_ask_friction: number;
    overall_reliability_pct: number;
    missing_matching_minutes: number;
    gaps_over_5_min: number;
  };

  // Stacked Time Series Curve Points
  equity_curve: { date: string; strategy_equity: number; benchmark_equity: number; drawdown_pct: number; margin_util_pct: number; open_positions_count: number }[];

  positions: SpreadPositionDetail[];
  blocked_candidates: BlockedSpreadCandidate[];
}

export const MOCK_OPTIONS_DATASET: OptionsPortfolioDataset = {
  run_id: "opt_run_20240826_alpaca_9f81a",
  provider: "Alpaca",
  date_range: { start: "2024-03-01", end: "2024-06-28" },
  strategy_name: "credit_spread_vol_ratchet",
  strategy_revision: "credit_spread_vol_ratchet:v2",
  dataset_version: "alpaca_options_chains_2024_q1_q2_v1",
  engine_source_fingerprint: "sha256:7f3b892ac19e81b6728045dd189cf0049e7b23d9a54e60124",

  summary: {
    total_trades: 14,
    winning_trades: 11,
    losing_trades: 3,
    win_rate_pct: 78.6,
    worst_net_pnl: -320.0,
    worst_return_pct: -0.32,
    best_net_pnl: 640.0,
    best_return_pct: 0.64,
    total_margin_allocated: 14800.0,
    portfolio_rom_pct: 18.4,
    max_drawdown_pct: -2.4,
    sharpe_ratio: 1.18,
    profit_factor: 1.84,
    expectancy_per_trade: 45.7,
    total_slippage_drag: 142.5,
    total_bid_ask_friction: 188.0,
    overall_reliability_pct: 99.4,
    missing_matching_minutes: 18,
    gaps_over_5_min: 2,
  },

  equity_curve: [
    { date: "2024-03-01", strategy_equity: 100000, benchmark_equity: 100000, drawdown_pct: 0.0, margin_util_pct: 12.5, open_positions_count: 1 },
    { date: "2024-03-15", strategy_equity: 100180, benchmark_equity: 100450, drawdown_pct: 0.0, margin_util_pct: 25.0, open_positions_count: 2 },
    { date: "2024-04-02", strategy_equity: 100340, benchmark_equity: 100800, drawdown_pct: -0.2, margin_util_pct: 38.5, open_positions_count: 3 },
    { date: "2024-04-18", strategy_equity: 100020, benchmark_equity: 99400, drawdown_pct: -2.4, margin_util_pct: 22.0, open_positions_count: 2 },
    { date: "2024-05-01", strategy_equity: 100420, benchmark_equity: 101200, drawdown_pct: -0.5, margin_util_pct: 30.0, open_positions_count: 2 },
    { date: "2024-05-20", strategy_equity: 100680, benchmark_equity: 102400, drawdown_pct: 0.0, margin_util_pct: 42.0, open_positions_count: 3 },
    { date: "2024-06-14", strategy_equity: 100850, benchmark_equity: 103800, drawdown_pct: 0.0, margin_util_pct: 28.0, open_positions_count: 2 },
    { date: "2024-06-28", strategy_equity: 101120, benchmark_equity: 104500, drawdown_pct: -0.3, margin_util_pct: 10.0, open_positions_count: 1 },
  ],

  positions: [
    {
      id: "pos_nvda_20240517_c920",
      security_id: "NVDA",
      spread_type: "Bear Call",
      short_strike: 920.0,
      long_strike: 930.0,
      expiration: "2024-05-17",
      width: 10.0,
      entry_credit: 2.85,
      margin_required: 7.15, // $715 per contract
      short_delta: 0.28,
      implied_volatility: 0.482,
      open_timestamp: "2024-04-02 09:45 ET",
      open_rule: "MOMENTUM_OVERBOUGHT_BEAR_CALL",
      close_timestamp: "2024-04-18 11:18 ET",
      close_rule: "STOP_LEVEL_BREACH_INTRADAY",
      days_held: 16,
      status: "Closed Stop Level",
      worst_net_pnl: -165.0,
      best_net_pnl: -75.0,
      return_on_margin_pct: -23.1,
      annualized_rom_pct: -526.0,
      bid_ask_spread_drag: 28.0,
      slippage_cost: 32.0,
      execution_mode: "Multi-Leg Complex Ticket",
      greeks: {
        entry: { delta: 0.28, theta: 4.8, gamma: "Moderate", vega: 18.2 },
        mid: { delta: 0.42, theta: 6.2, gamma: "Elevated", vega: 21.0 },
        exit: { delta: 0.74, theta: 2.1, gamma: "Critical (Pin)", vega: 14.5 },
      },
      stop_movements: [
        { timestamp: "2024-04-02 09:45 ET", previous_stop: 0, new_stop: 5.7, trigger_rule: "INITIAL_2X_CREDIT", underlying_price: 890.5 },
        { timestamp: "2024-04-10 14:15 ET", previous_stop: 5.7, new_stop: 4.2, trigger_rule: "TIME_DECAY_WEEK_2_TIGHTEN", underlying_price: 896.0 },
      ],
      counterfactual: {
        outcome: "STOP_SAVED",
        value_at_expiration: 10.0, // Max Loss $1,000
        difference_amount: 550.0,
        explanation: "Stop saved +$550 vs Max Loss. NVDA continued soaring to $948 by expiry; holding without stop would have lost -$715 max margin.",
      },
      missing_minutes_count: 7,
      gaps: [{ start: "2024-04-10 13:22 ET", end: "2024-04-10 13:29 ET", duration_minutes: 7, reason: "Alpaca feed quote latency spike (no NBBO updates for NVDA $920C)" }],
      reliability_pct: 94.2,
      candles: [
        { date: "04-02", open: 888.0, high: 894.0, low: 884.0, close: 890.5, volume: 4200000 },
        { date: "04-08", open: 889.0, high: 891.0, low: 881.0, close: 885.0, volume: 3800000 },
        { date: "04-12", open: 887.0, high: 905.0, low: 886.0, close: 902.0, volume: 5100000 },
        { date: "04-16", open: 904.0, high: 918.0, low: 901.0, close: 915.0, volume: 6200000 },
        { date: "04-18", open: 916.0, high: 932.0, low: 914.0, close: 928.0, volume: 7400000 },
        { date: "04-26", open: 930.0, high: 945.0, low: 928.0, close: 942.0, volume: 6900000 },
        { date: "05-17", open: 944.0, high: 955.0, low: 940.0, close: 948.0, volume: 8100000 },
      ],
      trajectory_points: [
        { minute: "04-02", underlying: 890.5, spread_worst: 2.85, spread_best: 2.85, stop_level: 5.7, counterfactual_spread: 2.85 },
        { minute: "04-08", underlying: 885.0, spread_worst: 2.48, spread_best: 2.32, stop_level: 5.7, counterfactual_spread: 2.4 },
        { minute: "04-12", underlying: 902.0, spread_worst: 3.45, spread_best: 2.95, stop_level: 4.2, counterfactual_spread: 3.2 },
        { minute: "04-16", underlying: 915.0, spread_worst: 4.25, spread_best: 3.55, stop_level: 4.2, counterfactual_spread: 3.9 },
        { minute: "04-18", underlying: 928.0, spread_worst: 4.5, spread_best: 3.6, stop_level: 4.2, counterfactual_spread: 4.5 },
        { minute: "05-17", underlying: 948.0, spread_worst: 10.0, spread_best: 10.0, stop_level: 4.2, counterfactual_spread: 10.0 },
      ],
    },
    {
      id: "pos_aapl_20240419_p170",
      security_id: "AAPL",
      spread_type: "Bull Put",
      short_strike: 170.0,
      long_strike: 165.0,
      expiration: "2024-04-19",
      width: 5.0,
      entry_credit: 1.15,
      margin_required: 3.85, // $385 per contract
      short_delta: -0.22,
      implied_volatility: 0.248,
      open_timestamp: "2024-03-15 10:02 ET",
      open_rule: "IV_RANK_GT_50_DELTA_20",
      close_timestamp: "2024-04-12 14:35 ET",
      close_rule: "PROFIT_TARGET_80_PCT",
      days_held: 28,
      status: "Closed Profit Target",
      worst_net_pnl: 91.0,
      best_net_pnl: 94.0,
      return_on_margin_pct: 23.6,
      annualized_rom_pct: 307.0,
      bid_ask_spread_drag: 14.0,
      slippage_cost: 4.0,
      execution_mode: "Multi-Leg Complex Ticket",
      greeks: {
        entry: { delta: -0.22, theta: 2.4, gamma: "Low", vega: 8.5 },
        mid: { delta: -0.11, theta: 3.1, gamma: "Low", vega: 5.2 },
        exit: { delta: -0.03, theta: 1.2, gamma: "Negligible", vega: 1.8 },
      },
      stop_movements: [
        { timestamp: "2024-03-15 10:02 ET", previous_stop: 0, new_stop: 2.3, trigger_rule: "INITIAL_2X_CREDIT", underlying_price: 172.6 },
        { timestamp: "2024-03-26 11:20 ET", previous_stop: 2.3, new_stop: 1.75, trigger_rule: "PROFIT_30_PCT_RATCHET", underlying_price: 174.1 },
        { timestamp: "2024-04-05 13:45 ET", previous_stop: 1.75, new_stop: 1.15, trigger_rule: "BREAKEVEN_LOCK", underlying_price: 176.8 },
      ],
      counterfactual: {
        outcome: "NORMAL_PROFIT",
        value_at_expiration: 0.0,
        difference_amount: 24.0,
        explanation: "Took profit early at 80% max gain ($91). Held to expiry would have netted remaining $24 for 7 more days of risk.",
      },
      missing_minutes_count: 0,
      gaps: [],
      reliability_pct: 100.0,
      candles: [
        { date: "03-15", open: 171.8, high: 173.2, low: 171.5, close: 172.6, volume: 5500000 },
        { date: "03-22", open: 172.5, high: 174.0, low: 172.0, close: 173.2, volume: 4900000 },
        { date: "03-29", open: 173.0, high: 175.2, low: 172.8, close: 174.5, volume: 5200000 },
        { date: "04-05", open: 175.0, high: 177.4, low: 174.6, close: 176.8, volume: 6100000 },
        { date: "04-12", open: 177.0, high: 178.5, low: 176.5, close: 178.1, volume: 5800000 },
        { date: "04-19", open: 178.0, high: 180.2, low: 177.8, close: 179.5, volume: 6400000 },
      ],
      trajectory_points: [
        { minute: "03-15", underlying: 172.6, spread_worst: 1.15, spread_best: 1.15, stop_level: 2.3, counterfactual_spread: 1.15 },
        { minute: "03-22", underlying: 173.2, spread_worst: 0.98, spread_best: 0.92, stop_level: 2.3, counterfactual_spread: 0.95 },
        { minute: "03-29", underlying: 174.5, spread_worst: 0.76, spread_best: 0.69, stop_level: 1.75, counterfactual_spread: 0.72 },
        { minute: "04-05", underlying: 176.8, spread_worst: 0.48, spread_best: 0.42, stop_level: 1.15, counterfactual_spread: 0.45 },
        { minute: "04-12", underlying: 178.1, spread_worst: 0.24, spread_best: 0.21, stop_level: 1.15, counterfactual_spread: 0.23 },
        { minute: "04-19", underlying: 179.5, spread_worst: 0.0, spread_best: 0.0, stop_level: 1.15, counterfactual_spread: 0.0 },
      ],
    },
    {
      id: "pos_spy_20240621_p500",
      security_id: "SPY",
      spread_type: "Bull Put",
      short_strike: 500.0,
      long_strike: 490.0,
      expiration: "2024-06-21",
      width: 10.0,
      entry_credit: 1.8,
      margin_required: 8.2, // $820 per contract
      short_delta: -0.18,
      implied_volatility: 0.154,
      open_timestamp: "2024-05-01 10:15 ET",
      open_rule: "DELTA_18_OOTM_BULL_PUT",
      close_timestamp: "2024-06-21 16:00 ET",
      close_rule: "EXPIRED_WORTHLESS",
      days_held: 51,
      status: "Expired Worthless",
      worst_net_pnl: 179.0,
      best_net_pnl: 180.0,
      return_on_margin_pct: 21.8,
      annualized_rom_pct: 156.0,
      bid_ask_spread_drag: 18.0,
      slippage_cost: 1.0,
      execution_mode: "Multi-Leg Complex Ticket",
      greeks: {
        entry: { delta: -0.18, theta: 1.8, gamma: "Low", vega: 12.0 },
        mid: { delta: -0.08, theta: 2.4, gamma: "Low", vega: 6.5 },
        exit: { delta: 0.0, theta: 0.0, gamma: "Zero", vega: 0.0 },
      },
      stop_movements: [
        { timestamp: "2024-05-01 10:15 ET", previous_stop: 0, new_stop: 3.6, trigger_rule: "INITIAL_2X_CREDIT", underlying_price: 508.2 },
        { timestamp: "2024-05-24 14:00 ET", previous_stop: 3.6, new_stop: 1.8, trigger_rule: "PROFIT_50_PCT_RATCHET", underlying_price: 524.5 },
      ],
      counterfactual: {
        outcome: "NORMAL_PROFIT",
        value_at_expiration: 0.0,
        difference_amount: 0.0,
        explanation: "Expired 100% worthless for full maximum credit of $180.00.",
      },
      missing_minutes_count: 0,
      gaps: [],
      reliability_pct: 100.0,
      candles: [
        { date: "05-01", open: 506.0, high: 509.5, low: 505.0, close: 508.2, volume: 62000000 },
        { date: "05-15", open: 515.0, high: 519.0, low: 514.0, close: 518.0, volume: 54000000 },
        { date: "05-30", open: 524.0, high: 527.5, low: 523.0, close: 526.0, volume: 48000000 },
        { date: "06-14", open: 532.0, high: 536.0, low: 531.0, close: 535.0, volume: 51000000 },
        { date: "06-21", open: 542.0, high: 545.0, low: 541.0, close: 544.0, volume: 67000000 },
      ],
      trajectory_points: [
        { minute: "05-01", underlying: 508.2, spread_worst: 1.8, spread_best: 1.8, stop_level: 3.6, counterfactual_spread: 1.8 },
        { minute: "05-15", underlying: 518.0, spread_worst: 1.15, spread_best: 1.05, stop_level: 3.6, counterfactual_spread: 1.1 },
        { minute: "05-30", underlying: 526.0, spread_worst: 0.6, spread_best: 0.5, stop_level: 1.8, counterfactual_spread: 0.55 },
        { minute: "06-14", underlying: 535.0, spread_worst: 0.18, spread_best: 0.12, stop_level: 1.8, counterfactual_spread: 0.15 },
        { minute: "06-21", underlying: 544.0, spread_worst: 0.01, spread_best: 0.0, stop_level: 1.8, counterfactual_spread: 0.0 },
      ],
    },
    {
      id: "pos_msft_20240628_c450",
      security_id: "MSFT",
      spread_type: "Bear Call",
      short_strike: 450.0,
      long_strike: 460.0,
      expiration: "2024-06-28",
      width: 10.0,
      entry_credit: 2.1,
      margin_required: 7.9, // $790 per contract
      short_delta: 0.25,
      implied_volatility: 0.221,
      open_timestamp: "2024-05-20 11:30 ET",
      open_rule: "RESISTANCE_CALL_SPREAD",
      close_timestamp: "2024-06-14 15:10 ET",
      close_rule: "EARNINGS_PRE_RUN_EXIT",
      days_held: 25,
      status: "Closed Early Risk",
      worst_net_pnl: 139.0,
      best_net_pnl: 155.0,
      return_on_margin_pct: 17.6,
      annualized_rom_pct: 257.0,
      bid_ask_spread_drag: 22.0,
      slippage_cost: 8.5,
      execution_mode: "Multi-Leg Complex Ticket",
      greeks: {
        entry: { delta: 0.25, theta: 3.2, gamma: "Low", vega: 14.0 },
        mid: { delta: 0.18, theta: 4.1, gamma: "Low", vega: 9.8 },
        exit: { delta: 0.09, theta: 2.0, gamma: "Low", vega: 4.5 },
      },
      stop_movements: [
        { timestamp: "2024-05-20 11:30 ET", previous_stop: 0, new_stop: 4.2, trigger_rule: "INITIAL_2X_CREDIT", underlying_price: 432.0 },
      ],
      counterfactual: {
        outcome: "NORMAL_PROFIT",
        value_at_expiration: 0.0,
        difference_amount: 71.0,
        explanation: "Closed ahead of earnings to avoid gap risk. MSFT stayed below $450 at expiry; remaining $71 premium left on table safely.",
      },
      missing_minutes_count: 11,
      gaps: [{ start: "2024-06-05 14:12 ET", end: "2024-06-05 14:23 ET", duration_minutes: 11, reason: "Alpaca matching minute gap: Long leg $460C has zero trade/quote ticks during interval" }],
      reliability_pct: 88.5,
      candles: [
        { date: "05-20", open: 430.0, high: 434.0, low: 428.5, close: 432.0, volume: 18000000 },
        { date: "05-28", open: 431.0, high: 432.5, low: 427.0, close: 429.0, volume: 16500000 },
        { date: "06-05", open: 433.0, high: 439.5, low: 432.0, close: 438.0, volume: 21000000 },
        { date: "06-14", open: 440.0, high: 444.0, low: 439.0, close: 442.5, volume: 19500000 },
        { date: "06-28", open: 445.0, high: 448.0, low: 443.0, close: 446.0, volume: 24000000 },
      ],
      trajectory_points: [
        { minute: "05-20", underlying: 432.0, spread_worst: 2.1, spread_best: 2.1, stop_level: 4.2, counterfactual_spread: 2.1 },
        { minute: "05-28", underlying: 429.0, spread_worst: 1.75, spread_best: 1.55, stop_level: 4.2, counterfactual_spread: 1.65 },
        { minute: "06-05", underlying: 438.0, spread_worst: 1.4, spread_best: 1.1, stop_level: 4.2, counterfactual_spread: 1.25 },
        { minute: "06-14", underlying: 442.5, spread_worst: 0.71, spread_best: 0.55, stop_level: 4.2, counterfactual_spread: 0.63 },
        { minute: "06-28", underlying: 446.0, spread_worst: 0.0, spread_best: 0.0, stop_level: 4.2, counterfactual_spread: 0.0 },
      ],
    },
  ],

  blocked_candidates: [
    {
      id: "blk_aapl_20240424",
      security_id: "AAPL",
      candidate_type: "Bull Put 165/160",
      timestamp: "2024-04-24 10:00 ET",
      rule_id: "EARNINGS_BLACKOUT",
      reason: "Blocked by earnings calendar rule",
      details: "Upcoming Q2 earnings announcement on 2024-05-02 is within the 7-day exclusion blackout window.",
    },
    {
      id: "blk_tsla_20240320",
      security_id: "TSLA",
      candidate_type: "Bear Call 190/200",
      timestamp: "2024-03-20 14:30 ET",
      rule_id: "FINAL_SEVEN_DAY_RULE",
      reason: "Blocked by final-seven-day rule",
      details: "Target expiry 2024-03-22 has DTE < 7 days; model restricts new entries inside final expiration week.",
    },
    {
      id: "blk_nvda_20240505",
      security_id: "NVDA",
      candidate_type: "Bull Put 850/840",
      timestamp: "2024-05-05 11:15 ET",
      rule_id: "PORTFOLIO_LIMIT",
      reason: "Blocked by portfolio margin limit",
      details: "Active NVDA risk exposure ($10,000 max width) meets portfolio single-name concentration threshold.",
    },
    {
      id: "blk_amd_20240512",
      security_id: "AMD",
      candidate_type: "Bear Call 170/180",
      timestamp: "2024-05-12 13:45 ET",
      rule_id: "SIMILARITY_LIMIT",
      reason: "Blocked by similarity threshold limit",
      details: "Correlation of AMD bear call with active NVDA semiconductor short position exceeds 0.85 threshold.",
    },
  ],
};
