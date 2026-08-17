import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

async function main() {
  const outDir = 'C:/Users/stroo/.gemini/antigravity/brain/af29b08a-d657-4d29-a3df-51f3fb9a33f4';
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  console.log('Navigating to http://127.0.0.1:8000 ...');
  await page.goto('http://127.0.0.1:8000');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Take screenshot of main landing view
  await page.screenshot({ path: path.join(outDir, 'shot_01_landing.png') });

  // Navigate to Backtests view
  console.log('Navigating to Backtests...');
  await page.getByText('Backtests', { exact: true }).click();
  await page.waitForTimeout(800);

  // Set multi-symbol universe and benchmark
  console.log('Filling simulation setup...');
  const universeInput = page.getByLabel('Universe (Comma-separated symbols)');
  if (await universeInput.isVisible()) {
    await universeInput.fill('AAPL, MSFT');
  }

  const benchmarkInput = page.getByLabel('Benchmark Symbol (Optional)');
  if (await benchmarkInput.isVisible()) {
    await benchmarkInput.fill('SPY');
  }

  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'shot_02_backtest_form.png') });

  // Click Execute Backtest Run
  console.log('Executing Backtest simulation...');
  const runBtn = page.getByRole('button', { name: 'Execute Backtest Run' });
  await runBtn.click();

  // Wait for result
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(outDir, 'shot_03_backtest_overview.png') });

  // Navigate through sub-tabs
  console.log('Checking Closed Trades tab...');
  const tradesTab = page.getByText(/Closed Trades/i);
  if (await tradesTab.isVisible()) {
    await tradesTab.click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(outDir, 'shot_04_closed_trades.png') });
  }

  console.log('Checking Simulated Fills tab...');
  const fillsTab = page.getByText(/Simulated Fills/i);
  if (await fillsTab.isVisible()) {
    await fillsTab.click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(outDir, 'shot_05_simulated_fills.png') });
  }

  console.log('Checking Daily Ledger tab...');
  const ledgerTab = page.getByText(/Daily Ledger/i);
  if (await ledgerTab.isVisible()) {
    await ledgerTab.click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(outDir, 'shot_06_daily_ledger.png') });
  }

  console.log('Checking Manifest tab...');
  const manifestTab = page.getByText(/Manifest/i);
  if (await manifestTab.isVisible()) {
    await manifestTab.click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(outDir, 'shot_07_manifest.png') });
  }

  console.log('Checking Compare Runs tab...');
  const compareTab = page.getByText(/Compare Runs/i);
  if (await compareTab.isVisible()) {
    await compareTab.click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(outDir, 'shot_08_compare_runs.png') });
  }

  console.log('All screenshots captured successfully in', outDir);
  await browser.close();
}

main().catch((err) => {
  console.error('Error during UI capture:', err);
  process.exit(1);
});
