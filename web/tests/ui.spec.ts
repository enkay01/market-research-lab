import { test } from 'playwright/test';

test.use({ channel: 'msedge', viewport: { width: 1440, height: 900 } });

test('capture screenshots of all views', async ({ page }) => {
  await page.goto('http://127.0.0.1:5173');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  const outDir = 'C:/Users/stroo/.gemini/antigravity/brain/f25f797b-3a1b-4364-9189-fa072431dec2';
  await page.screenshot({ path: `${outDir}/shot_data.png` });

  // Security Research
  await page.getByText('Security Research').click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${outDir}/shot_research.png` });

  // Valuation
  await page.getByText('Valuation').click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${outDir}/shot_valuation.png` });

  // Models & Indicators
  await page.getByText('Models & Indicators').click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${outDir}/shot_models.png` });

  // Backtests
  await page.getByText('Backtests').click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${outDir}/shot_backtests.png` });

  // Alerts
  await page.getByText('Alerts').click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${outDir}/shot_alerts.png` });
});
