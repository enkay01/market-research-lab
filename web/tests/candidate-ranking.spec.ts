import { expect, test } from "playwright/test";

test("Tab 4 renders the latest candidate ranking and preserves it during a security audit", async ({
  page,
}) => {
  interface CapturedVerdictRequest {
    symbol?: string;
  }
  const verdictRequests: CapturedVerdictRequest[] = [];

  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      json: [{ id: "proj-1", name: "Ranking Alpha Project" }],
    }),
  );
  await page.route("**/api/datasets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/downloads/latest", (route) =>
    route.fulfill({ status: 404, json: { code: "download_not_found" } }),
  );

  const candidateRanking = {
    strategy_name: "top_n_momentum",
    benchmark_symbol: "SPY",
    rankings: [
      {
        session_date: "2024-02-05",
        decision_time: "2024-02-05T21:00:00Z",
        security_id: "AAPL",
        score: 0.155,
        rank: 1,
        selected: true,
        target_weight: 1,
        rationale: "Selected among top positive momentum scores with equal weighting.",
      },
      {
        session_date: "2024-02-05",
        decision_time: "2024-02-05T21:00:00Z",
        security_id: "MSFT",
        score: 0.101,
        rank: 2,
        selected: false,
        target_weight: 0,
        rationale: "Not selected by the top-N positive momentum rule.",
      },
      {
        session_date: "2024-02-05",
        decision_time: "2024-02-05T21:00:00Z",
        security_id: "TSLA",
        score: -0.047,
        rank: 3,
        selected: false,
        target_weight: 0,
        rationale: "Not selected by the top-N positive momentum rule.",
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
      win_rate: 0.6,
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
    candidate_ranking: candidateRanking,
  };

  await page.route("**/api/projects/proj-1/backtests/verdict", async (route) => {
    // SAFETY: The mocked route is only used for this test and returns the captured JSON body shape.
    const postData = route.request().postDataJSON() as CapturedVerdictRequest;
    verdictRequests.push(postData);
    await route.fulfill({ json: mockVerdictResponse });
  });

  await page.route("**/api/projects/proj-1/backtests/candidate-ranking", async (route) => {
    await route.fulfill({ json: candidateRanking });
  });

  await page.goto("/?tab=backtest");
  await page.waitForLoadState("domcontentloaded");

  const runButton = page.getByRole("button", { name: /Run Backtest & Generate Verdict/ });
  await expect(runButton).toBeVisible({ timeout: 10000 });
  await runButton.click();

  const tab4 = page.getByText("4. Candidate Ranking");
  await expect(tab4).toBeVisible({ timeout: 10000 });
  await tab4.click();

  await expect(page.getByText("Candidate Ranking", { exact: true })).toBeVisible();
  await expect(page.getByText("Latest ranking snapshot")).toBeVisible();
  await expect(page.getByText("2024-02-05")).toBeVisible();
  await expect(page.getByText("AAPL")).toBeVisible();
  await expect(page.getByText("MSFT")).toBeVisible();
  await expect(page.getByText("TSLA")).toBeVisible();
  await expect(page.getByText("+15.5%")).toBeVisible();

  const initialCount = verdictRequests.length;
  await page.getByRole("row", { name: /MSFT/ }).click();

  await expect.poll(() => verdictRequests.length).toBeGreaterThan(initialCount);
  const lastRequest = verdictRequests[verdictRequests.length - 1];
  expect(lastRequest?.symbol).toBe("MSFT");
  await expect(page.getByText(/Security MSFT loaded into primary configuration/)).toBeVisible();
  await expect(page.getByText(/Target: MSFT/)).toBeVisible();
  await expect(page.getByText("Latest ranking snapshot")).toBeVisible();
});
