import { expect, Page, test } from '@playwright/test';

const left = ['VER_HT_0005', 'VER_HT_0001', 'VER_HT_0002', 'VER_HT_0006', 'VER_HT_0009'];
const right = ['VER_HT_0003', 'VER_HT_0004', 'VER_HT_0007', 'VER_HT_0008', 'VER_HT_0010'];
const statuses = ['clean', 'empty', 'dirty', 'rinsed', 'washed', 'reserved', 'unclear'];

async function fixture(page: Page) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  const snapshot = {
    grid: { rows: 8, cols: 12, positions_per_rack: 96 }, auto_refresh_ms: 1000,
    status_order: statuses, status_colors: { clean: '#22c55e', empty: '#d1d5db', dirty: '#ef4444', rinsed: '#3b82f6', washed: '#a855f7', reserved: '#f59e0b', unclear: '#6b7280' },
    unknown_status: 'unclear', refreshed_at: '2026-09-26T12:00:00Z',
    permissions: { role: 'admin', is_local_session: true, can_update: true },
    families: [{ family_id: 'tips1000', display_name: '1000 µL tips', left_racks: left, right_racks: right, reset_map: {},
      tips: Object.fromEntries([...left, ...right].map((rack, index) => [rack, Object.fromEntries(Array.from({ length: 96 }, (_, i) => [String(i + 1), index === 0 ? 'clean' : statuses[(Math.floor(i / 8) + index) % statuses.length]]))])) }],
  };
  const state = { reads: 0, writes: [] as any[], gate: null as Promise<void> | null, lateStatus: null as string | null };
  await page.route('**/api/labware/tip-tracking', async route => {
    if (route.request().method() === 'PUT') {
      const payload = route.request().postDataJSON(); state.writes.push(payload);
      for (const edit of payload.updates) snapshot.families[0].tips[edit.labware_id][edit.position_id] = edit.status;
      return route.fulfill({ json: { data: { requested_count: payload.updates.length, updated_count: payload.updates.length } } });
    }
    state.reads++;
    const response = structuredClone(snapshot);
    if (state.gate) await state.gate;
    if (state.lateStatus) response.families[0].tips[left[0]] = Object.fromEntries(Array.from({ length: 96 }, (_, i) => [String(i + 1), state.lateStatus!]));
    await route.fulfill({ json: { data: response } }).catch(() => {});
  });
  return state;
}

