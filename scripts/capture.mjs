import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { mkdir } from 'node:fs/promises';

const base = process.env.EVALSCOPE_URL || 'http://127.0.0.1:8000';
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
await mkdir('docs/screenshots', { recursive: true });
try {
  await page.goto(base);
  await page.getByRole('heading', { name: 'Evaluation overview' }).waitFor();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: 'docs/screenshots/overview.png', fullPage: true });
  await page.getByRole('button', { name: 'Comparisons', exact: true }).click();
  for (const [field, name] of [['Baseline run', 'Support assistant · baseline'], ['Candidate run', 'Support assistant · candidate']]) {
    const select = page.getByLabel(field);
    const option = select.locator('option').filter({ hasText: name });
    await select.selectOption(await option.getAttribute('value'));
  }
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await page.getByRole('heading', { name: 'Case-by-case changes' }).waitFor();
  await page.screenshot({ path: 'docs/screenshots/comparison.png', fullPage: true });
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'docs/screenshots/mobile.png', fullPage: true });
} finally {
  await browser.close();
}
