import { expect, test } from "playwright/test";

const mockReplayTicks = [
  {
    date: "2024-01-02",
    price: 150.0,
    signal: 0.0,
    position_shares: 0.0,
    portfolio_value: 100000.0,
    cash: 100000.0,
    daily_pnl: 0.0,
    position_value: 0.0,
    allocation_pct: 0.0,
    fill_actions: [],
  },
  {
    date: "2024-01-03",
    price: 152.0,
    signal: 1.0,
    position_shares: 650.0,
    portfolio_value: 100000.0,
    cash: 1200.0,
    daily_pnl: 0.0,
    position_value: 98800.0,
    allocation_pct: 98.8,
    fill_actions: [
      {
        action_type: "buy",
        quantity: 650.0,
        execution_price: 152.0,
        source_fill_id: "fill-1",
        source_fill_sequence: 1,
      },
    ],
  },
  {
    date: "2024-01-04",
    price: 155.0,
    signal: 1.0,
    position_shares: 650.0,
    portfolio_value: 101950.0,
    cash: 1200.0,
    daily_pnl: 1950.0,
    position_value: 100750.0,
    allocation_pct: 98.8,
    fill_actions: [],
  },
  {
    date: "2024-01-05",
    price: 158.0,
    signal: 1.0,
    position_shares: 650.0,
    portfolio_value: 103900.0,
    cash: 1200.0,
    daily_pnl: 1950.0,
    position_value: 102700.0,
    allocation_pct: 98.8,
    fill_actions: [],
  },
  {
    date: "2024-01-08",
    price: 160.0,
    signal: 0.0,
    position_shares: 0.0,
    portfolio_value: 105200.0,
    cash: 105200.0,
    daily_pnl: 1300.0,
    position_value: 0.0,
    allocation_pct: 0.0,
    fill_actions: [
      {
        action_type: "exit",
        quantity: 650.0,
        execution_price: 160.0,
        source_fill_id: "fill-2",
        source_fill_sequence: 1,
      },
    ],
  },
  {
    date: "2024-01-09",
    price: 159.0,
    signal: 0.0,
    position_shares: 0.0,
    portfolio_value: 105200.0,
    cash: 105200.0,
    daily_pnl: 0.0,
    position_value: 0.0,
    allocation_pct: 0.0,
    fill_actions: [],
  },
];

const mockVerdictResponse = {
  overall_passed: true,
  headline_verdict: "Strategy Clears All Hurdle Gates",
  rejection_reason: null,
  confidence_score: 0.85,
  holdout_ratio: 0.25,
  gates: [
    {
      gate_number: 1,
      name: "Benchmark Hurdle",
      passed: true,
      metric_label: "Net Edge",
      metric_value: "+5.2%",
      threshold_label: "Min Edge",
      threshold_value: "0.0%",
      verdict_note: "Cleared benchmark hurdle",
    },
    {
      gate_number: 2,
      name: "Fee Stress",
      passed: true,
      metric_label: "3x Friction PF",
      metric_value: "1.45",
      threshold_label: "Min PF",
      threshold_value: "1.00",
      verdict_note: "Survives 3x cost stress ladder",
    },
    {
      gate_number: 3,
      name: "Sample Size",
      passed: true,
      metric_label: "Trade Count",
      metric_value: "42",
      threshold_label: "Min Trades",
      threshold_value: "30",
      verdict_note: "Sufficient sample size",
    },
    {
      gate_number: 4,
      name: "Probabilistic Sharpe",
      passed: true,
      metric_label: "PSR Confidence",
      metric_value: "85.0%",
      threshold_label: "Min PSR",
      threshold_value: "60.0%",
      verdict_note: "Statistically distinguished from luck",
    },
    {
      gate_number: 5,
      name: "Monte Carlo Luck",
      passed: true,
      metric_label: "Percentile Rank",
      metric_value: "82.0th",
      threshold_label: "Min Percentile",
      threshold_value: "75.0th",
      verdict_note: "Outperforms random entry timings",
    },
  ],
  in_sample_metrics: {
    total_return: 0.12,
    cagr: 0.15,
    sharpe_ratio: 1.8,
    sortino_ratio: 2.1,
    max_drawdown: -0.06,
    benchmark_return: 0.08,
    win_rate: 0.6,
    profit_factor: 1.85,
    trades_count: 32,
    exposure_pct: 0.45,
  },
  out_of_sample_metrics: {
    total_return: 0.05,
    cagr: 0.11,
    sharpe_ratio: 1.4,
    sortino_ratio: 1.6,
    max_drawdown: -0.04,
    benchmark_return: 0.02,
    win_rate: 0.55,
    profit_factor: 1.6,
    trades_count: 10,
    exposure_pct: 0.4,
  },
  combined_metrics: {
    total_return: 0.17,
    cagr: 0.14,
    sharpe_ratio: 1.7,
    sortino_ratio: 1.9,
    max_drawdown: -0.06,
    benchmark_return: 0.1,
    win_rate: 0.58,
    profit_factor: 1.75,
    trades_count: 42,
    exposure_pct: 0.43,
  },
  equity_curve: [
    {
      session_date: "2024-01-02",
      strategy_equity: 100000.0,
      benchmark_equity: 100000.0,
      drawdown_pct: 0.0,
      is_holdout: false,
    },
    {
      session_date: "2024-01-09",
      strategy_equity: 105200.0,
      benchmark_equity: 101000.0,
      drawdown_pct: 0.0,
      is_holdout: true,
    },
  ],
  friction_ladder: [
    {
      multiplier: 1,
      commission_bps: 5.0,
      slippage_bps: 2.0,
      borrow_fee_bps: 0.0,
      total_return_pct: 17.0,
      net_profit_usd: 5200.0,
      profit_factor: 1.75,
      max_drawdown_pct: 6.0,
      commission_paid_usd: 65.0,
      slippage_drag_usd: 26.0,
      borrow_paid_usd: 0.0,
    },
    {
      multiplier: 3,
      commission_bps: 15.0,
      slippage_bps: 6.0,
      borrow_fee_bps: 0.0,
      total_return_pct: 14.5,
      net_profit_usd: 4500.0,
      profit_factor: 1.45,
      max_drawdown_pct: 6.5,
      commission_paid_usd: 195.0,
      slippage_drag_usd: 78.0,
      borrow_paid_usd: 0.0,
    },
  ],
  replay_ticks: mockReplayTicks,
};

