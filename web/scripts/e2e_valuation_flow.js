import { chromium } from "playwright";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";

const SCREENSHOTS_DIR = "C:/Users/stroo/.gemini/antigravity/brain/9b834304-e384-4e15-bc26-1927768ea0a3/screenshots";
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

async function run() {
  console.log("1. Starting backend server on port 8000...");
  const server = spawn(
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
      "8000",
    ],
    { cwd: "d:/stroo/Documents/GitHub/market-research-lab", stdio: "inherit" }
  );

  let online = false;
  for (let i = 0; i < 40; i++) {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/health");
      if (res.ok) {
        online = true;
        break;
      }
    } catch {
      await new Promise((r) => setTimeout(r, 400));
    }
  }

  if (!online) {
    server.kill();
    throw new Error("Server failed to start on port 8000");
  }
  console.log("Backend server is online.");

  try {
    // 2. Ingest market data for AAPL, MSFT, NVDA
    console.log("2. Ingesting market bars and fundamentals...");
    const barsCsv = `symbol,name,exchange,currency,session_date,open,high,low,close,volume,available_at
AAPL,Apple Inc.,NASDAQ,USD,2026-08-01,200.0,205.0,198.0,200.0,50000000,2026-08-01T20:00:00Z
MSFT,Microsoft Corp.,NASDAQ,USD,2026-08-01,400.0,405.0,398.0,400.0,20000000,2026-08-01T20:00:00Z
NVDA,NVIDIA Corp.,NASDAQ,USD,2026-08-01,100.0,105.0,98.0,100.0,80000000,2026-08-01T20:00:00Z
`;
    const barsFormData = new FormData();
    barsFormData.append("source", "e2e_bars");
    barsFormData.append("file", new Blob([barsCsv], { type: "text/csv" }), "bars.csv");
    await fetch("http://127.0.0.1:8000/api/datasets", {
      method: "POST",
      body: barsFormData,
    });

    const fundamentalsCsv = `symbol,field,fiscal_period,value,unit,available_at
AAPL,shares_outstanding,2026Q2,15.0,share,2026-07-15T00:00:00Z
AAPL,total_debt,2026Q2,100.0,USD,2026-07-15T00:00:00Z
AAPL,cash,2026Q2,50.0,USD,2026-07-15T00:00:00Z
AAPL,revenue,2026Q2,400.0,USD,2026-07-15T00:00:00Z
AAPL,ebitda,2026Q2,120.0,USD,2026-07-15T00:00:00Z
AAPL,net_income,2026Q2,100.0,USD,2026-07-15T00:00:00Z
AAPL,free_cash_flow,2026Q2,90.0,USD,2026-07-15T00:00:00Z
MSFT,shares_outstanding,2026Q2,7.5,share,2026-07-15T00:00:00Z
MSFT,total_debt,2026Q2,80.0,USD,2026-07-15T00:00:00Z
MSFT,cash,2026Q2,60.0,USD,2026-07-15T00:00:00Z
MSFT,revenue,2026Q2,250.0,USD,2026-07-15T00:00:00Z
MSFT,ebitda,2026Q2,125.0,USD,2026-07-15T00:00:00Z
MSFT,net_income,2026Q2,80.0,USD,2026-07-15T00:00:00Z
MSFT,free_cash_flow,2026Q2,70.0,USD,2026-07-15T00:00:00Z
NVDA,shares_outstanding,2026Q2,25.0,share,2026-07-15T00:00:00Z
NVDA,total_debt,2026Q2,10.0,USD,2026-07-15T00:00:00Z
NVDA,cash,2026Q2,30.0,USD,2026-07-15T00:00:00Z
NVDA,revenue,2026Q2,300.0,USD,2026-07-15T00:00:00Z
NVDA,ebitda,2026Q2,180.0,USD,2026-07-15T00:00:00Z
NVDA,net_income,2026Q2,150.0,USD,2026-07-15T00:00:00Z
NVDA,free_cash_flow,2026Q2,140.0,USD,2026-07-15T00:00:00Z
`;
    const fundFormData = new FormData();
    fundFormData.append("source", "e2e_fundamentals");
    fundFormData.append("file", new Blob([fundamentalsCsv], { type: "text/csv" }), "fundamentals.csv");
    await fetch("http://127.0.0.1:8000/api/datasets", {
      method: "POST",
      body: fundFormData,
    });

    // 3. Create project
    console.log("3. Creating Valuation Research project...");
    const projRes = await fetch("http://127.0.0.1:8000/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Valuation Lab Fund" }),
    });
    const project = await projRes.json();
    console.log(`Created project: ${project.id} - ${project.name}`);

    // 4. Launch browser walkthrough
    console.log("4. Starting Playwright browser...");
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();

    // Start Vite preview or connect to local dev
    await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_initial_dashboard.png") });

    // Navigate to Valuations tab
    console.log("5. Navigating to Valuations tab...");
    const valuationTab = page.getByRole("tab", { name: "Valuation" });
    if (await valuationTab.count()) {
      await valuationTab.click();
    } else {
      await page.click("text=Valuation");
    }
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_valuation_view.png") });

    // Select peer securities (MSFT & NVDA)
    console.log("6. Selecting peer securities...");
    const msftCheckbox = page.locator('input[type="checkbox"][value="MSFT"]');
    if (await msftCheckbox.count()) {
      await msftCheckbox.check();
    } else {
      await page.click("text=MSFT");
    }

    const nvdaCheckbox = page.locator('input[type="checkbox"][value="NVDA"]');
    if (await nvdaCheckbox.count()) {
      await nvdaCheckbox.check();
    } else {
      await page.click("text=NVDA");
    }
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_peers_selected.png") });

    // Click Calculate
    console.log("7. Calculating Comparable-Company Valuation...");
    await page.click('button:has-text("Calculate")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_valuation_calculated.png") });

    // Click Save Revision
    console.log("8. Saving Valuation Revision...");
    await page.click('button:has-text("Save Revision")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_revision_saved.png") });

    console.log("E2E valuation test flow completed successfully!");
    await browser.close();
  } finally {
    server.kill();
  }
}

run().catch((err) => {
  console.error("E2E test failed:", err);
  process.exit(1);
});
