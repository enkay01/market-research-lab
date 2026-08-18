import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { spawn } from "child_process";

const SCREENSHOTS_DIR = "C:/Users/stroo/.gemini/antigravity/brain/1f92e451-e362-4153-a1d8-1a98e66e6901/screenshots";
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

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
  const worktreeRoot = path.resolve(process.cwd(), "..");
  const engineProc = spawn(
    "uv",
    ["run", "--project", "engine", "python", "-m", "uvicorn", "market_research_lab.api:app", "--host", "127.0.0.1", "--port", "8000"],
    {
      cwd: worktreeRoot,
      shell: true,
      stdio: "inherit",
    }
  );

  const webProc = spawn("npx", ["vite", "--port", "5173"], {
    cwd: process.cwd(),
    shell: true,
    stdio: "inherit",
  });

  const cleanup = () => {
    try { engineProc.kill(); } catch {}
    try { webProc.kill(); } catch {}
  };
  process.on("exit", cleanup);
  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);

  await waitForServer("http://127.0.0.1:8000/api/health");
  await waitForServer("http://127.0.0.1:5173");
  console.log("Servers are up and ready.");

  console.log("2. Launching Playwright Chromium browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  page.on("console", (msg) => console.log("Browser console:", msg.text()));

  console.log("3. Navigating to http://127.0.0.1:5173 ...");
  await page.goto("http://127.0.0.1:5173", { waitUntil: "networkidle" });
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
    const sampleCsv = path.join(process.cwd(), "sample_market_data.csv");
    let csvData = "symbol,name,exchange,currency,date,open,high,low,close,volume,available_at\n";
    let base = 100.0;
    for (let d = 1; d <= 40; d++) {
      const monthStr = d <= 31 ? "01" : "02";
      const fullDate = `2024-${monthStr}-${String(d <= 31 ? d : d - 31).padStart(2, "0")}`;
      const availStr = `${fullDate}T21:00:00Z`;
      base += (d % 2 === 0 ? 1.5 : -0.8);
      csvData += `AAPL,Apple Inc,NASDAQ,USD,${fullDate},${base.toFixed(2)},${(base + 2).toFixed(2)},${(base - 1).toFixed(2)},${(base + 0.5).toFixed(2)},5000000,${availStr}\n`;
    }
    fs.writeFileSync(sampleCsv, csvData);

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
  if (await predictiveTab.isVisible()) {
    await predictiveTab.click();
    await page.waitForTimeout(1000);
  }

  console.log("7. Running Predictive Model with Naive Benchmark...");
  const runModelBtn = page.getByRole("button", { name: /Run & Save Model|Run Model/i }).first();
  await runModelBtn.click();
  await page.waitForTimeout(3000);

  const shot1 = path.join(SCREENSHOTS_DIR, "01_predictive_model_benchmark_overview.png");
  await page.screenshot({ path: shot1, fullPage: true });
  console.log(`Saved screenshot: ${shot1}`);

  // Switch to Strategies Tab
  console.log("8. Navigating to Strategies tab to verify MOD-009 strategy evaluation...");
  const strategiesTab = page.locator("button").filter({ hasText: /Strategies/i }).first();
  if (await strategiesTab.isVisible()) {
    await strategiesTab.click();
    await page.waitForTimeout(1000);
  }

  // Select Predictive Return Threshold Strategy
  const stratSelector = page.getByRole("combobox", { name: "Strategy" });
  if (await stratSelector.isVisible()) {
    await stratSelector.click();
    await page.waitForTimeout(300);
    const predStratOpt = page.getByRole("option", { name: /Predictive Return Threshold/i });
    if (await predStratOpt.isVisible()) {
      await predStratOpt.click();
      await page.waitForTimeout(500);
    }
  }

  const evalStratBtn = page.getByRole("button", { name: "Evaluate Strategy" }).first();
  if (await evalStratBtn.isVisible()) {
    await evalStratBtn.click();
    await page.waitForTimeout(2000);
  }

  const shot2 = path.join(SCREENSHOTS_DIR, "02_predictive_strategy_evaluation.png");
  await page.screenshot({ path: shot2, fullPage: true });
  console.log(`Saved screenshot: ${shot2}`);

  console.log("E2E browser verification completed successfully!");
  await browser.close();
  cleanup();
  process.exit(0);
}

run().catch((err) => {
  console.error("E2E verification error:", err);
  process.exit(1);
});
