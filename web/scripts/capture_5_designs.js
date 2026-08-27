import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { spawn } from 'child_process';

async function main() {
  const outDir = 'C:/Users/stroo/.gemini/antigravity/brain/0b8c60ca-15ee-4353-8bf3-14c7615bfd9f';
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  console.log('Starting preview server on port 5178...');
  const server = spawn('npx.cmd', ['vite', 'preview', '--port', '5178', '--strictPort'], {
    cwd: 'd:/stroo/Documents/GitHub/market-research-lab/web',
    stdio: 'pipe',
    shell: true,
  });

  await new Promise((resolve) => setTimeout(resolve, 2000));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message));

  try {
    // 1. Capture Design 1: Quant Multi-Pane
    console.log('Capturing Design 1 (Quant Multi-Pane)...');
    await page.goto('http://127.0.0.1:5178/?tab=backtest&variant=1');
    await page.waitForSelector('text=Design 1: Quant Multi-Pane', { timeout: 10000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, 'design_01_quant_multi_pane.png') });

    // 2. Capture Design 2: Candlestick Master
    console.log('Capturing Design 2 (Candlestick Master)...');
    await page.goto('http://127.0.0.1:5178/?tab=backtest&variant=2');
    await page.waitForSelector('text=Design 2: Candlestick Master', { timeout: 10000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, 'design_02_candlestick_master.png') });

    // 3. Capture Design 3: Hybrid Split-Canvas
    console.log('Capturing Design 3 (Hybrid Split-Canvas)...');
    await page.goto('http://127.0.0.1:5178/?tab=backtest&variant=3');
    await page.waitForSelector('text=Design 3: Hybrid Split-Canvas', { timeout: 10000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, 'design_03_hybrid_split_canvas.png') });

    // 4. Capture Design 4: Gantt Lifecycle Matrix
    console.log('Capturing Design 4 (Gantt Lifecycle Matrix)...');
    await page.goto('http://127.0.0.1:5178/?tab=backtest&variant=4');
    await page.waitForSelector('text=Design 4: Gantt Lifecycle Matrix', { timeout: 10000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, 'design_04_gantt_lifecycle_matrix.png') });

    // 5. Capture Design 5: Dense Ledger Tear-Sheet
    console.log('Capturing Design 5 (Dense Ledger Tear-Sheet)...');
    await page.goto('http://127.0.0.1:5178/?tab=backtest&variant=5');
    await page.waitForSelector('text=Design 5: Dense Ledger Tear-Sheet', { timeout: 10000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, 'design_05_dense_ledger_tearsheet.png') });

    console.log('All 5 designs captured successfully.');
  } finally {
    await browser.close();
    server.kill();
  }
}

main().catch((err) => {
  console.error('Error during capture:', err);
  process.exit(1);
});