test("Tab 3 interactive simulation replay canvas renders price path, explicit axis labels, markers, order ticket banner, speed toggles, and scrubber", async ({
  page,
}) => {
  // 1. Mock API endpoints
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      json: [
        {
          id: "proj-alpha",
          name: "Alpha Quantitative Fund",
          description: "Replay Test Project",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
      ],
    }),
  );
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found" } }),
  );
  await page.route("**/api/projects/**/backtests/verdict", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      json: mockVerdictResponse,
    }),
  );

  // 2. Navigate directly to backtests view
  await page.goto("/?tab=backtest", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  // 3. Click Run Backtest & Generate Verdict
  const runVerdictBtn = page.getByRole("button", { name: /Run Backtest & Generate Verdict/i });
  await expect(runVerdictBtn).toBeVisible();
  await runVerdictBtn.click();

  // 5. Verify Verdict banner appears
  await expect(page.getByText("Strategy Clears All Hurdle Gates")).toBeVisible();

  // 6. Navigate to Tab 3: Replay & Trade Actions
  const tab3 = page.getByText("3. Replay & Trade Actions");
  await expect(tab3).toBeVisible();
  await tab3.click();
  await page.waitForTimeout(300);

  // 7. Verify explicit axis labels: "PRICE (USD)" and "SESSION TIMELINE"
  const priceAxis = page.locator("text=PRICE (USD)");
  await expect(priceAxis).toBeVisible();
  const timelineAxis = page.locator("text=SESSION TIMELINE");
  await expect(timelineAxis).toBeVisible();

  // 8. Verify Buy ("▲ BUY") and exit ("▼ EXIT") markers appear directly on price bars
  const buyMarker = page.locator("text=▲ BUY").first();
  await expect(buyMarker).toBeVisible();
  const exitMarker = page.locator("text=▼ EXIT").first();
  await expect(exitMarker).toBeVisible();

  // 9. Verify Order Ticket Banner initially displays Day 0 state
  await expect(page.getByText("Order Ticket: No fill")).toBeVisible();
  await expect(page.getByText("$100,000").first()).toBeVisible();

  // 10. Verify Timeline Scrubber allows dragging/stepping to any point
  const scrubber = page.getByTestId("timeline-scrubber");
  await expect(scrubber).toBeVisible();
  await expect(scrubber).toHaveAttribute("min", "0");
  await expect(scrubber).toHaveAttribute("max", "5");

  // Scrub to index 1 (Day of BUY)
  await scrubber.fill("1");
  await page.waitForTimeout(200);

  // Order ticket banner dynamically updates to Day 1 BUY action and allocation
  await expect(page.getByText("Order Ticket: ▲ BUY 650.00 @ $152.00")).toBeVisible();
  await expect(page.getByText("650 shs").first()).toBeVisible();
  await expect(page.getByText("$1,200").first()).toBeVisible();

  // Scrub to index 4 (Day of EXIT)
  await scrubber.fill("4");
  await page.waitForTimeout(200);

  // Order ticket banner dynamically updates to Day 4 EXIT action
  await expect(page.getByText("Order Ticket: ▼ EXIT 650.00 @ $160.00")).toBeVisible();
  await expect(page.getByText("$105,200").first()).toBeVisible();
  await expect(page.getByText("+$1300.00").first()).toBeVisible();

  // 11. Verify playback speed toggles (0.5x, 1x, 2x, 4x) update selected state
  const speedHalf = page.getByRole("radio", { name: "0.5x" });
  await expect(speedHalf).toBeVisible();
  await speedHalf.click();
  await expect(speedHalf).toBeChecked();

  const speed2x = page.getByRole("radio", { name: "2x" });
  await expect(speed2x).toBeVisible();
  await speed2x.click();
  await expect(speed2x).toBeChecked();

  const speed4x = page.getByRole("radio", { name: "4x" });
  await expect(speed4x).toBeVisible();
  await speed4x.click();
  await expect(speed4x).toBeChecked();

  const speed1x = page.getByRole("radio", { name: "1x" });
  await expect(speed1x).toBeVisible();
  await speed1x.click();
  await expect(speed1x).toBeChecked();

  // 12. Test Step Navigation buttons
  const stepPrev = page.getByRole("button", { name: "⏮ Step" });
  await stepPrev.click();
  await page.waitForTimeout(200);
  // Scrubber stepped from index 4 to index 3
  await expect(page.getByText("Active: 2024-01-05")).toBeVisible();

  const resetBtn = page.getByRole("button", { name: "↺ Reset" });
  await resetBtn.click();
  await page.waitForTimeout(200);
  // Scrubber reset to index 0
  await expect(page.getByText("Active: 2024-01-02")).toBeVisible();
  await expect(page.getByText("Order Ticket: No fill")).toBeVisible();

  // 13. Test Click on Recorded Trade Fill table row
  const jumpToExit = page.getByRole("button", { name: "Jump" }).last();
  await jumpToExit.click();
  await page.waitForTimeout(200);
  await expect(page.getByText("Active: 2024-01-08")).toBeVisible();
  await expect(page.getByText("Order Ticket: ▼ EXIT 650.00 @ $160.00")).toBeVisible();
});

