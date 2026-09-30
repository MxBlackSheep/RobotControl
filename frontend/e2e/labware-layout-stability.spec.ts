import { expect, Page, test } from '@playwright/test';

/** Failure cases for tip layout and background reading:
 * - The tip surface fills the page width (no maximum). The overview/editor split is
 *   40/60; when 60% cannot hold twelve 44px targets, keep the editor minimum and shrink
 *   the overview to 320px; below that, show the overview plus a focused-rack dialog.
 * - Five overview rows and eight editor rows share header, diagram and footer bounds.
 *   Pitches may differ, but targets stay at least 44px and dots stay circular (at least
 *   5px in miniatures). A short desktop has one stage scroll, no nested editor scroll.
 * - Measurement must not observe its own output: no ResizeObserver loop, no size change
 *   while scrolling, and a scrollbar near the breakpoint must not toggle modes. Hidden
 *   retained sections must not publish zero sizes. Sidebar, toolbar wrapping and zoom
 *   recalculate without remounting the rack or losing selection and drafts.
 * - Heading, toolbar and workspace share one leading edge at 1280 and 3840px.
 * - Long rack IDs ellipsize but keep their full accessible name; adding or clearing 96
 *   unsaved tips must not move either diagram.
 * - A background read must not move or replace rack nodes, insert a progress bar,
 *   disable controls, pulse a focused tip or take focus from Refresh.
 * - Starting a selection or edit invalidates an in-flight read synchronously, so a late
 *   response cannot replace the snapshot, chosen corner or drafts. Cancelled and no-op
 *   actions resume reading; pending drafts or writes keep it paused.
 * - Resizing the container cancels an unfinished selection but keeps drafts.
 * Native browser zoom is checked separately by labware-native-zoom.cjs.
 */
const left = ['VER_HT_0005', 'VER_HT_0001', 'VER_HT_0002', 'VER_HT_0006', 'VER_HT_0009'];
const right = ['VER_HT_0003', 'VER_HT_0004', 'VER_HT_0007', 'VER_HT_0008', 'VER_HT_0010'];
const statuses = ['clean', 'empty', 'dirty', 'rinsed', 'washed', 'reserved', 'unclear'];

