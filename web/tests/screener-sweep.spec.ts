import { expect, test } from "playwright/test";

test("Tab 4 renders screener sweep table, diagnostic banner, and clicking a row loads security into primary config and runs 5-gate evaluation", async ({
  page,
}) => {
  let verdictRequests: unknown[] = [];

  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      json: [{ id: "proj-1", name: "Screener Alpha Project" }],
    }),
  );
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found" } }),
  );

  const mockScreenerSweep = {
    strategy_name: "trend_exhaustion",
    benchmark_symbol: "SPY",
    diagnostic_banner: {
      market_edge_detected: true,
      edge_distribution: "MARKET_WIDE",
      headline: "Market-Wide Systematic Edge",
      summary:
        "Positive net edge observed across 2 of 3 securities (66.7%). Systematic edge persists across the broad market relative to SPY.",
      total_securities: 3,
      positive_edge_securities: 2,
      market_breadth_pct: 66.7,
    },
    candidates: [
      {
        rank: 1,
        symbol: "AAPL",
        name: "Apple Inc.",
        sector: "Technology",
        strategy_return: 0.155,
        benchmark_return: 0.082,
        net_edge: 0.073,
        win_rate: 0.643,
        profit_factor: 2.15,
        trades_count: 14,
        status: "PASS",
      },
      {
        rank: 2,
        symbol: "MSFT",
        name: "Microsoft Corp.",
        sector: "Technology",
        strategy_return: 0.101,
        benchmark_return: 0.082,
        net_edge: 0.019,
        win_rate: 0.55,
        profit_factor: 1.45,
        trades_count: 10,
        status: "PASS",
      },
      {
        rank: 3,
        symbol: "TSLA",
        name: "Tesla Inc.",
        sector: "Consumer Discretionary",
        strategy_return: 0.035,
        benchmark_return: 0.082,
        net_edge: -0.047,
        win_rate: 0.38,
        profit_factor: 0.85,
        trades_count: 8,
        status: "FAIL",
      },
    ],
  };

  const mockVerdictResponse = {
    overall_passed: true,
    headline_verdict: "Strategy Clears All 5 Hurdle Gates",
    rejection_reason: null,
    confidence_score: 0.88,
    holdout_ratio: 0.25,
    gates: [
      {
        gate_number: 1,
        name: "Benchmark Hurdle",
        passed: true,
        metric_label: "Strategy vs SPY",
        metric_value: "+15.5% vs +8.2%",
        threshold_label: "Hurdle",
        threshold_value: "> Benchmark",
        verdict_note: "Excess return cleared",
      },
      {
        gate_number: 2,
        name: "Fee Stress",
        passed: true,
        metric_label: "3x PF",
        metric_value: "1.65 PF",
        threshold_label: "Hurdle",
        threshold_value: "> 1.0 PF",
        verdict_note: "Robust to friction",
      },
      {
        gate_number: 3,
        name: "Sample Size",
        passed: true,
        metric_label: "Closed Trades",
        metric_value: "35 trades",
        threshold_label: "Min Trades",
        threshold_value: ">= 30 trades",
        verdict_note: "Sufficient sample size",
      },
      {
        gate_number: 4,
        name: "Probabilistic Sharpe Ratio",
        passed: true,
        metric_label: "PSR",
        metric_value: "88.0%",
        threshold_label: "Min Confidence",
        threshold_value: ">= 60.0%",
        verdict_note: "Statistical edge confirmed",
      },
      {
        gate_number: 5,
        name: "Random Timing Luck",
        passed: true,
        metric_label: "Percentile",
        metric_value: "82.5th",
        threshold_label: "Hurdle",
        threshold_value: ">= 75.0th",
        verdict_note: "Timing skill verified",
      },
    ],
    in_sample_metrics: {
      total_return: 0.12,
      cagr: 0.14,
      sharpe_ratio: 1.5,
      sortino_ratio: 1.8,
      max_drawdown: -0.06,
      benchmark_return: 0.06,
      win_rate: 0.65,
      profit_factor: 2.1,
      trades_count: 25,
      exposure_pct: 0.45,
    },
    out_of_sample_metrics: {
      total_return: 0.05,
      cagr: 0.11,
      sharpe_ratio: 1.2,
      sortino_ratio: 1.4,
      max_drawdown: -0.04,
      benchmark_return: 0.022,
      win_rate: 0.60,
      profit_factor: 1.8,
      trades_count: 10,
      exposure_pct: 0.42,
    },
    combined_metrics: {
      total_return: 0.155,
      cagr: 0.135,
      sharpe_ratio: 1.45,
      sortino_ratio: 1.7,
      max_drawdown: -0.06,
      benchmark_return: 0.082,
      win_rate: 0.643,
      profit_factor: 2.15,
      trades_count: 35,
      exposure_pct: 0.44,
    },
    equity_curve: [
      {
        session_date: "2024-01-02",
        strategy_equity: 100000,
        benchmark_equity: 100000,
        drawdown_pct: 0,
        is_holdout: false,
      },
      {
        session_date: "2024-01-15",
        strategy_equity: 115500,
        benchmark_equity: 108200,
        drawdown_pct: 0,
        is_holdout: true,
      },
    ],
    friction_ladder: [],
    screener_sweep: mockScreenerSweep,
  };

  await page.route("**/api/projects/proj-1/backtests/verdict", async (route) => {
    const postData = route.request().postDataJSON();
    verdictRequests.push(postData);
    await route.fulfill({ json: mockVerdictResponse });
  });

  await page.route("**/api/projects/proj-1/backtests/screener", async (route) => {
    await route.fulfill({ json: mockScreenerSweep });
  });

  // Start Vite preview with backtest tab active
  await page.goto("/?tab=backtest");
  await page.waitForLoadState("domcontentloaded");

  // Find and click the initial Run Backtest button
  const runBtn = page.getByRole("button", { name: /Run Backtest & Generate Verdict/ });
  await expect(runBtn).toBeVisible({ timeout: 10000 });
  await runBtn.click();

  // Tab navigation should now be visible. Switch to Tab 4 (Universe Screener)
  const tab4 = page.getByText("4. Universe Screener");
  await expect(tab4).toBeVisible({ timeout: 10000 });
  await tab4.click();

  // Verify diagnostic banner
  await expect(page.getByText(/MARKET-WIDE EDGE/i)).toBeVisible();
  await expect(page.getByText("Market-Wide Systematic Edge")).toBeVisible();
  await expect(page.getByText(/Positive net edge observed across 2 of 3 securities/)).toBeVisible();

  // Verify table contents
  await expect(page.getByText("Universe Diagnostic Screener Table")).toBeVisible();
  await expect(page.getByText("AAPL")).toBeVisible();
  await expect(page.getByText("Apple Inc.")).toBeVisible();
  await expect(page.getByText("MSFT")).toBeVisible();
  await expect(page.getByText("Microsoft Corp.")).toBeVisible();
  await expect(page.getByText("TSLA")).toBeVisible();
  await expect(page.getByText("Tesla Inc.")).toBeVisible();

  // Verify returns and status tokens
  await expect(page.getByText("+7.3%")).toBeVisible();
  await expect(page.getByText("+1.9%")).toBeVisible();
  await expect(page.getByText("-4.7%")).toBeVisible();

  // Clicking a row loads selected security into primary configuration and runs full 5-gate audit
  const initialCount = verdictRequests.length;
  const msftRow = page.getByRole("row", { name: /MSFT/ });
  await msftRow.click();

  // Verify that another verdict request was sent specifying MSFT as symbol
  await expect.poll(() => verdictRequests.length).toBeGreaterThan(initialCount);
  const lastRequest = verdictRequests[verdictRequests.length - 1] as Record<string, unknown>;
  expect(lastRequest.symbol).toBe("MSFT");

  // Verify notification banner indicating MSFT is loaded into primary configuration
  await expect(page.getByText(/Security MSFT loaded into primary configuration/)).toBeVisible();
  await expect(page.getByText(/Target: MSFT/)).toBeVisible();
});