test("Playback speed toggle updates stepping cadence at 1200, 600, 300, and 150 ms", async ({ page }) => {
  await page.clock.install({ time: 0 });
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      json: [
        {
          id: "proj-alpha",
          name: "Alpha Quantitative Fund",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
      ],
    }),
  );
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found" } }),
  );
  await page.route("**/api/projects/**/backtests/verdict", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      json: mockVerdictResponse,
    }),
  );

  await page.goto("/?tab=backtest", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  const runVerdictBtn = page.getByRole("button", { name: /Run Backtest & Generate Verdict/i });
  await runVerdictBtn.click();

  // Wait for verdict execution to complete before switching tabs
  await expect(page.getByText("Strategy Clears All Hurdle Gates")).toBeVisible();

  const tab3 = page.getByText("3. Replay & Trade Actions");
  await tab3.click();
  const scrubber = page.getByTestId("timeline-scrubber");
  await expect(scrubber).toBeVisible();

  // Ensure playback starts from index 0
  const resetBtn = page.getByRole("button", { name: "↺ Reset" });
  await resetBtn.click();
  await expect(page.getByText("Active: 2024-01-02")).toBeVisible();
  await page.clock.pauseAt(await page.evaluate(() => Date.now()));

  // 1. Test 4x speed (150ms cadence) without advancing early.
  const speed4x = page.getByRole("radio", { name: "4x" });
  await speed4x.click();
  await expect(speed4x).toBeChecked();
  await expect(page.getByTestId("playback-speed")).toHaveAttribute("data-cadence", "150");

  const playBtn = page.getByRole("button", { name: /Play Replay/i });
  await playBtn.evaluate((button) => button.click());
  expect(await scrubber.inputValue()).toBe("0");
  await page.clock.runFor(149);
  expect(await scrubber.inputValue()).toBe("0");
  await page.clock.runFor(1);
  expect(await scrubber.inputValue()).toBe("1");
  const pauseBtn = page.getByRole("button", { name: /Pause/i });
  await pauseBtn.click();

  // 2. Test 2x speed (300ms cadence) without advancing early.
  const speed2x = page.getByRole("radio", { name: "2x" });
  await speed2x.click();
  await expect(speed2x).toBeChecked();
  await expect(page.getByTestId("playback-speed")).toHaveAttribute("data-cadence", "300");

  await playBtn.evaluate((button) => button.click());
  await page.clock.runFor(299);
  expect(await scrubber.inputValue()).toBe("1");
  await page.clock.runFor(1);
  expect(await scrubber.inputValue()).toBe("2");
  await pauseBtn.click();

  // 3. Test 1x speed (600ms cadence) without advancing early.
  const speed1x = page.getByRole("radio", { name: "1x" });
  await speed1x.click();
  await expect(speed1x).toBeChecked();
  await expect(page.getByTestId("playback-speed")).toHaveAttribute("data-cadence", "600");

  await playBtn.evaluate((button) => button.click());
  await page.clock.runFor(599);
  expect(await scrubber.inputValue()).toBe("2");
  await page.clock.runFor(1);
  expect(await scrubber.inputValue()).toBe("3");
  await pauseBtn.click();

  // 4. Test 0.5x speed (1200ms cadence) without advancing early.
  const speed05x = page.getByRole("radio", { name: "0.5x" });
  await speed05x.click();
  await expect(speed05x).toBeChecked();
  await expect(page.getByTestId("playback-speed")).toHaveAttribute("data-cadence", "1200");

  await playBtn.evaluate((button) => button.click());
  await page.clock.runFor(1199);
  expect(await scrubber.inputValue()).toBe("3");
  await page.clock.runFor(1);
  expect(await scrubber.inputValue()).toBe("4");
  await pauseBtn.click();
});
