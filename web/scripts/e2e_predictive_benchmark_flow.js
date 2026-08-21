import { chromium } from "playwright";
import fs from "fs";
import net from "net";
import os from "os";
import path from "path";
import { execFileSync, spawn } from "child_process";
import { fileURLToPath } from "url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WORKTREE_ROOT = path.resolve(SCRIPT_DIR, "..", "..");
const WEB_ROOT = path.resolve(SCRIPT_DIR, "..");
const SCREENSHOTS_DIR =
  process.env.MARKET_RESEARCH_LAB_E2E_SCREENSHOTS_DIR ??
  path.join(os.tmpdir(), "market-research-lab-e2e-screenshots");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

async function findFreePort(environmentVariable) {
  const configuredPort = process.env[environmentVariable];
  if (configuredPort) return configuredPort;
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address && !Array.isArray(address) ? String(address.port) : null;
      server.close((error) => {
        if (error) reject(error);
        else if (port) resolve(port);
        else reject(new Error("Could not allocate a local test port."));
      });
    });
  });
}

async function waitForServer(url, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return true;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  throw new Error(`Timeout waiting for server at ${url}`);
}

async function run() {
  console.log("1. Starting backend and frontend dev servers...");
  const apiPort = await findFreePort("MARKET_RESEARCH_LAB_API_PORT");
  const webPort = await findFreePort("MARKET_RESEARCH_LAB_WEB_PORT");
  const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
  const webBaseUrl = `http://127.0.0.1:${webPort}`;
  const engineProc = spawn(
    "uv",
    [
      "run",
      "--project",
      "engine",
      "python",
      "-m",
      "uvicorn",
      "market_research_lab.api:app",
      "--host",
      "127.0.0.1",
      "--port",
      apiPort,
    ],
    {
      cwd: WORKTREE_ROOT,
      shell: true,
      stdio: "inherit",
    }
  );

  const webProc = spawn("npx", ["vite", "--port", webPort], {
    cwd: WEB_ROOT,
    env: { ...process.env, MARKET_RESEARCH_LAB_API_PORT: apiPort },
    shell: true,
    stdio: "inherit",
  });

  const cleanup = () => {
    for (const child of [engineProc, webProc]) {
      if (!child.pid) continue;
      try {
        if (process.platform === "win32") {
          execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
            stdio: "ignore",
          });
        } else {
          child.kill();
        }
      } catch {}
    }
  };
  process.on("exit", cleanup);
  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);

  await waitForServer(`${apiBaseUrl}/api/health`);
  await waitForServer(webBaseUrl);
  console.log("Servers are up and ready.");

  console.log("2. Launching Playwright Chromium browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  page.on("console", (msg) => console.log("Browser console:", msg.text()));

  console.log(`3. Navigating to ${webBaseUrl} ...`);
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // Ensure Project exists
  console.log("4. Ensuring project exists...");
  const plusBtn = page.getByRole("button", { name: "+", exact: true });
  if (await plusBtn.isVisible()) {
    await plusBtn.click();
    await page.waitForTimeout(500);
    const projInput = page.getByLabel("Project Name");
    await projInput.fill("Benchmark Research Lab");
    await page.getByRole("button", { name: "Create Project" }).click();
    await page.waitForTimeout(1000);
  }

  // Ingest Market Dataset
  console.log("5. Ingesting market dataset...");
  await page.getByRole("button", { name: "Market Data" }).click();
  await page.waitForTimeout(1000);

  const importBtn = page.getByRole("button", { name: "Import File" }).first();
  if (await importBtn.isVisible()) {
    const sampleCsv = path.join(WEB_ROOT, "sample_market_data.csv");
    await importBtn.click();
    await page.waitForTimeout(500);
    await page.locator("input[type='file']").setInputFiles(sampleCsv);
    await page.locator("form").getByRole("button", { name: "Import" }).click();
    await page.waitForTimeout(2500);
  }

  // Navigate to Models & Strategies View -> Predictive Models tab
  console.log("6. Navigating to Models & Indicators tab...");
  await page.getByRole("button", { name: "Models & Indicators" }).click();
  await page.waitForTimeout(1000);

  const predictiveTab = page.locator("button").filter({ hasText: /Predictive Models/i }).first();
  await predictiveTab.waitFor({ state: "visible" });
  await predictiveTab.click();
  await page.waitForTimeout(1000);

  console.log("7. Running Predictive Model with Naive Benchmark...");
  const runModelBtn = page.getByRole("button", { name: /Run & Save Model|Run Model/i }).first();
  const runResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/predictive-models\/runs$/.test(
        new URL(response.url()).pathname,
      ),
  );
  await runModelBtn.click();
  const runResponse = await runResponsePromise;
  const runBody = await runResponse.json();
  await page.waitForTimeout(3000);

  const projectMatch = new URL(runResponse.url()).pathname.match(
    /\/api\/projects\/([^/]+)\/predictive-models\/runs$/,
  );
  if (!projectMatch) throw new Error("Could not identify the saved Project for the model Run.");
  const projectId = projectMatch[1];
  const benchmark = runBody.benchmark;
  const comparison = benchmark?.out_of_sample_comparison;
  const testPeriod = runBody.period_metrics?.find((period) => period.period === "test");
  const numericComparisonKeys = [
    "model_rmse",
    "benchmark_rmse",
    "rmse_improvement",
    "model_mae",
    "benchmark_mae",
    "mae_improvement",
    "model_r2",
    "benchmark_r2",
  ];
  if (
    runBody.status !== "completed" ||
    !runBody.run_id ||
    benchmark?.completed !== true ||
    comparison?.comparison_complete !== true ||
    comparison?.same_eligible_periods !== true ||
    comparison?.sample_scope !== "out_of_sample" ||
    comparison?.status !== "evaluated" ||
    comparison?.observations <= 0 ||
    !testPeriod ||
    testPeriod.sample_scope !== "out_of_sample" ||
    !numericComparisonKeys.every((key) => Number.isFinite(comparison[key])) ||
    !["mae", "rmse", "r2"].every((key) => Number.isFinite(testPeriod.benchmark_metrics?.[key])) ||
    !runBody.assumptions?.length ||
    !runBody.warnings?.length ||
    !runBody.limitations?.length ||
    !runBody.unsupported_claims?.length
  ) {
    throw new Error("The saved Run did not preserve complete benchmark and provenance data.");
  }

  const gatePayload = {
    name: "long_flat_moving_average",
    dataset_version_id: runBody.dataset_version_id,
    symbol: runBody.symbol,
    parameters: {
      predictive_model_evaluation: {
        benchmark,
        is_eligible_for_strategy: true,
      },
    },
  };
  const gateResponse = await fetch(
    `${apiBaseUrl}/api/projects/${projectId}/strategies/evaluate`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(gatePayload),
    },
  );
  const gateBody = await gateResponse.json();
  if (
    gateResponse.status !== 400 ||
    !String(gateBody.message ?? "").includes("persisted Predictive Model Run")
  ) {
    throw new Error("The MOD-009 Strategy gate accepted a caller-supplied model evaluation.");
  }

  const shot1 = path.join(SCREENSHOTS_DIR, "01_predictive_model_benchmark_overview.png");
  await page.screenshot({ path: shot1, fullPage: true });
  console.log(`Saved screenshot: ${shot1}`);

  const benchmarkCard = page.getByText("Naive Benchmark Comparison").first();
  if (!(await benchmarkCard.isVisible())) {
    throw new Error("Naive benchmark comparison was not shown after the Predictive Model Run.");
  }
  for (const marker of [
    page.getByText(/out-of-sample/i).first(),
    page.getByText("Assumptions", { exact: true }).first(),
    page.getByText("Warnings", { exact: true }).first(),
    page.getByText("Limitations", { exact: true }).first(),
    page.getByText("Unsupported Claims", { exact: true }).first(),
  ]) {
    if (!(await marker.isVisible())) {
      throw new Error("The Predictive Model Run did not show all benchmark provenance sections.");
    }
  }

  console.log("E2E browser verification completed successfully!");
  await browser.close();
  cleanup();
  process.exit(0);
}

run().catch((err) => {
  console.error("E2E verification error:", err);
  process.exit(1);
});
