import { chromium } from "playwright";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";

const SCREENSHOTS_DIR = "C:/Users/stroo/.gemini/antigravity/brain/7ea8d8f3-428b-4772-9a29-d1a7064a6267/screenshots";
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

async function run() {
  console.log("1. Starting backend server on port 8000...");
  const server = spawn(
    "uv",
    ["run", "--project", "engine", "python", "-m", "uvicorn", "market_research_lab.api:app", "--host", "127.0.0.1", "--port", "8000"],
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

  // Seed sample dataset
  console.log("2. Ingesting sample market dataset...");
  const csvContent = `symbol,name,exchange,currency,date,open,high,low,close,volume
AAPL,Apple Inc.,NASDAQ,USD,2026-08-01,215.0,220.5,214.2,219.8,45000000
AAPL,Apple Inc.,NASDAQ,USD,2026-08-02,220.0,224.1,219.5,223.4,48000000
MSFT,Microsoft Corporation,NASDAQ,USD,2026-08-01,440.0,448.0,439.1,446.5,22000000
NVDA,NVIDIA Corporation,NASDAQ,USD,2026-08-01,120.0,125.0,119.5,124.2,85000000
SPY,SPDR S&P 500 ETF Trust,NYSE Arca,USD,2026-08-01,550.0,554.0,549.2,553.1,35000000
`;
  const formData = new FormData();
  formData.append("source", "seed_e2e_dataset");
  formData.append("file", new Blob([csvContent], { type: "text/csv" }), "seed_market_data.csv");
  await fetch("http://127.0.0.1:8000/api/datasets", {
    method: "POST",
    body: formData,
  });

  // Seed project
  console.log("3. Ensuring project exists...");
  const projRes = await fetch("http://127.0.0.1:8000/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Alpha Tech & Macro Fund" }),
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

    // Screenshot 1: Initial View
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01_initial_data_view.png") });
    console.log("Captured 01_initial_data_view.png");

    // Switch to Security Research tab
    console.log("6. Switching to Security Research tab...");
    await page.locator('button:has-text("Security Research")').click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02_research_empty_state.png") });
    console.log("Captured 02_research_empty_state.png");

    // Open Add Security Dialog
    console.log("7. Opening Add Security Dialog...");
    await page.locator('button:has-text("+ Add Security")').click();
    await page.waitForTimeout(800);

    // Search catalogue for "Apple"
    console.log("8. Searching catalogue for Apple...");
    await page.keyboard.type("Apple", { delay: 20 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03_catalogue_search_modal.png") });
    console.log("Captured 03_catalogue_search_modal.png");

    // Add AAPL using exact button match
    console.log("9. Adding AAPL to watchlist...");
    await page.locator('button').filter({ hasText: /^Add$/ }).first().click();
    await page.waitForTimeout(1000);

    // Add MSFT
    await page.locator('button:has-text("+ Add Security")').click();
    await page.waitForTimeout(600);
    await page.keyboard.type("MSFT", { delay: 20 });
    await page.waitForTimeout(600);
    await page.locator('button').filter({ hasText: /^Add$/ }).first().click();
    await page.waitForTimeout(1000);

    // Add NVDA
    await page.locator('button:has-text("+ Add Security")').click();
    await page.waitForTimeout(600);
    await page.keyboard.type("NVDA", { delay: 20 });
    await page.waitForTimeout(600);
    await page.locator('button').filter({ hasText: /^Add$/ }).first().click();
    await page.waitForTimeout(1000);

    // Try uncatalogued search
    await page.locator('button:has-text("+ Add Security")').click();
    await page.waitForTimeout(600);
    await page.keyboard.type("UNREGISTERED_CO", { delay: 20 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04_uncatalogued_search.png") });
    console.log("Captured 04_uncatalogued_search.png");
    await page.locator('button').filter({ hasText: /^Close$/ }).first().click();
    await page.waitForTimeout(600);

    // Watchlist table
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05_populated_watchlist.png") });
    console.log("Captured 05_populated_watchlist.png");

    // Filter watchlist by search query
    console.log("10. Testing filter query...");
    await page.locator('input[placeholder*="Filter watchlist"]').fill("Apple");
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06_filtered_watchlist.png") });
    console.log("Captured 06_filtered_watchlist.png");

    // Clear filter
    await page.locator('input[placeholder*="Filter watchlist"]').fill("");
    await page.waitForTimeout(600);

    // Select AAPL
    console.log("11. Selecting AAPL and editing thesis...");
    await page.locator('text=Apple Inc.').first().click();
    await page.waitForTimeout(800);

    const thesisText = `# Research Thesis: AAPL (Apple Inc.)

## Summary
Apple maintains unmatched high-margin ecosystem retention with expanding services revenue ($100B+ run-rate) and hardware installed base exceeding 2.2B active devices.

## Evidence
- Active installed base crossed 2.2 billion active devices globally.
- Services gross margin exceeds 74%, growing double digits YoY.
- Consistent annual share repurchases exceeding $80B.

## Risks
- Antitrust scrutiny over App Store fees and default search agreements.
- Smartphone replacement cycle elongation in developed markets.

## Catalysts
- Apple Intelligence rollout driving accelerated iPhone 16/17 upgrade cycle.
- Spatial computing and generative AI monetization across services.

## Assumptions
- Terminal growth rate of 3.0% and WACC of 8.5%.
`;
    const thesisArea = page.locator('textarea');
    await thesisArea.fill(thesisText);
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07_thesis_editor_mode.png") });
    console.log("Captured 07_thesis_editor_mode.png");

    // Switch to Preview mode
    console.log("12. Switching to Preview mode...");
    await page.locator('button:has-text("Preview")').click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08_thesis_preview_mode.png") });
    console.log("Captured 08_thesis_preview_mode.png");

    // Click Save Thesis
    console.log("13. Saving thesis...");
    await page.locator('button:has-text("Save Thesis")').click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09_thesis_saved_with_data_linkage.png") });
    console.log("Captured 09_thesis_saved_with_data_linkage.png");

    // Final verified state
    console.log("14. Final verified state...");
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "10_final_verified_flow.png") });
    console.log("Captured 10_final_verified_flow.png");

    console.log("All end-to-end browser steps executed successfully!");
  } finally {
    await browser.close();
    server.kill();
  }
}

run().catch((err) => {
  console.error("Browser flow error:", err);
  process.exit(1);
});