async function fixture(page: Page, firstRack = left[0]) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  const snapshot = {
    grid: { rows: 8, cols: 12, positions_per_rack: 96 }, auto_refresh_ms: 1000,
    status_order: statuses, status_colors: { clean: '#22c55e', empty: '#d1d5db', dirty: '#ef4444', rinsed: '#3b82f6', washed: '#a855f7', reserved: '#f59e0b', unclear: '#6b7280' },
    unknown_status: 'unclear', refreshed_at: '2026-09-26T12:00:00Z',
    permissions: { role: 'admin', is_local_session: true, can_update: true },
    families: [{ family_id: 'tips1000', display_name: '1000 µL tips', left_racks: [firstRack, ...left.slice(1)], right_racks: right, reset_map: {},
      tips: Object.fromEntries([firstRack, ...left.slice(1), ...right].map((rack, index) => [rack, Object.fromEntries(Array.from({ length: 96 }, (_, i) => [String(i + 1), index === 0 ? 'clean' : statuses[(Math.floor(i / 8) + index) % statuses.length]]))])) }],
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

for (const reducedMotion of ['reduce'] as const) test(`focused wells are static with ${reducedMotion} motion`, async ({ page }, info) => {
  await fixture(page); await page.emulateMedia({ reducedMotion }); await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto('/labware'); await openRack(page);
  const first = page.getByRole('button', { name: 'Tip 1, clean', exact: true }); await first.focus(); await first.press('ArrowDown');
  const second = page.getByRole('button', { name: 'Tip 2, clean', exact: true }); await expect(second).toBeFocused();
  await expect(second.locator('.MuiTouchRipple-root')).toHaveCount(0);
  const focus = await second.evaluate(element => ({ outline: getComputedStyle(element).outlineStyle, width: getComputedStyle(element).outlineWidth, animations: element.getAnimations({ subtree: true }).filter(animation => animation.playState === 'running').length }));
  expect(focus.outline).not.toBe('none'); expect(parseFloat(focus.width)).toBeGreaterThanOrEqual(2); expect(focus.animations).toBe(0);
  await info.attach(`static-focus-${reducedMotion}`, { body: JSON.stringify(focus), contentType: 'application/json' });
  await info.attach(`static-focus-${reducedMotion}`, { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

for (const viewport of [{ width: 3840, height: 2160 }, { width: 1280, height: 720 }, { width: 320, height: 720 }]) test(`joined workbench fits ${viewport.width}x${viewport.height}`, async ({ page }, info) => {
  await fixture(page); await page.setViewportSize(viewport); await page.goto('/labware'); await openRack(page);
  const grid = page.getByRole('group', { name: `${left[0]} tips`, exact: true });
  const first = grid.getByRole('button').first(); const box = await first.boundingBox(); expect(box!.width).toBeGreaterThanOrEqual(43.9); expect(box!.height).toBeGreaterThanOrEqual(43.9);
  const dot = await first.locator('[data-tip-dot]').boundingBox(); expect(Math.abs(dot!.width - dot!.height)).toBeLessThan(0.1);
  const scrollBody = page.locator('[data-tip-editor-body]');
  const clipping = await scrollBody.evaluate(element => ({ top: element.getBoundingClientRect().top + element.clientTop, visibleHeight: element.clientHeight, horizontal: element.scrollWidth > element.clientWidth }));
  if (clipping.horizontal) { const last = await grid.getByRole('button').last().boundingBox(); expect(last!.y + last!.height).toBeLessThanOrEqual(clipping.top + clipping.visibleHeight + 1); }
  if (!(await page.getByRole('dialog').isVisible())) {
    const deck = page.getByRole('region', { name: 'Tip deck' }); const deckBox = await deck.boundingBox();
    const editor = page.locator('[data-rack-editor]'); const editorBox = await editor.boundingBox();
    expect(Math.abs(editorBox!.x - (deckBox!.x + deckBox!.width))).toBeLessThanOrEqual(1);
    const workbench = await page.locator('[data-tip-workspace]').boundingBox();
    const available = await page.locator('[data-tip-workspace]').evaluate(element => element.clientWidth);
    const content = await page.locator('[data-page-pattern="spatial"]').boundingBox();
    expect(Math.abs(workbench!.width - content!.width)).toBeLessThanOrEqual(1);
    const expectedOverview = Math.max(320, Math.min(available * 0.4, available - 596));
    expect(Math.abs(deckBox!.width - expectedOverview)).toBeLessThanOrEqual(2);
    const overviewBody = await page.locator('[data-tip-overview-body]').boundingBox();
    const editorBody = await page.locator('[data-tip-editor-body]').boundingBox();
    expect(Math.abs(overviewBody!.y - editorBody!.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(overviewBody!.y + overviewBody!.height - editorBody!.y - editorBody!.height)).toBeLessThanOrEqual(1);
    const miniDot = await deck.locator('[data-overview-dot]').first().boundingBox();
    expect(miniDot!.width).toBeGreaterThanOrEqual(4.9); expect(Math.abs(miniDot!.width - miniDot!.height)).toBeLessThan(0.1);
    if (viewport.width === 3840) { expect(box!.width).toBeGreaterThan(132); expect(miniDot!.width).toBeGreaterThan(9); }
    await expect(deck.getByRole('group', { name: 'Col A', exact: true }).getByRole('button')).toHaveCount(5);
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

test('short desktop has one stage scroll and container resizing cancels only the unfinished selection', async ({ page }, info) => {
  await fixture(page); await page.setViewportSize({ width: 1440, height: 500 }); await page.goto('/labware'); await openRack(page);
  const stage = page.locator('[data-tip-workspace]'); const body = page.locator('[data-tip-editor-body]');
  expect(await stage.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  expect(await body.evaluate(element => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
  await page.getByRole('button', { name: 'Tip 96, clean', exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByText('Choose a status to edit tips.', { exact: true })).toBeVisible();
  await stage.evaluate(element => { element.scrollTop = 0; });
  await page.getByRole('combobox', { name: 'Set tips to', exact: true }).click(); await page.getByRole('option', { name: 'Dirty', exact: true }).click();
  await page.getByRole('button', { name: 'Tip 1, clean', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel selection', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /^(Collapse|Expand) navigation$/ }).click();
  await expect(page.getByRole('button', { name: 'Cancel selection', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Save changes (0)', exact: true })).toBeDisabled();
  await info.attach('short-stage-scroll-resize', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

test('short split boundary stays stable when a scrollbar appears', async ({ page }, info) => {
  await fixture(page); await page.setViewportSize({ width: 1040, height: 500 }); await page.goto('/labware');
  const evidence: any[] = [];
  for (const width of [1040, 1020, 1014, 1010]) {
    await page.setViewportSize({ width, height: 500 }); await page.waitForTimeout(350);
    const samples = await page.locator('[data-tip-workspace]').evaluate(async element => {
      const frames: any[] = [];
      for (let frame = 0; frame < 20; frame++) {
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
        const box = element.getBoundingClientRect();
        frames.push({ width: box.width, height: box.height, split: Boolean(element.querySelector('[data-rack-editor]')), scroll: element.scrollHeight > element.clientHeight });
      }
      return frames;
    });
    expect(new Set(samples.map(sample => JSON.stringify(sample))).size).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    evidence.push({ width, samples });
  }
  await info.attach('short-boundary-geometry', { body: JSON.stringify(evidence, null, 2), contentType: 'application/json' });
  await info.attach('short-boundary-layout', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});

test('long rack names and unsaved counts cannot move the diagram', async ({ page }, info) => {
  const rack = 'VER_HT_0005__LONG_STORAGE_RACK_LOCATION_ALPHANUMERIC_IDENTIFIER';
  await fixture(page, rack); await page.setViewportSize({ width: 1280, height: 720 }); await page.goto('/labware');
  const opener = page.getByRole('button', { name: `Open rack ${rack}`, exact: true }); await opener.click();
  await page.getByRole('combobox', { name: 'Set tips to', exact: true }).click(); await page.getByRole('option', { name: 'Dirty', exact: true }).click();
  // Clicking an offscreen control can legitimately scroll the stage. Compare
  // layout in its content coordinates, not its changing viewport position.
  const geometry = async () => page.locator('[data-tip-workspace]').evaluate(stage => {
    const origin = stage.getBoundingClientRect();
    const box = (element: Element | null) => {
      const bounds = element!.getBoundingClientRect();
      return { x: bounds.x - origin.x + stage.scrollLeft, y: bounds.y - origin.y + stage.scrollTop, width: bounds.width, height: bounds.height };
    };
    return { stage: { x: origin.x + window.scrollX, y: origin.y + window.scrollY, width: origin.width, height: origin.height }, overview: box(stage.querySelector('[data-tip-overview-body]')), editor: box(stage.querySelector('[data-tip-editor-body]')), rack: box(stage.querySelector('[aria-current="true"]')) };
  });
  const before = await geometry();
  await page.getByRole('button', { name: 'Set entire rack', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save changes (96)', exact: true })).toBeEnabled();
  expect(await geometry()).toEqual(before);
  await expect(opener.locator('[title]').first()).toHaveAttribute('title', rack);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  expect(await geometry()).toEqual(before);
  await info.attach('long-rack-stable-pending', { body: await page.screenshot({ animations: 'disabled' }), contentType: 'image/png' });
});
