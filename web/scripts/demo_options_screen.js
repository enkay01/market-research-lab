import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { spawn } from 'child_process';

async function main() {
  const outDir = 'C:/Users/stroo/.gemini/antigravity/brain/0b8c60ca-15ee-4353-8bf3-14c7615bfd9f';
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  console.log('Starting preview server on port 5188...');
  const server = spawn('npx.cmd', ['vite', 'preview', '--port', '5188', '--strictPort'], {
    cwd: 'd:/stroo/Documents/GitHub/market-research-lab/web',
    stdio: 'pipe',
    shell: true,
  });

  await new Promise((resolve) => setTimeout(resolve, 2000));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  try {
    // 1. Open the Backtests tab
    console.log('Opening Backtests view...');
    await page.goto('http://127.0.0.1:5188/?tab=backtest');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(outDir, 'demo_01_options_backtest_view.png') });
    console.log('Captured initial Options Backtest view');

    // 2. Open Data Health Drawer
    console.log('Opening Data Health Drawer...');
    const dataHealthBtn = page.getByRole('button', { name: /Data Health/i });
    if (await dataHealthBtn.isVisible()) {
      await dataHealthBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'demo_02_data_health_drawer.png') });
      console.log('Captured Data Health drawer');
    }

    // 3. Switch Position in Gantt Timeline to NVDA
    console.log('Selecting NVDA Bear Call position...');
    const nvdaRow = page.getByText('NVDA', { exact: false }).first();
    if (await nvdaRow.isVisible()) {
      await nvdaRow.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'demo_03_nvda_position_trajectory.png') });
      console.log('Captured NVDA trajectory chart');
    }

    // 4. Click on "Leg Execution Prices" Sub-tab
    console.log('Checking Leg Execution Prices tab...');
    const pricesTab = page.getByText(/Leg Execution Prices/i);
    if (await pricesTab.isVisible()) {
      await pricesTab.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'demo_04_leg_prices_tab.png') });
      console.log('Captured Leg Execution Prices sub-tab');
    }

    // 5. Click on "Blocked Opportunities" Sub-tab
    console.log('Checking Blocked Opportunities tab...');
    const blockedTab = page.getByText(/Blocked Opportunities/i);
    if (await blockedTab.isVisible()) {
      await blockedTab.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'demo_05_blocked_opportunities.png') });
      console.log('Captured Blocked Opportunities sub-tab');
    }

    // 6. Click on "Run Provenance Manifest" Sub-tab
    console.log('Checking Manifest tab...');
    const manifestTab = page.getByText(/Run Provenance Manifest/i);
    if (await manifestTab.isVisible()) {
      await manifestTab.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'demo_06_manifest_tab.png') });
      console.log('Captured Manifest sub-tab');
    }

    // 7. Toggle back to Multi-Asset Backtest
    console.log('Switching to Standard Multi-Asset Backtest...');
    const multiAssetBtn = page.getByRole('button', { name: /Multi-Asset Backtest/i });
    if (await multiAssetBtn.isVisible()) {
      await multiAssetBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'demo_07_standard_backtest_switch.png') });
      console.log('Captured standard backtest view switch');
    }

  } finally {
    await browser.close();
    server.kill();
    console.log('Demo completed successfully.');
  }
}

main().catch((err) => {
  console.error('Error during demo capture:', err);
  process.exit(1);
});
