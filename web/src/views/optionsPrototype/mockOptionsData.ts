export interface OptionLegPrice {
  minute: string;
  bid: number;
  ask: number;
  mid: number;
}

export interface StopLevelEvent {
  timestamp: string;
  previous_stop: number;
  new_stop: number;
  trigger_reason: string;
  underlying_price: number;
}

export interface DataGap {
  start_minute: string;
  end_minute: string;
  duration_minutes: number;
  reason: string;
  severity: "critical" | "warning";
}

export interface OptionSpreadPosition {
  id: string;
  security_id: string;
  spread_type: "Bull Put" | "Bear Call" | "Iron Condor";
  short_strike: number;
  long_strike: number;
  expiration: string;
  width: number;
  short_delta: number;
  implied_volatility: number;
  entry_credit: number;
  open_timestamp: string;
  open_rule: string;
  close_timestamp: string;
  close_rule: string;
  status: "Closed Profit Target" | "Closed Stop Level" | "Expired Worthless" | "Closed Early Risk";

  // Dual Execution Paths: Worst vs Best
  worst_execution: {
    short_leg_exit: number;
    long_leg_exit: number;
    net_debit_to_close: number;
    net_pnl: number;
    return_pct: number;
    slippage_cost: number;
  };
  best_execution: {
    short_leg_exit: number;
    long_leg_exit: number;
    net_debit_to_close: number;
    net_pnl: number;
    return_pct: number;
    slippage_cost: number;
  };

  stop_movements: StopLevelEvent[];
  data_gaps: DataGap[];
  missing_matching_minutes_count: number;
  reliability_score: number; // e.g. 98.5%

  // Minute-by-minute trajectory preview
  trajectory: {
    minute: string;
    underlying: number;
    spread_mid: number;
    spread_worst: number;
    spread_best: number;
    stop_level: number;
  }[];
}

export interface BlockedPosition {
  id: string;
  security_id: string;
  candidate_type: string;
  timestamp: string;
  rule_id: "EARNINGS_BLACKOUT" | "FINAL_SEVEN_DAY_RULE" | "PORTFOLIO_LIMIT" | "SIMILARITY_LIMIT";
  reason: string;
  details: string;
}

export interface OptionsBacktestRun {
  run_id: string;
  provider: "Alpaca";
  date_range: {
    start: string;
    end: string;
  };
  strategy_name: string;
  strategy_revision: string;
  dataset_version: string;
  engine_source_fingerprint: string;

  // Dual-path Portfolio Summary
  worst_result: {
    net_pnl: number;
    total_return_pct: number;
    annualized_return_pct: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown_pct: number;
    calmar_ratio: number;
    win_rate_pct: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    gross_credit: number;
    total_slippage: number;
    total_commissions: number;
  };
  best_result: {
    net_pnl: number;
    total_return_pct: number;
    annualized_return_pct: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown_pct: number;
    calmar_ratio: number;
    win_rate_pct: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    gross_credit: number;
    total_slippage: number;
    total_commissions: number;
  };

  positions: OptionSpreadPosition[];
  blocked_positions: BlockedPosition[];

  data_health: {
    total_bars: number;
    missing_matching_minutes: number;
    gaps_over_5_min: number;
    overall_reliability_pct: number;
  };
}

