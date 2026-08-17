import { chromium } from "playwright";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";

const SCREENSHOTS_DIR = "C:/Users/stroo/.gemini/antigravity/brain/a7e60a11-936c-441d-a94c-567fee262ef6/screenshots";
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
    { cwd: "d:/stroo/Documents/GitHub/market-research-lab", stdio: "inherit", shell: true }
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

  console.log("1b. Starting Vite dev server on port 5173...");
  const vite = spawn(
    "npm",
    ["run", "dev", "--", "--port", "5173"],
    { cwd: "d:/stroo/Documents/GitHub/market-research-lab/web", stdio: "inherit", shell: true }
  );

  let viteOnline = false;
  for (let i = 0; i < 40; i++) {
    try {
      const res = await fetch("http://localhost:5173");
      if (res.ok) {
        viteOnline = true;
        break;
      }
    } catch {
      await new Promise((r) => setTimeout(r, 400));
    }
  }

  if (!viteOnline) {
    vite.kill();
    server.kill();
    throw new Error("Vite failed to start on port 5173");
  }
  console.log("Vite dev server is online.");

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
      body: JSON.stringify({ name: "Epic 3 Valuation Suite" }),
    });
    const project = await projRes.json();
    console.log(`Created project: ${project.id} - ${project.name}`);

    // 4. Launch browser walkthrough
    console.log("4. Starting Playwright browser...");
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();

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

    // 6. Test FCFF DCF Calculation
    console.log("6. Testing FCFF DCF Calculation...");
    await page.click('button:has-text("Calculate")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_dcf_valuation_calculated.png") });

    // 7. Save DCF Revision v1
    console.log("7. Saving FCFF DCF Revision v1...");
    await page.click('button:has-text("Save Revision")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_dcf_revision1_saved.png") });

    // 8. Edit Revenue Growth and Save DCF Revision v2
    console.log("8. Modifying assumptions and saving Revision v2...");
    const revGrowthInput = page.locator('input').nth(1); // Revenue growth input
    await revGrowthInput.fill("12.0");
    await page.waitForTimeout(500);
    await page.click('button:has-text("Save Revision")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_dcf_revision2_saved.png") });

    // 9. Switch to Comparables tab
    console.log("9. Testing Trading Comparables...");
    await page.getByText("Comparables", { exact: true }).click();
    await page.waitForTimeout(1000);

    // Select peer securities (MSFT)
    const msftItem = page.locator('li:has-text("MSFT")');
    if (await msftItem.count()) {
      await msftItem.first().click();
    }
    await page.waitForTimeout(500);
    await page.click('button:has-text("Calculate")');
    await page.waitForTimeout(1500);
    await page.click('button:has-text("Save Revision")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_comparables_saved.png") });

    // 10. Switch to Side-by-Side Comparison tab
    console.log("10. Testing Side-by-Side Comparison...");
    await page.getByText("Compare Revisions", { exact: true }).click();
    await page.waitForTimeout(1000);

    // Check all saved runs by clicking each list item
    const runItems = page.locator('li[data-pressable-container="true"]');
    const count = await runItems.count();
    console.log(`Found ${count} saved run items`);
    for (let i = 0; i < count; i++) {
      await runItems.nth(i).click();
    }
    await page.waitForTimeout(500);
    await page.click('button:has-text("Compare Selected Valuations")');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_valuation_comparison_view.png") });

    console.log("E2E valuation test flow completed successfully!");
    await browser.close();
  } finally {
    vite.kill();
    server.kill();
  }
}

run().catch((err) => {
  console.error("E2E test failed:", err);
  process.exit(1);
});
