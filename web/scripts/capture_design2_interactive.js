import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { spawn } from 'child_process';

async function main() {
  const outDir = 'C:/Users/stroo/.gemini/antigravity/brain/0b8c60ca-15ee-4353-8bf3-14c7615bfd9f';
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  console.log('Starting preview server on port 5179...');
  const server = spawn('npx.cmd', ['vite', 'preview', '--port', '5179', '--strictPort'], {
    cwd: 'd:/stroo/Documents/GitHub/market-research-lab/web',
    stdio: 'pipe',
    shell: true,
  });

  await new Promise((resolve) => setTimeout(resolve, 2000));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  try {
    console.log('Navigating to Design 2 (Interactive Candlestick Master)...');
    await page.goto('http://127.0.0.1:5179/?tab=backtest&variant=2');
    await page.waitForSelector('text=Design 2: Candlestick Master', { timeout: 10000 });
    await page.waitForTimeout(1500);

    // 1. Capture Main Design 2 Overview
    await page.screenshot({ path: path.join(outDir, 'design2_01_candlestick_overview.png') });
    console.log('Captured Design 2 Overview');

    // 2. Hover over the middle of the Candlestick Canvas to trigger Crosshair HUD seeking
    const canvas = page.locator('canvas').first();
    if (await canvas.isVisible()) {
      const box = await canvas.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.5);
        await page.waitForTimeout(600);
        await page.screenshot({ path: path.join(outDir, 'design2_02_crosshair_hud_seeking.png') });
        console.log('Captured Crosshair Seeking HUD');
      }
    }

    // 3. Switch to AAPL Bull Put position and inspect full open tray
    console.log('Selecting AAPL Bull Put position...');
    const aaplBtn = page.getByRole('button', { name: /AAPL/i }).first();
    if (await aaplBtn.isVisible()) {
      await aaplBtn.click();
      await page.waitForTimeout(800);
      // Scroll to reveal full tray cleanly
      await page.evaluate(() => window.scrollBy(0, 700));
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(outDir, 'design2_03_aapl_candlestick_tray.png') });
      console.log('Captured AAPL Candlestick & Table Tray');
    }

    console.log('Design 2 interactive capture completed successfully.');
  } finally {
    await browser.close();
    server.kill();
  }
}

main().catch((err) => {
  console.error('Error during capture:', err);
  process.exit(1);
});
