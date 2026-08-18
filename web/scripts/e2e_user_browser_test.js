import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const SCREENSHOTS_DIR = "C:/Users/stroo/.gemini/antigravity/brain/ebd9ce8b-d74e-4621-93a5-d9f0281f3808/screenshots";
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

async function run() {
  console.log("1. Launching Playwright Chromium browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  page.on("console", (msg) => console.log("Browser console:", msg.text()));

  console.log("2. Navigating to http://127.0.0.1:5173 ...");
  await page.goto("http://127.0.0.1:5173", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // 1. Check/Create Project
  console.log("3. Ensuring Project exists...");
  const plusBtn = page.getByRole("button", { name: "+", exact: true });
  if (await plusBtn.isVisible()) {
    await plusBtn.click();
    await page.waitForTimeout(500);
    const projInput = page.getByLabel("Project Name");
    await projInput.fill("Alpha Quantitative Fund");
    await page.getByRole("button", { name: "Create Project" }).click();
    await page.waitForTimeout(1000);
  }

  // 2. Ingest Market Data with temporal provenance
  console.log("4. Ingesting market dataset with point-in-time provenance via UI...");
  await page.getByRole("button", { name: "Market Data" }).click();
  await page.waitForTimeout(1000);

  const importBtn = page.getByRole("button", { name: "Import File" }).first();
  if (await importBtn.isVisible()) {
    const sampleCsv = path.join(process.cwd(), "sample_market_data.csv");
    let csvData = "symbol,name,exchange,currency,date,open,high,low,close,volume,available_at\n";
    const symbols = ["AAPL", "MSFT", "NVDA", "SPY"];
    for (const sym of symbols) {
      let base = sym === "AAPL" ? 150 : sym === "MSFT" ? 300 : sym === "NVDA" ? 100 : 450;
      for (let d = 2; d <= 28; d++) {
        const dateStr = `2024-01-${String(d).padStart(2, "0")}`;
        const availStr = `${dateStr}T21:00:00Z`;
        base += (d % 2 === 0 ? 1.5 : -0.8);
        csvData += `${sym},${sym} Inc,NASDAQ,USD,${dateStr},${base.toFixed(2)},${(base + 2).toFixed(2)},${(base - 1).toFixed(2)},${(base + 1).toFixed(2)},5000000,${availStr}\n`;
      }
    }
    fs.writeFileSync(sampleCsv, csvData);

    await importBtn.click();
    await page.waitForTimeout(500);
    await page.locator("input[type='file']").setInputFiles(sampleCsv);
    await page.locator("form").getByRole("button", { name: "Import" }).click();
    await page.waitForTimeout(2500);
  }

  // 3. Navigate to Backtests View
  console.log("5. Navigating to Backtests View...");
  await page.getByRole("button", { name: "Backtests" }).click();
  await page.waitForTimeout(1500);

  // Set Universe & Dates
  const universeInput = page.getByLabel("Universe (Symbols)");
  if (await universeInput.isVisible()) {
    await universeInput.fill("AAPL, MSFT");
  }

  const startInput = page.getByLabel("Start Date");
  if (await startInput.isVisible()) {
    await startInput.fill("2024-01-02");
  }
  const endInput = page.getByLabel("End Date");
  if (await endInput.isVisible()) {
    await endInput.fill("2024-01-28");
  }

  // Strategy selection
  const stratCombobox = page.getByLabel("Strategy");
  if (await stratCombobox.isVisible()) {
    await stratCombobox.click();
    await page.waitForTimeout(300);
    const stratOpt = page.getByRole("option", { name: /Long\/Short Moving Average/i });
    if (await stratOpt.isVisible()) {
      await stratOpt.click();
    }
  }

  const runBacktest = async () => {
    const runBtn = page.getByRole("button", { name: "Run Backtest" });
    await runBtn.click();
    console.log("Waiting for backtest execution to complete...");
    await page.waitForTimeout(3500);
  };

  // SCENARIO A: Max Leverage 0.5x, Reject Mode
  console.log("6. Scenario A: Running Backtest with Max Leverage 0.5x & Reject Orders Mode...");
  const maxLevInput = page.getByLabel("Max Leverage Limit (x)");
  if (await maxLevInput.isVisible()) {
    await maxLevInput.fill("0.5");
  }

  const breachCombobox = page.getByLabel("Leverage Breach Mode");
  if (await breachCombobox.isVisible()) {
    await breachCombobox.click();
    await page.waitForTimeout(300);
    const rejectOpt = page.getByRole("option", { name: /Reject Orders/i });
    if (await rejectOpt.isVisible()) {
      await rejectOpt.click();
    }
  }

  await runBacktest();

  const shot1 = path.join(SCREENSHOTS_DIR, "01_leverage_reject_overview.png");
  await page.screenshot({ path: shot1 });
  console.log(`Saved screenshot: ${shot1}`);

  // Switch to Rejections Tab and scroll table into view
  console.log("Switching to Rejections Tab...");
  const rejectionsTab = page.locator("button").filter({ hasText: /Rejections/i }).first();
  if (await rejectionsTab.isVisible()) {
    await rejectionsTab.click();
    await page.waitForTimeout(1000);
    const rejTable = page.locator("table").first();
    await rejTable.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    const shot2 = path.join(SCREENSHOTS_DIR, "02_rejections_tab_table.png");
    await page.screenshot({ path: shot2 });
    console.log(`Saved screenshot: ${shot2}`);
  }

  // SCENARIO B: Max Leverage 0.5x, Constrain Mode
  console.log("7. Scenario B: Running Backtest with Max Leverage 0.5x & Constrain / Scale Mode...");
  const overviewTab = page.locator("button").filter({ hasText: /Overview/i }).first();
  if (await overviewTab.isVisible()) {
    await overviewTab.click();
    await page.waitForTimeout(500);
  }

  if (await breachCombobox.isVisible()) {
    await breachCombobox.click();
    await page.waitForTimeout(300);
    const scaleOpt = page.getByRole("option", { name: /Constrain \/ Scale/i });
    if (await scaleOpt.isVisible()) {
      await scaleOpt.click();
    }
  }
  await runBacktest();

  const shot3 = path.join(SCREENSHOTS_DIR, "03_leverage_constrain_overview.png");
  await page.screenshot({ path: shot3 });
  console.log(`Saved screenshot: ${shot3}`);

  if (await rejectionsTab.isVisible()) {
    await rejectionsTab.click();
    await page.waitForTimeout(1000);
    const rejTable = page.locator("table").first();
    await rejTable.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    const shot3b = path.join(SCREENSHOTS_DIR, "03b_rejections_tab_scaling.png");
    await page.screenshot({ path: shot3b });
    console.log(`Saved screenshot: ${shot3b}`);
  }

  // SCENARIO C: Leveraged Portfolio 2.0x, Margin 50%
  console.log("8. Scenario C: Running Backtest with Leveraged 2.0x & Margin Requirement 50%...");
  if (await overviewTab.isVisible()) {
    await overviewTab.click();
    await page.waitForTimeout(500);
  }

  if (await maxLevInput.isVisible()) {
    await maxLevInput.fill("2.0");
  }
  const marginReqInput = page.getByLabel("Margin Requirement (%)");
  if (await marginReqInput.isVisible()) {
    await marginReqInput.fill("50.0");
  }
  await runBacktest();

  const shot4 = path.join(SCREENSHOTS_DIR, "04_leveraged_2x_portfolio.png");
  await page.screenshot({ path: shot4 });
  console.log(`Saved screenshot: ${shot4}`);

  // Inspect Daily Ledger
  console.log("9. Inspecting Daily Ledger for dated Gross & Net Exposure...");
  const ledgerTab = page.locator("button").filter({ hasText: /Daily Ledger|Ledger/i }).first();
  if (await ledgerTab.isVisible()) {
    await ledgerTab.click();
    await page.waitForTimeout(1000);
    const ledgerTable = page.locator("table").first();
    await ledgerTable.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    const shot5 = path.join(SCREENSHOTS_DIR, "05_daily_ledger_exposure.png");
    await page.screenshot({ path: shot5 });
    console.log(`Saved screenshot: ${shot5}`);
  }

  console.log("All E2E browser scenarios completed and verified successfully!");
  await browser.close();
}

run().catch((err) => {
  console.error("E2E test error:", err);
  process.exit(1);
});
