import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { spawn } from 'child_process';

async function main() {
  const outDir = 'C:/Users/stroo/.gemini/antigravity/brain/0b8c60ca-15ee-4353-8bf3-14c7615bfd9f';
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  // Start vite preview server
  console.log('Starting vite preview server...');
  const server = spawn('npx.cmd', ['vite', 'preview', '--port', '5199', '--strictPort'], {
    cwd: 'd:/stroo/Documents/GitHub/market-research-lab/web',
    stdio: 'pipe',
    shell: true,
  });

  // Wait a moment for the server to bind
  await new Promise((resolve) => setTimeout(resolve, 2000));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();

  try {
    // 1. Capture Variant A: Execution & Risk Audit
    console.log('Navigating to Variant A...');
    await page.goto('http://127.0.0.1:5199/?tab=backtest&variant=A');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(outDir, 'shot_01_variant_a_execution_audit.png') });
    console.log('Captured Variant A');

    // 2. Capture Variant B: Visual Dual-Path Explorer
    console.log('Navigating to Variant B...');
    await page.goto('http://127.0.0.1:5199/?tab=backtest&variant=B');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(outDir, 'shot_02_variant_b_visual_explorer.png') });
    console.log('Captured Variant B');

    // 3. Capture Variant C: Spread Matrix
    console.log('Navigating to Variant C (Spread Matrix)...');
    await page.goto('http://127.0.0.1:5199/?tab=backtest&variant=C');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(outDir, 'shot_03_variant_c_spread_matrix.png') });
    console.log('Captured Variant C Matrix');

    // 4. Capture Variant C (Printable Report tab)
    console.log('Capturing Variant C Report Mode...');
    await page.getByText('Printable Report Mode').click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(outDir, 'shot_04_variant_c_printable_report.png') });
    console.log('Captured Variant C Report');

    // 5. Test keyboard switcher: press Right Arrow to cycle back to Variant A
    console.log('Testing keyboard navigation...');
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(outDir, 'shot_05_keyboard_cycle_variant_a.png') });
    console.log('Captured keyboard cycle');

  } finally {
    await browser.close();
    server.kill();
    console.log('Server stopped and test completed successfully.');
  }
}

main().catch((err) => {
  console.error('Error during screenshot capture:', err);
  process.exit(1);
});
