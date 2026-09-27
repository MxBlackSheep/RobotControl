// Run from the repository root: node frontend/e2e/labware-native-zoom.cjs
// Set the dedicated Edge window's native browser zoom to 200% when prompted.
const { chromium, expect } = require('@playwright/test');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'recovery/viewer-verification');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const server = spawn(path.join(root, '.venv/Scripts/python.exe'), [path.join(root, 'backend/e2e/viewer_server.py')], { cwd: root, windowsHide: true, stdio: 'ignore' });
  let browser, context;
  const result = { passed: false, checks: [] };
  try {
    for (let attempt = 0; ; attempt++) {
      try { if ((await fetch('http://127.0.0.1:8016/__e2e/health')).ok) break; } catch {}
      if (attempt > 50 || server.exitCode !== null) throw new Error('Disposable fixture server did not start');
      await pause(200);
    }
    browser = await chromium.launch({ channel: 'msedge', headless: false, args: ['--window-size=1920,1080', '--force-device-scale-factor=1'] });
    context = await browser.newContext({ viewport: null });
    await context.tracing.start({ screenshots: true, snapshots: true });
    await context.addInitScript(() => { localStorage.setItem('access_token', 'viewer-admin'); localStorage.setItem('robotcontrol-appearance', 'dark'); });
    const page = await context.newPage();
    const left = ['VER_HT_0005', 'VER_HT_0001', 'VER_HT_0002', 'VER_HT_0006', 'VER_HT_0009'];
    const right = ['VER_HT_0003', 'VER_HT_0004', 'VER_HT_0007', 'VER_HT_0008', 'VER_HT_0010'];
    await page.route('**/api/labware/**', route => {
      if (route.request().method() !== 'GET') return route.fulfill({ status: 403, json: { message: 'Read-only fixture' } });
      const shared = { auto_refresh_ms: 60000, refreshed_at: '2026-09-27T12:00:00Z', permissions: { role: 'admin', is_local_session: false, can_update: false } };
      const data = route.request().url().endsWith('/cytomat') ? { ...shared, rows: Array.from({ length: 9 }, (_, i) => ({ cytomat_pos: String(i + 1), plate_id: i % 2 ? '' : 'Plate-' + (i + 1) })), plate_options: [''] } : {
        ...shared, grid: { rows: 8, cols: 12, positions_per_rack: 96 }, status_order: ['clean', 'empty'], status_colors: { clean: '#22c55e', empty: '#d1d5db' }, unknown_status: 'empty',
        families: [{ family_id: '1000ul', display_name: '1000ul Tips', left_racks: left, right_racks: right, reset_map: {}, tips: Object.fromEntries([...left, ...right].map((rack, n) => [rack, Object.fromEntries(Array.from({ length: 96 }, (_, i) => [i + 1, n % 2 ? 'clean' : 'empty']))])) }],
      };
      return route.fulfill({ json: { data } });
    });
    const metrics = () => page.evaluate(() => ({ ratio: devicePixelRatio, width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth > innerWidth + 1 }));
    await page.goto('http://127.0.0.1:8016/labware');
    await page.getByRole('button', { name: 'Open rack ' + left[0], exact: true }).click();
    await expect(page.locator('[data-tip="1"]')).toBeVisible();
    await page.evaluate(() => { document.title = 'RobotControl Labware native zoom verification'; });
    result.before = await metrics();
    await page.screenshot({ path: path.join(output, 'labware-native-zoom-100.png'), animations: 'disabled' });
    console.log('Dedicated Edge window ready. Set native browser zoom to 200%.');
    await page.waitForFunction(before => devicePixelRatio >= before * 1.9, result.before.ratio, { timeout: 180000 });
    result.after = await metrics();
    expect(result.after.overflow).toBe(false);
    if (!(await page.getByRole('dialog').isVisible())) await page.getByRole('button', { name: 'Open rack ' + left[0], exact: true }).click();
    const tip = page.locator('[data-tip="1"]');
    await expect(tip).toBeVisible();
    const bounds = await tip.boundingBox();
    expect(bounds.width).toBeGreaterThanOrEqual(44); expect(bounds.height).toBeGreaterThanOrEqual(44);
    await tip.focus(); await tip.press('ArrowDown'); await expect(page.locator('[data-tip="2"]')).toBeFocused();
    await page.screenshot({ path: path.join(output, 'labware-native-zoom-200.png'), animations: 'disabled' });
    if (await page.getByRole('dialog').isVisible()) {
      await page.getByRole('button', { name: 'Back to deck', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Open rack ' + left[0], exact: true })).toBeFocused();
    }
    await page.goto('http://127.0.0.1:8016/labware?section=cytomat');
    await expect(page.getByRole('group', { name: 'Position 9', exact: true })).toContainText('Unused');
    expect((await metrics()).overflow).toBe(false);
    await page.screenshot({ path: path.join(output, 'cytomat-native-zoom-200.png'), fullPage: true, animations: 'disabled' });
    result.passed = true;
    result.checks = ['native 200% browser zoom', 'no horizontal page overflow', '44px tip targets', 'keyboard tip navigation', 'compact Back focus restoration when applicable', 'Cytomat order and unused positions'];
    console.log('Labware native zoom verification passed.');
  } catch (error) { result.error = String(error); throw error; }
  finally {
    await fs.writeFile(path.join(output, 'labware-native-zoom.json'), JSON.stringify(result, null, 2));
    if (context) await context.tracing.stop({ path: path.join(output, 'labware-native-zoom-trace.zip') });
    if (browser) await browser.close();
    try { await fetch('http://127.0.0.1:8016/__e2e/shutdown', { method: 'POST' }); } catch {}
    for (let attempt = 0; server.exitCode === null && attempt < 100; attempt++) await pause(100);
    if (server.exitCode === null) server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
