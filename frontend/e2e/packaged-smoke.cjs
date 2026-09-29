// Called by backend/e2e/packaged_viewer_smoke.py while its relocated EXE is running.
const { chromium, expect } = require('@playwright/test');
const path = require('node:path');

(async () => {
  const output = path.resolve(__dirname, '../../test-output/viewer-verification');
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
    await page.getByRole('button', { name: 'Appearance', exact: true }).click();
    await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
    expect((await page.getByLabel('Log content').boundingBox()).height / 720).toBeGreaterThanOrEqual(.60);
    await page.getByRole('button', { name: 'Beginning', exact: true }).click();
    // A real 1 MiB section can finish rendering just after the default 5s
    // assertion deadline on the Windows VM. Keep a bounded preparation wait.
    await expect(page.getByText(/Section 1 of 2/)).toBeVisible({ timeout: 20000 });
    await page.getByRole('button', { name: 'Expand', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Packaged archive verification αβγ');
    await page.screenshot({ path: path.join(output, 'packaged-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Latest', exact: true }).click();
    await expect(page.getByText(/Section 2 of 2/)).toBeVisible({ timeout: 20000 });
    await page.getByRole('button', { name: 'Expand', exact: true }).click();
    expect((await page.getByRole('dialog').boundingBox()).width).toBe(390);
    await page.keyboard.press('Escape');
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

    // Failure case: a candidate embeds the old rack list or loses carrier order.
    // This fixture intercepts every Labware request, including writes; no real SQL
    // or robot inventory is read or changed by this packaged UI check.
    const left = ['VER_HT_0005', 'VER_HT_0001', 'VER_HT_0002', 'VER_HT_0006', 'VER_HT_0009'];
    const right = ['VER_HT_0003', 'VER_HT_0004', 'VER_HT_0007', 'VER_HT_0008', 'VER_HT_0010'];
    const states = ['clean', 'empty', 'dirty', 'rinsed', 'washed', 'reserved', 'unclear'];
    await page.route('**/api/labware/**', route => {
      if (route.request().method() !== 'GET') return route.fulfill({ status: 403, json: { message: 'Read-only packaged fixture' } });
      if (route.request().url().endsWith('/cytomat')) return route.fulfill({ json: { data: {
        rows: Array.from({ length: 9 }, (_, index) => ({ cytomat_pos: String(index + 1), plate_id: index % 2 ? '' : `Plate-${index + 1}` })),
        plate_options: ['', 'Plate-1', 'Plate-3', 'Plate-5', 'Plate-7', 'Plate-9'], auto_refresh_ms: 60000,
        refreshed_at: '2026-09-26T12:00:00Z', permissions: { role: 'admin', is_local_session: false, can_update: false },
      } } });
      return route.fulfill({ json: { data: {
        grid: { rows: 8, cols: 12, positions_per_rack: 96 }, auto_refresh_ms: 60000,
        status_order: states, status_colors: { clean: '#22c55e', empty: '#d1d5db', dirty: '#ef4444', rinsed: '#3b82f6', washed: '#a855f7', reserved: '#f59e0b', unclear: '#6b7280' },
        unknown_status: 'unclear', refreshed_at: '2026-09-26T12:00:00Z',
        permissions: { role: 'admin', is_local_session: false, can_update: false },
        families: [{ family_id: '1000ul', display_name: '1000ul Tips', left_racks: left, right_racks: right, reset_map: {},
          tips: Object.fromEntries([...left, ...right].map((rack, index) => [rack, Object.fromEntries(Array.from({ length: 96 }, (_, tip) => [tip + 1, states[(index + Math.floor(tip / 8)) % states.length]]))])) }],
      } } });
    });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('http://127.0.0.1:8017/labware');
    await expect(page.getByRole('button', { name: /^Open rack / })).toHaveCount(10);
    const firstLeft = page.getByRole('button', { name: `Open rack ${left[0]}`, exact: true });
    const firstRight = page.getByRole('button', { name: `Open rack ${right[0]}`, exact: true });
    expect((await firstLeft.boundingBox()).x).toBeLessThan((await firstRight.boundingBox()).x);
    await expect(page.getByText('Read only', { exact: true })).toBeVisible();
    // Failure case: packaging restores the old repeating focus ripple.
    const focusedTip = page.locator('[data-tip="2"]');
    await focusedTip.focus();
    expect(await focusedTip.evaluate(element => element.getAnimations({ subtree: true }).some(animation => animation.effect?.getTiming().iterations === Infinity))).toBe(false);
    await page.screenshot({ path: path.join(output, 'packaged-deck-desktop.png'), fullPage: true, animations: 'disabled' });
    // Failure case: a 4K candidate keeps the old tiny fixed-size rack inside a huge card.
    const desktopTipSize = (await page.locator('[data-tip="1"]').boundingBox()).width;
    await page.setViewportSize({ width: 3840, height: 2160 });
    await expect.poll(async () => (await page.locator('[data-tip="1"]').boundingBox()).width).toBeGreaterThan(desktopTipSize * 1.25);
    // Failure case: a candidate restores width caps, uneven diagram bottoms or stretched dots.
    const workspace = page.locator('[data-tip-workspace]');
    await expect.poll(async () => Math.abs((await workspace.boundingBox()).width - (await page.locator('[data-page-pattern="spatial"]').boundingBox()).width)).toBeLessThanOrEqual(2);
    const overview = await page.getByRole('region', { name: 'Tip deck', exact: true }).boundingBox();
    expect(overview.width / (await workspace.boundingBox()).width).toBeCloseTo(.4, 2);
    const overviewBody = await page.locator('[data-tip-overview-body]').boundingBox();
    const editorBody = await page.locator('[data-tip-editor-body]').boundingBox();
    expect(Math.abs(overviewBody.y + overviewBody.height - editorBody.y - editorBody.height)).toBeLessThanOrEqual(2);
    const dot = await page.locator('[data-tip-dot]').first().boundingBox();
    expect(Math.abs(dot.width - dot.height)).toBeLessThanOrEqual(1);
    await page.screenshot({ path: path.join(output, 'packaged-deck-4k.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 320, height: 740 });
    expect((await firstLeft.boundingBox()).x).toBeLessThan((await firstRight.boundingBox()).x);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: path.join(output, 'packaged-deck-phone.png'), fullPage: true, animations: 'disabled' });
    // Failure case: physical shelves are reordered, omitted, or unused positions become editable.
    await page.goto('http://127.0.0.1:8017/labware?section=cytomat');
    const topShelf = page.getByRole('group', { name: 'Position 1', exact: true });
    const bottomShelf = page.getByRole('group', { name: 'Position 7', exact: true });
    await expect(topShelf).toBeVisible();
    expect((await topShelf.boundingBox()).y).toBeLessThan((await bottomShelf.boundingBox()).y);
    await expect(page.getByRole('group', { name: 'Position 8', exact: true })).toContainText('Unused');
    await expect(page.getByRole('group', { name: 'Position 9', exact: true })).toContainText('Unused');
    await expect(page.getByRole('combobox', { name: 'Plate at 8', exact: true })).toHaveCount(0);
    await page.screenshot({ path: path.join(output, 'packaged-cytomat-phone.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 1920, height: 1080 });
    const register = page.locator('[data-cytomat-register]');
    await expect.poll(async () => Math.abs((await register.boundingBox()).width - (await page.locator('[data-page-pattern="spatial"]').boundingBox()).width)).toBeLessThanOrEqual(2);
    await expect.poll(async () => { const box = await register.boundingBox(); return 1080 - box.y - box.height; }).toBeLessThanOrEqual(20);
    await page.screenshot({ path: path.join(output, 'packaged-cytomat-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 320, height: 740 });
    await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
    await page.route('**/api/monitoring/system-health', route => route.fulfill({ json: { data: {
      sampled_at: '2026-09-26T12:00:00Z', system: { cpu_percent: 4, memory_percent: 25, disk_percent: 50 },
      database: { is_connected: true, database_name: 'Fixture DB', server_name: 'Fixture server', mode: 'primary' },
    } } }));
    await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: {
      enabled: true, active_session_count: 0, max_sessions: 10, resource_usage_percent: 45, total_bandwidth_mbps: 7,
    } } }));
    await page.goto('http://127.0.0.1:8017/system-status');
    const details = page.getByRole('button', { name: 'Connection details', exact: true });
    await expect(details).toHaveAttribute('aria-expanded', 'false');
    await details.click();
    await expect(page.getByText('0 of 10 slots in use', { exact: true })).toBeVisible();
    await expect(page.getByText(/Utilization|Bandwidth/)).toHaveCount(0);
    await page.screenshot({ path: path.join(output, 'packaged-connections-phone.png'), fullPage: true, animations: 'disabled' });
    expect(errors).toEqual([]);
  } finally {
    await context.tracing.stop({ path: path.join(output, 'packaged-trace.zip') });
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