async function openRack(page: Page) {
  await page.getByRole('button', { name: `Open rack ${left[0]}`, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Tip 1, clean', exact: true })).toBeVisible();
}

test('background reads preserve geometry, mounted tips and Refresh keyboard focus', async ({ page }, info) => {
  const state = await fixture(page); await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto('/labware'); await openRack(page);
  const first = page.getByRole('button', { name: 'Tip 1, clean', exact: true });
  const grid = page.getByRole('group', { name: `${left[0]} tips`, exact: true });
  const refresh = page.getByRole('button', { name: 'Refresh', exact: true });
  await expect.poll(() => first.boundingBox().then(box => box!.width)).toBeGreaterThanOrEqual(44);
  const before = await grid.boundingBox();
  await first.evaluate(element => { (window as any).__stableTip = element; });
  let release!: () => void; state.gate = new Promise<void>(resolve => release = resolve);
  const reads = state.reads; await refresh.focus(); await refresh.press('Enter');
  await expect.poll(() => state.reads).toBeGreaterThan(reads);
  await expect(refresh).toBeFocused(); await expect(refresh).toBeEnabled();
  await expect(page.getByRole('combobox', { name: 'Set tips to', exact: true })).toBeEnabled();
  const during = await grid.boundingBox(); expect(during).toEqual(before);
  await expect(page.getByRole('progressbar', { name: 'Refreshing tips' })).toHaveCount(0);
  release(); state.gate = null; await expect(page.getByText('Updating…', { exact: true })).toHaveCount(0);
  await expect(refresh).toBeFocused(); expect(await grid.boundingBox()).toEqual(before);
  expect(await first.evaluate(element => element === (window as any).__stableTip)).toBe(true);
  await info.attach('refresh-stability-evidence', { body: JSON.stringify({ before, during, after: await grid.boundingBox(), focusPreserved: true, sameTipNode: true }, null, 2), contentType: 'application/json' });
  await info.attach('quiet-workbench-refresh', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

test('selection during an in-flight read rejects its late snapshot and keeps one undoable draft', async ({ page }, info) => {
  const state = await fixture(page); await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto('/labware'); await openRack(page);
  await page.getByRole('combobox', { name: 'Set tips to', exact: true }).click(); await page.getByRole('option', { name: 'Dirty', exact: true }).click();
  let release!: () => void; state.gate = new Promise<void>(resolve => release = resolve); state.lateStatus = 'reserved';
  const reads = state.reads; await page.getByRole('button', { name: 'Refresh', exact: true }).click(); await expect.poll(() => state.reads).toBeGreaterThan(reads);
  await page.getByRole('button', { name: 'Tip 1, clean', exact: true }).click(); await expect(page.getByRole('button', { name: 'Cancel selection', exact: true })).toBeVisible();
  release(); state.gate = null; await page.waitForTimeout(100);
  await expect(page.getByRole('button', { name: 'Tip 10, clean', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Tip 10, clean', exact: true }).click();
  for (const tip of [1, 2, 9, 10]) await expect(page.getByRole('button', { name: `Tip ${tip}, dirty`, exact: true })).toBeVisible();
  expect(state.writes).toEqual([]); await expect(page.getByRole('button', { name: 'Save changes (4)', exact: true })).toBeEnabled();
  await info.attach('selection-late-read-rejected', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
  state.lateStatus = null; await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save changes (0)', exact: true })).toBeDisabled();
});

test('setting an unchanged rack keeps background reading and the chosen status', async ({ page }, info) => {
  const state = await fixture(page); await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto('/labware'); await openRack(page);
  const status = page.getByRole('combobox', { name: 'Set tips to', exact: true });
  await status.click(); await page.getByRole('option', { name: 'Clean', exact: true }).click();
  const reads = state.reads; await page.getByRole('button', { name: 'Set entire rack', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save changes (0)', exact: true })).toBeDisabled();
  await expect.poll(() => state.reads).toBeGreaterThan(reads); await expect(status).toContainText('Clean'); expect(state.writes).toEqual([]);
  await info.attach('unchanged-rack-still-reading', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

test('sidebar resizing keeps the rack mounted and its draft geometry settles', async ({ page }, info) => {
  await fixture(page); await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto('/labware'); await openRack(page);
  await page.getByRole('combobox', { name: 'Set tips to', exact: true }).click(); await page.getByRole('option', { name: 'Dirty', exact: true }).click();
  const tip = page.getByRole('button', { name: 'Tip 1, clean', exact: true }); await tip.dblclick();
  const edited = page.getByRole('button', { name: 'Tip 1, dirty', exact: true });
  await edited.evaluate(element => { (window as any).__stableTip = element; });
  await page.getByRole('button', { name: /^(Collapse|Expand) navigation$/ }).click();
  await expect(edited).toBeVisible(); await expect(page.getByRole('button', { name: 'Save changes (1)', exact: true })).toBeEnabled();
  await page.waitForTimeout(350); // Allow the shared drawer transition to finish.
  const geometry = await edited.evaluate(async element => {
    const samples: number[][] = [];
    for (let frame = 0; frame < 10; frame++) {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      const box = element.getBoundingClientRect(); samples.push([box.x, box.y, box.width, box.height]);
    }
    return { samples, sameNode: element === (window as any).__stableTip };
  });
  expect(geometry.sameNode).toBe(true); expect(new Set(geometry.samples.map(sample => JSON.stringify(sample))).size).toBe(1);
  await info.attach('sidebar-rack-stability', { body: JSON.stringify(geometry, null, 2), contentType: 'application/json' });
  await info.attach('sidebar-rack-draft', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

for (const reducedMotion of ['no-preference', 'reduce'] as const) test(`focused wells are static with ${reducedMotion} motion`, async ({ page }, info) => {
  await fixture(page); await page.emulateMedia({ reducedMotion }); await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto('/labware'); await openRack(page);
  const first = page.getByRole('button', { name: 'Tip 1, clean', exact: true }); await first.focus(); await first.press('ArrowDown');
  const second = page.getByRole('button', { name: 'Tip 2, clean', exact: true }); await expect(second).toBeFocused();
  await expect(second.locator('.MuiTouchRipple-root')).toHaveCount(0);
  const focus = await second.evaluate(element => ({ outline: getComputedStyle(element).outlineStyle, width: getComputedStyle(element).outlineWidth, animations: element.getAnimations({ subtree: true }).filter(animation => animation.playState === 'running').length }));
  expect(focus.outline).not.toBe('none'); expect(parseFloat(focus.width)).toBeGreaterThanOrEqual(2); expect(focus.animations).toBe(0);
  await info.attach(`static-focus-${reducedMotion}`, { body: JSON.stringify(focus), contentType: 'application/json' });
  await info.attach(`static-focus-${reducedMotion}`, { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 1024, height: 600 }, { width: 390, height: 844 }, { width: 320, height: 720 }]) test(`joined workbench fits ${viewport.width}x${viewport.height}`, async ({ page }, info) => {
  await fixture(page); await page.setViewportSize(viewport); await page.goto('/labware'); await openRack(page);
  const grid = page.getByRole('group', { name: `${left[0]} tips`, exact: true });
  const first = grid.getByRole('button').first(); const box = await first.boundingBox(); expect(box!.width).toBeGreaterThanOrEqual(44); expect(Math.abs(box!.width - box!.height)).toBeLessThan(1);
  if (!(await page.getByRole('dialog').isVisible())) {
    const deck = page.getByRole('region', { name: 'Tip deck' }); const deckBox = await deck.boundingBox();
    const editor = page.locator('[data-rack-editor]'); const editorBox = await editor.boundingBox();
    expect(Math.abs(editorBox!.x - (deckBox!.x + deckBox!.width))).toBeLessThanOrEqual(1);
    const workbench = await page.locator('[data-tip-workspace]').boundingBox();
    expect(workbench!.width - deckBox!.width - editorBox!.width).toBeLessThanOrEqual(3);
    await expect(deck.getByRole('group', { name: 'Col A', exact: true }).getByRole('button')).toHaveCount(5);
    if (viewport.width >= 1280) { const last = await grid.getByRole('button').last().boundingBox(); expect(last!.y + last!.height).toBeLessThanOrEqual(viewport.height - 12); }
  }
  if (viewport.width === 1280 || viewport.width === 3840) {
    const heading = await page.getByRole('heading', { name: 'Labware', exact: true }).boundingBox();
    const toolbar = await page.getByRole('combobox', { name: 'Tip family', exact: true }).locator('xpath=ancestor::*[contains(@class,"MuiTextField-root")]').boundingBox();
    expect(Math.abs(heading!.x - toolbar!.x)).toBeLessThanOrEqual(1);
    const surface = await page.locator('[data-tip-workspace]').boundingBox();
    expect(Math.abs(heading!.x - surface!.x)).toBeLessThanOrEqual(1);
    if (viewport.width === 1280) expect(surface!.y + surface!.height).toBeLessThanOrEqual(viewport.height - 2);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await info.attach(`joined-workbench-${viewport.width}`, { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});