export const MOCK_OPTIONS_RUN: OptionsBacktestRun = {
  run_id: "opt_run_20240826_alpaca_9f81a",
  provider: "Alpaca",
  date_range: {
    start: "2024-03-01",
    end: "2024-06-28",
  },
  strategy_name: "credit_spread_vol_ratchet",
  strategy_revision: "credit_spread_vol_ratchet:v2",
  dataset_version: "alpaca_options_chains_2024_q1_q2_v1",
  engine_source_fingerprint: "sha256:7f3b892ac19e81b6728045dd189cf0049e7b23d9a54e60124",

  worst_result: {
    net_pnl: -320.0,
    total_return_pct: -0.32,
    annualized_return_pct: -0.96,
    sharpe_ratio: 1.18,
    sortino_ratio: 1.42,
    max_drawdown_pct: -2.4,
    calmar_ratio: 0.40,
    win_rate_pct: 78.6, // 11 of 14
    total_trades: 14,
    winning_trades: 11,
    losing_trades: 3,
    gross_credit: 2450.0,
    total_slippage: 142.5,
    total_commissions: 28.0,
  },

  best_result: {
    net_pnl: 640.0,
    total_return_pct: 0.64,
    annualized_return_pct: 1.92,
    sharpe_ratio: 1.84,
    sortino_ratio: 2.31,
    max_drawdown_pct: -1.2,
    calmar_ratio: 1.60,
    win_rate_pct: 92.9, // 13 of 14
    total_trades: 14,
    winning_trades: 13,
    losing_trades: 1,
    gross_credit: 2450.0,
    total_slippage: 38.0,
    total_commissions: 28.0,
  },

  data_health: {
    total_bars: 38400,
    missing_matching_minutes: 18,
    gaps_over_5_min: 2,
    overall_reliability_pct: 99.4,
  },

  positions: [
    {
      id: "pos_aapl_20240419_p170",
      security_id: "AAPL",
      spread_type: "Bull Put",
      short_strike: 170.0,
      long_strike: 165.0,
      expiration: "2024-04-19",
      width: 5.0,
      short_delta: -0.22,
      implied_volatility: 0.248,
      entry_credit: 1.15,
      open_timestamp: "2024-03-15 10:02 ET",
      open_rule: "IV_RANK_GT_50_DELTA_20",
      close_timestamp: "2024-04-12 14:35 ET",
      close_rule: "PROFIT_TARGET_80_PCT",
      status: "Closed Profit Target",
      worst_execution: {
        short_leg_exit: 0.25,
        long_leg_exit: 0.01,
        net_debit_to_close: 0.24,
        net_pnl: 91.0,
        return_pct: 18.2,
        slippage_cost: 4.0,
      },
      best_execution: {
        short_leg_exit: 0.22,
        long_leg_exit: 0.01,
        net_debit_to_close: 0.21,
        net_pnl: 94.0,
        return_pct: 18.8,
        slippage_cost: 1.0,
      },
      stop_movements: [
        {
          timestamp: "2024-03-15 10:02 ET",
          previous_stop: 0,
          new_stop: 2.3,
          trigger_reason: "INITIAL_ENTRY_2X_CREDIT",
          underlying_price: 172.6,
        },
        {
          timestamp: "2024-03-26 11:20 ET",
          previous_stop: 2.3,
          new_stop: 1.75,
          trigger_reason: "PROFIT_MILESTONE_30_PCT_RATCHET",
          underlying_price: 174.1,
        },
        {
          timestamp: "2024-04-05 13:45 ET",
          previous_stop: 1.75,
          new_stop: 1.15,
          trigger_reason: "PROFIT_MILESTONE_60_PCT_BREAKEVEN_LOCK",
          underlying_price: 176.8,
        },
      ],
      data_gaps: [],
      missing_matching_minutes_count: 0,
      reliability_score: 100.0,
      trajectory: [
        { minute: "03-15", underlying: 172.6, spread_mid: 1.15, spread_worst: 1.15, spread_best: 1.15, stop_level: 2.3 },
        { minute: "03-22", underlying: 173.2, spread_mid: 0.95, spread_worst: 0.98, spread_best: 0.92, stop_level: 2.3 },
        { minute: "03-29", underlying: 174.5, spread_mid: 0.72, spread_worst: 0.76, spread_best: 0.69, stop_level: 1.75 },
        { minute: "04-05", underlying: 176.8, spread_mid: 0.45, spread_worst: 0.48, spread_best: 0.42, stop_level: 1.15 },
        { minute: "04-12", underlying: 178.1, spread_mid: 0.23, spread_worst: 0.24, spread_best: 0.21, stop_level: 1.15 },
      ],
    },
    {
      id: "pos_nvda_20240517_c920",
      security_id: "NVDA",
      spread_type: "Bear Call",
      short_strike: 920.0,
      long_strike: 930.0,
      expiration: "2024-05-17",
      width: 10.0,
      short_delta: 0.28,
      implied_volatility: 0.482,
      entry_credit: 2.85,
      open_timestamp: "2024-04-02 09:45 ET",
      open_rule: "MOMENTUM_OVERBOUGHT_BEAR_CALL",
      close_timestamp: "2024-04-18 11:18 ET",
      close_rule: "STOP_LEVEL_BREACH_INTRADAY",
      status: "Closed Stop Level",
      worst_execution: {
        short_leg_exit: 5.4,
        long_leg_exit: 0.9,
        net_debit_to_close: 4.5,
        net_pnl: -165.0,
        return_pct: -16.5,
        slippage_cost: 32.0,
      },
      best_execution: {
        short_leg_exit: 4.8,
        long_leg_exit: 1.2,
        net_debit_to_close: 3.6,
        net_pnl: -75.0,
        return_pct: -7.5,
        slippage_cost: 8.0,
      },
      stop_movements: [
        {
          timestamp: "2024-04-02 09:45 ET",
          previous_stop: 0,
          new_stop: 5.7,
          trigger_reason: "INITIAL_ENTRY_2X_CREDIT",
          underlying_price: 890.5,
        },
        {
          timestamp: "2024-04-10 14:15 ET",
          previous_stop: 5.7,
          new_stop: 4.2,
          trigger_reason: "TIME_DECAY_WEEK_2_TIGHTEN",
          underlying_price: 896.0,
        },
      ],
      data_gaps: [
        {
          start_minute: "2024-04-10 13:22 ET",
          end_minute: "2024-04-10 13:29 ET",
          duration_minutes: 7,
          reason: "Alpaca feed quote latency spike (no NBBO updates for NVDA $920C)",
          severity: "warning",
        },
      ],
      missing_matching_minutes_count: 7,
      reliability_score: 94.2,
      trajectory: [
        { minute: "04-02", underlying: 890.5, spread_mid: 2.85, spread_worst: 2.85, spread_best: 2.85, stop_level: 5.7 },
        { minute: "04-08", underlying: 885.0, spread_mid: 2.4, spread_worst: 2.48, spread_best: 2.32, stop_level: 5.7 },
        { minute: "04-12", underlying: 902.0, spread_mid: 3.2, spread_worst: 3.45, spread_best: 2.95, stop_level: 4.2 },
        { minute: "04-16", underlying: 915.0, spread_mid: 3.9, spread_worst: 4.25, spread_best: 3.55, stop_level: 4.2 },
        { minute: "04-18", underlying: 928.0, spread_mid: 4.5, spread_worst: 4.5, spread_best: 3.6, stop_level: 4.2 },
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
      short_delta: -0.18,
      implied_volatility: 0.154,
      entry_credit: 1.8,
      open_timestamp: "2024-05-01 10:15 ET",
      open_rule: "DELTA_18_OOTM_BULL_PUT",
      close_timestamp: "2024-06-21 16:00 ET",
      close_rule: "EXPIRED_WORTHLESS",
      status: "Expired Worthless",
      worst_execution: {
        short_leg_exit: 0.01,
        long_leg_exit: 0.0,
        net_debit_to_close: 0.01,
        net_pnl: 179.0,
        return_pct: 17.9,
        slippage_cost: 1.0,
      },
      best_execution: {
        short_leg_exit: 0.0,
        long_leg_exit: 0.0,
        net_debit_to_close: 0.0,
        net_pnl: 180.0,
        return_pct: 18.0,
        slippage_cost: 0.0,
      },
      stop_movements: [
        {
          timestamp: "2024-05-01 10:15 ET",
          previous_stop: 0,
          new_stop: 3.6,
          trigger_reason: "INITIAL_ENTRY_2X_CREDIT",
          underlying_price: 508.2,
        },
        {
          timestamp: "2024-05-24 14:00 ET",
          previous_stop: 3.6,
          new_stop: 1.8,
          trigger_reason: "PROFIT_50_PCT_RATCHET",
          underlying_price: 524.5,
        },
      ],
      data_gaps: [],
      missing_matching_minutes_count: 0,
      reliability_score: 100.0,
      trajectory: [
        { minute: "05-01", underlying: 508.2, spread_mid: 1.8, spread_worst: 1.8, spread_best: 1.8, stop_level: 3.6 },
        { minute: "05-15", underlying: 518.0, spread_mid: 1.1, spread_worst: 1.15, spread_best: 1.05, stop_level: 3.6 },
        { minute: "05-30", underlying: 526.0, spread_mid: 0.55, spread_worst: 0.6, spread_best: 0.5, stop_level: 1.8 },
        { minute: "06-14", underlying: 535.0, spread_mid: 0.15, spread_worst: 0.18, spread_best: 0.12, stop_level: 1.8 },
        { minute: "06-21", underlying: 544.0, spread_mid: 0.0, spread_worst: 0.01, spread_best: 0.0, stop_level: 1.8 },
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
      short_delta: 0.25,
      implied_volatility: 0.221,
      entry_credit: 2.1,
      open_timestamp: "2024-05-20 11:30 ET",
      open_rule: "RESISTANCE_CALL_SPREAD",
      close_timestamp: "2024-06-14 15:10 ET",
      close_rule: "EARNINGS_PRE_RUN_EXIT",
      status: "Closed Early Risk",
      worst_execution: {
        short_leg_exit: 0.75,
        long_leg_exit: 0.04,
        net_debit_to_close: 0.71,
        net_pnl: 139.0,
        return_pct: 13.9,
        slippage_cost: 8.5,
      },
      best_execution: {
        short_leg_exit: 0.6,
        long_leg_exit: 0.05,
        net_debit_to_close: 0.55,
        net_pnl: 155.0,
        return_pct: 15.5,
        slippage_cost: 2.0,
      },
      stop_movements: [
        {
          timestamp: "2024-05-20 11:30 ET",
          previous_stop: 0,
          new_stop: 4.2,
          trigger_reason: "INITIAL_ENTRY_2X_CREDIT",
          underlying_price: 432.0,
        },
      ],
      data_gaps: [
        {
          start_minute: "2024-06-05 14:12 ET",
          end_minute: "2024-06-05 14:23 ET",
          duration_minutes: 11,
          reason: "Alpaca matching minute gap: Long leg $460C has zero trade/quote ticks during interval",
          severity: "critical",
        },
      ],
      missing_matching_minutes_count: 11,
      reliability_score: 88.5,
      trajectory: [
        { minute: "05-20", underlying: 432.0, spread_mid: 2.1, spread_worst: 2.1, spread_best: 2.1, stop_level: 4.2 },
        { minute: "05-28", underlying: 429.0, spread_mid: 1.65, spread_worst: 1.75, spread_best: 1.55, stop_level: 4.2 },
        { minute: "06-05", underlying: 438.0, spread_mid: 1.25, spread_worst: 1.4, spread_best: 1.1, stop_level: 4.2 },
        { minute: "06-14", underlying: 442.5, spread_mid: 0.63, spread_worst: 0.71, spread_best: 0.55, stop_level: 4.2 },
      ],
    },
  ],

  blocked_positions: [
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
