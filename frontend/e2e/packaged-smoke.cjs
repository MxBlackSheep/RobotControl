// Called by backend/e2e/packaged_viewer_smoke.py while its relocated EXE is running.
const { chromium, expect } = require('@playwright/test');
const path = require('node:path');

(async () => {
  const output = path.resolve(__dirname, '../../recovery/viewer-verification');
  const browser = await chromium.launch({ channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  await context.tracing.start({ screenshots: true, snapshots: true });
  await context.addInitScript(token => localStorage.setItem('access_token', token), process.env.VIEWER_SMOKE_TOKEN);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto('http://127.0.0.1:8017/logfile?section=robotcontrol');
    await page.getByRole('button', { name: 'History', exact: true }).click();
    await page.getByRole('button', { name: /packaged-check.log.gz/ }).click();
    await expect(page.getByLabel('Log content')).toContainText('Packaged archive verification αβγ');
    await page.getByRole('button', { name: 'Beginning', exact: true }).click();
    await expect(page.getByText(/Section 1 of 2/)).toBeVisible();
    await page.getByRole('button', { name: 'Expand', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Packaged archive verification αβγ');
    await page.screenshot({ path: path.join(output, 'packaged-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Latest', exact: true }).click();
    await expect(page.getByText(/Section 2 of 2/)).toBeVisible();
    await page.screenshot({ path: path.join(output, 'packaged-phone.png'), fullPage: true, animations: 'disabled' });
    expect(errors).toEqual([]);
    // Navigating away releases the captured reader before the Python cache check.
    const released = page.waitForResponse(response => response.url().includes('/api/logfiles/readers/') && response.request().method() === 'DELETE' && response.ok());
    await page.evaluate(() => {
      history.pushState(null, '', '/about');
      dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(page.getByLabel('Log content')).toHaveCount(0);
    await released;
  } finally {
    await context.tracing.stop({ path: path.join(output, 'packaged-trace.zip') });
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
