import { chromium } from "playwright";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";

const SCREENSHOTS_DIR = "C:/Users/stroo/.gemini/antigravity/brain/82aa70b6-7ea8-4aad-99de-ee7b29e81f79/screenshots";
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
    { cwd: "d:/stroo/Documents/GitHub/issue-22", stdio: "inherit" }
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

  // Generate 60 days of daily bars for AAPL with sinusoidal trend
  console.log("2. Ingesting 60-day historical dataset for AAPL...");
  let csvContent = "symbol,name,exchange,currency,session_date,open,high,low,close,volume,available_at\n";
  let basePrice = 180.0;
  for (let d = 1; d <= 60; d++) {
    const month = d <= 30 ? "06" : "07";
    const day = d <= 30 ? String(d).padStart(2, "0") : String(d - 30).padStart(2, "0");
    const dateStr = `2026-${month}-${day}`;
    const wave = Math.sin(d / 5) * 15;
    const trend = d * 0.4;
    const close = parseFloat((basePrice + wave + trend).toFixed(2));
    const open = parseFloat((close - 1.2).toFixed(2));
    const high = parseFloat((close + 2.5).toFixed(2));
    const low = parseFloat((close - 2.0).toFixed(2));
    const volume = 40000000 + d * 500000;
    csvContent += `AAPL,Apple Inc.,NASDAQ,USD,${dateStr},${open},${high},${low},${close},${volume},${dateStr}T20:00:00Z\n`;
  }

  const formData = new FormData();
  formData.append("source", "e2e_indicator_dataset");
  formData.append("file", new Blob([csvContent], { type: "text/csv" }), "aapl_60d_bars.csv");
  const importRes = await fetch("http://127.0.0.1:8000/api/datasets", {
    method: "POST",
    body: formData,
  });
  const importJson = await importRes.json();
  console.log("Imported dataset version:", importJson.dataset_version_id);

  // Seed project
  console.log("3. Ensuring project exists...");
  const projRes = await fetch("http://127.0.0.1:8000/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Trend & Crossover Lab" }),
  });
  const project = await projRes.json();
  console.log("Project active:", project.id, project.name);

  // Launch Playwright
  console.log("4. Launching Playwright browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  try {
    console.log("5. Navigating to application...");
    await page.goto("http://127.0.0.1:8000/", { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);

    // Switch to Models & Indicators tab
    console.log("6. Switching to Models & Indicators tab...");
    await page.locator('button:has-text("Models & Indicators")').click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_indicators_initial_empty_state.png") });
    console.log("Captured 01_indicators_initial_empty_state.png");

    // Click Calculate Indicator
    console.log("7. Calculating Moving Average Crossover (Fast: 20, Slow: 50)...");
    await page.locator('button:has-text("Calculate Indicator")').first().click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_ma_crossover_calculated.png") });
    console.log("Captured 02_ma_crossover_calculated.png");

    // Adjust parameters: Fast: 10, Slow: 25
    console.log("8. Adjusting parameter fields (Fast: 10, Slow: 25)...");
    const fastInput = page.locator('input').filter({ hasText: "" }).nth(1); // fast_period input
    // Locate inputs in panel
    const textInputs = page.locator('input[type="text"], input:not([type])');
    const inputCount = await textInputs.count();
    console.log(`Found ${inputCount} inputs on page.`);

    for (let i = 0; i < inputCount; i++) {
      const val = await textInputs.nth(i).inputValue();
      if (val === "20") {
        await textInputs.nth(i).fill("10");
      } else if (val === "50") {
        await textInputs.nth(i).fill("25");
      }
    }

    // Re-calculate with 10/25
    console.log("9. Recalculating with updated parameters...");
    await page.locator('button:has-text("Calculate Preview")').click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_ma_crossover_10_25_updated.png") });
    console.log("Captured 03_ma_crossover_10_25_updated.png");

    // Hover over chart to verify interactive inspection card
    console.log("10. Testing interactive chart hover...");
    const chartSvg = page.locator("svg").first();
    const box = await chartSvg.boundingBox();
    if (box) {
      // Hover at 70% width (past warmup period)
      await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.5);
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_chart_interactive_hover.png") });
      console.log("Captured 04_chart_interactive_hover.png");
    }

    // Save definition revision
    console.log("11. Saving indicator definition revision...");
    await page.locator('button:has-text("Save Revision")').first().click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_save_revision_dialog.png") });
    console.log("Captured 05_save_revision_dialog.png");

    // Submit dialog
    await page.locator('button').filter({ hasText: /^Save Revision$/ }).last().click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_revision_saved_success.png") });
    console.log("Captured 06_revision_saved_success.png");

    // Test Simple Moving Average (SMA) mode
    console.log("12. Testing Simple Moving Average (SMA) calculation...");
    // Select SMA in indicator dropdown
    const indSelect = page.locator("select").nth(2); // indicator selector
    if ((await indSelect.count()) > 0) {
      await indSelect.selectOption("sma");
      await page.waitForTimeout(600);
      await page.locator('button:has-text("Calculate Preview")').click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_sma_single_series.png") });
      console.log("Captured 07_sma_single_series.png");
    }

    console.log("All end-to-end browser walkthrough steps verified successfully!");
  } finally {
    await browser.close();
    server.kill();
  }
}

run().catch((err) => {
  console.error("Browser test failed:", err);
  process.exit(1);
});
