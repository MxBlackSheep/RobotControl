// Run from the repository root: node frontend/e2e/native-zoom.cjs
// In the dedicated Edge window, set native browser zoom to200% within3minutes.
const { chromium, expect } = require('@playwright/test');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'test-output/viewer-verification');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const server = spawn(path.join(root, '.venv/Scripts/python.exe'), [path.join(root, 'backend/e2e/viewer_server.py')], { cwd: root, windowsHide: true, stdio: 'ignore' });
  let browser, context;
  try {
    for (let attempt = 0; ; attempt++) {
      try { if ((await fetch('http://127.0.0.1:8016/__e2e/health')).ok) break; } catch {}
      if (attempt > 50 || server.exitCode !== null) throw new Error('Disposable fixture server did not start');
      await pause(200);
    }
    browser = await chromium.launch({ channel: 'msedge', headless: false, args: ['--window-size=1280,900', '--force-device-scale-factor=1'] });
    context = await browser.newContext({ viewport: null });
    await context.tracing.start({ screenshots: true, snapshots: true });
    await context.addInitScript(() => { localStorage.setItem('access_token', 'viewer-admin'); localStorage.setItem('robotcontrol-appearance', 'dark'); });
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:8016/logfile?section=robotcontrol');
    await page.getByRole('button', { name: /robotcontrol_backend.log/ }).click();
    await expect(page.getByLabel('Log content')).toContainText('ACTIVE-END');
    await page.evaluate(() => { document.title = 'RobotControl native zoom verification'; });
    const before = await page.evaluate(() => ({ ratio: devicePixelRatio, width: innerWidth, height: innerHeight }));
    await page.screenshot({ path: path.join(output, 'native-zoom-100.png'), fullPage: true });
    console.log('Dedicated Edge window ready. Set browser zoom to200%.');
    await page.waitForFunction(() => devicePixelRatio >= 1.9, null, { timeout: 180000 });
    await page.getByRole('button', { name: 'Find', exact: true }).click();
    await page.getByLabel('Find in this section').fill('ACTIVE');
    await expect(page.getByText('2 matches in this section', { exact: true })).toBeVisible();
    const after = await page.evaluate(() => ({ ratio: devicePixelRatio, width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth > innerWidth + 1 }));
    expect(after.overflow).toBe(false);
    await page.screenshot({ path: path.join(output, 'native-zoom-200.png'), fullPage: true });
    await page.getByRole('button', { name: 'Back to files', exact: true }).click();
    await expect(page.getByRole('button', { name: /robotcontrol_backend.log/ })).toBeFocused();
    await fs.writeFile(path.join(output, 'native-zoom.json'), JSON.stringify({ passed: true, before, after, checks: ['native200% browser zoom', 'Find remains usable', 'no horizontal page overflow', 'Back restores file focus'] }, null, 2));
    console.log('Native zoom verification passed.');
  } finally {
    if (context) await context.tracing.stop({ path: path.join(output, 'native-zoom-trace.zip') });
    if (browser) await browser.close();
    try { await fetch('http://127.0.0.1:8016/__e2e/shutdown', { method: 'POST' }); } catch {}
    for (let attempt = 0; server.exitCode === null && attempt < 100; attempt++) await pause(100);
    if (server.exitCode === null) server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
