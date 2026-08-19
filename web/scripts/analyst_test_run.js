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
const SCREENSHOTS_DIR = path.resolve(WORKTREE_ROOT, "docs", "images");
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

async function findFreePort(environmentVariable) {
  const configuredPort = process.env[environmentVariable];
  if (configuredPort) return configuredPort;
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? String(address.port) : null;
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
  console.log("Starting analyst session...");
  const apiPort = await findFreePort("MARKET_RESEARCH_LAB_API_PORT");
  const webPort = await findFreePort("MARKET_RESEARCH_LAB_WEB_PORT");
  process.env.MARKET_RESEARCH_LAB_API_PORT = apiPort;
  process.env.MARKET_RESEARCH_LAB_WEB_PORT = webPort;

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
  console.log("Servers online.");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  console.log("Navigating to app...");
  await page.goto(webBaseUrl, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // 1. Create Analyst Project
  console.log("Creating analyst project...");
  const plusBtn = page.getByRole("button", { name: "+", exact: true });
  if (await plusBtn.isVisible()) {
    await plusBtn.click();
    await page.waitForTimeout(500);
    const projInput = page.getByLabel("Project Name");
    await projInput.fill("Bornholdt Potts Research");
    await page.getByRole("button", { name: "Create Project" }).click();
    await page.waitForTimeout(1000);
  }

  // 2. Ingest Market Data
  console.log("Importing market data...");
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

  // 3. Models & Indicators -> Predictive Models
  console.log("Testing Potts Model on AAPL...");
  await page.getByRole("button", { name: "Models & Indicators" }).click();
  await page.waitForTimeout(1000);

  const predictiveTab = page.locator("button").filter({ hasText: /Predictive Models/i }).first();
  await predictiveTab.click();
  await page.waitForTimeout(1000);

  const selectElement = page.locator("select").filter({ hasText: /Momentum Return Regression|Potts/i }).first();
  if (await selectElement.isVisible()) {
    await selectElement.selectOption("potts_gain_loss_asymmetry");
  } else {
    const selectorBtn = page.locator("button").filter({ hasText: /Momentum Return Regression/i }).first();
    if (await selectorBtn.isVisible()) {
      await selectorBtn.click();
      await page.waitForTimeout(500);
      const option = page.locator("button, li, div").filter({ hasText: /^Potts Gain-Loss Asymmetry$/i }).first();
      await option.click();
    }
  }
  await page.waitForTimeout(1000);

  console.log("Executing Potts model run...");
  const runModelBtn = page.getByRole("button", { name: /Run & Save Model|Run Model/i }).first();
  await runModelBtn.click();
  await page.waitForTimeout(3000);

  const shot1 = path.join(SCREENSHOTS_DIR, "analyst_potts_model_evaluation.png");
  await page.screenshot({ path: shot1, fullPage: true });
  console.log(`Saved screenshot: ${shot1}`);

  // 4. Test Strategies -> Combined Predictive Model
  console.log("Evaluating Combined Predictive Model Strategy...");
  const strategiesTab = page.locator("button").filter({ hasText: /Strategies/i }).first();
  await strategiesTab.click();
  await page.waitForTimeout(1000);

  const strategySelect = page.locator("select").filter({ hasText: /Moving Average|Combined/i }).first();
  if (await strategySelect.isVisible()) {
    await strategySelect.selectOption("combined_predictive_model");
  } else {
    const stratBtn = page.locator("button").filter({ hasText: /Moving Average/i }).first();
    if (await stratBtn.isVisible()) {
      await stratBtn.click();
      await page.waitForTimeout(500);
      const opt = page.locator("button, li, div").filter({ hasText: /^Combined Predictive Model$/i }).first();
      await opt.click();
    }
  }
  await page.waitForTimeout(1000);

  const evalStrategyBtn = page.getByRole("button", { name: /Evaluate Strategy/i }).first();
  await evalStrategyBtn.click();
  await page.waitForTimeout(2000);

  const shot2 = path.join(SCREENSHOTS_DIR, "analyst_combined_strategy_evaluation.png");
  await page.screenshot({ path: shot2, fullPage: true });
  console.log(`Saved screenshot: ${shot2}`);

  // 5. Run Strategy on Backtest View
  console.log("Navigating to Backtests View...");
  await page.getByRole("button", { name: "Backtests" }).click();
  await page.waitForTimeout(1500);

  const runBacktestBtn = page.getByRole("button", { name: /Run Backtest|Execute/i }).first();
  if (await runBacktestBtn.isVisible()) {
    console.log("Executing backtest...");
    await runBacktestBtn.click();
    await page.waitForTimeout(3000);
  }

  const shot3 = path.join(SCREENSHOTS_DIR, "analyst_backtest_view.png");
  await page.screenshot({ path: shot3, fullPage: true });
  console.log(`Saved screenshot: ${shot3}`);

  console.log("Analyst session completed successfully.");
  await browser.close();
  cleanup();
  process.exit(0);
}

run().catch((err) => {
  console.error("Analyst test error:", err);
  process.exit(1);
});
