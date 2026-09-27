import { expect, test, type Page } from '@playwright/test';

async function fixture(page: Page, canUpdate = true, duplicates = false, extraPositions = true) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  const rows = [9, 8, 7, 6, 5, 3, 2, 1].map(position => ({ cytomat_pos: String(position), plate_id: position === 2 ? '' : `P${position}00` }));
  if (extraPositions) rows.push({ cytomat_pos: '01', plate_id: 'P010' }, { cytomat_pos: 'SPARE', plate_id: 'a-very-long-plate-identifier-that-must-wrap-inside-the-shelf-without-page-overflow' });
  if (duplicates) rows.push({ cytomat_pos: '1', plate_id: 'CONFLICT' }, { cytomat_pos: 'SPARE', plate_id: 'CONFLICT' });
  const snapshot = { rows, plate_options: ['', 'P100', 'P200'], auto_refresh_ms: 1000,
    permissions: { role: 'admin', is_local_session: canUpdate, can_update: canUpdate }, refreshed_at: '2026-09-26T12:00:00Z' };
  const state = { rows, writes: [] as any[], reads: 0, failSave: false, saveGate: null as Promise<void> | null,
    readGate: null as Promise<void> | null, staleRead: false };
  await page.route('**/api/labware/cytomat', async route => {
    if (route.request().method() === 'PUT') {
      const payload = route.request().postDataJSON(); state.writes.push(payload);
      if (state.saveGate) await state.saveGate;
      if (state.failSave) return route.fulfill({ status: 500, json: { message: 'Save failed' } });
      for (const update of payload.updates) rows.find(row => row.cytomat_pos === update.cytomat_pos)!.plate_id = update.plate_id;
      return route.fulfill({ json: { data: { requested_count: payload.updates.length, updated_count: payload.updates.length } } });
    }
    state.reads++;
    const response = structuredClone(snapshot);
    if (state.staleRead) { response.rows[response.rows.length - 1].plate_id = 'STALE'; response.permissions.can_update = false; }
    if (state.readGate) await state.readGate;
    return route.fulfill({ json: { data: response } });
  });
  return state;
}

for (const [width, height] of [[3840, 2160], [1920, 1080], [1280, 720], [320, 740]]) {
  test(`Cytomat retains physical shelves and truthful states at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height });
    const state = await fixture(page);
    await page.goto('/labware?section=cytomat');
    const shelves = page.getByRole('list', { name: 'Cytomat shelves', exact: true });
    await expect(shelves.getByRole('listitem')).toHaveCount(7);
    expect(await shelves.getByRole('listitem').evaluateAll(items => items.map(item => item.getAttribute('data-position')))).toEqual(['1', '2', '3', '4', '5', '6', '7']);
    const bounds = await shelves.getByRole('listitem').evaluateAll(items => items.map(item => { const rect = item.getBoundingClientRect(); return { x: rect.x, y: rect.y, width: rect.width }; }));
    for (let index = 1; index < bounds.length; index++) { expect(bounds[index].y).toBeGreaterThan(bounds[index - 1].y); expect(bounds[index].x).toBe(bounds[0].x); }
    const available = await page.locator('[data-page-pattern="spatial"]').boundingBox();
    const workspace = await page.getByTestId('cytomat-workspace').boundingBox();
    expect(Math.abs(workspace!.width - available!.width)).toBeLessThanOrEqual(1);
    expect(bounds[0].width).toBeGreaterThanOrEqual(available!.width - 24); // Register border and native scroll gutter.
    await expect(page.getByTestId('cytomat-position-4')).toContainText('Unavailable');
    await expect(page.getByRole('combobox', { name: 'Plate at 4', exact: true })).toHaveCount(0);
    await expect(page.getByTestId('cytomat-position-2')).toContainText('Empty');
    await expect(page.getByRole('combobox', { name: /^Plate at/ })).toHaveCount(0);
    const unused = page.getByRole('region', { name: 'Unused positions', exact: true });
    await expect(unused).toContainText('P800'); await expect(unused).toContainText('P900');
    await expect(unused.getByRole('combobox')).toHaveCount(0);
    const other = page.getByRole('region', { name: 'Other positions', exact: true });
    await expect(other.getByRole('button', { name: 'Edit position 01', exact: true })).toBeVisible();
    await expect(other.getByRole('button', { name: 'Edit position SPARE', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(state.writes).toEqual([]);
    await page.screenshot({ path: info.outputPath(`cytomat-${width}.png`), fullPage: true, animations: 'disabled' });
    await page.getByRole('button', { name: 'Other positions (2)', exact: true }).click();
    await expect(other).toBeFocused();
    await expect(other.getByRole('button', { name: 'Edit position SPARE', exact: true })).toBeInViewport();
    await page.screenshot({ path: info.outputPath(`cytomat-extra-positions-${width}.png`), fullPage: true, animations: 'disabled' });
  });
}

test('Cytomat retains batch drafts through failed saves and freezes editors while saving', async ({ page }, info) => {
  const state = await fixture(page); state.failSave = true;
  await page.goto('/labware?section=cytomat');
  await page.getByRole('button', { name: 'Edit position 1', exact: true }).click();
  await page.getByRole('combobox', { name: 'Plate at 1', exact: true }).click();
  await page.getByRole('option', { name: 'Empty', exact: true }).click();
  await page.getByRole('button', { name: 'Edit position 01', exact: true }).click();
  await expect(page.getByRole('combobox', { name: /^Plate at/ })).toHaveCount(1);
  await page.getByRole('combobox', { name: 'Plate at 01', exact: true }).click();
  await page.getByRole('option', { name: 'P200', exact: true }).click();
  const reads = state.reads; await page.waitForTimeout(1200); expect(state.reads).toBe(reads);
  await page.getByRole('button', { name: /Save changes/ }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Save failed' })).toBeVisible();
  await expect(page.getByTestId('cytomat-position-1')).toContainText('Empty');
  await page.evaluate(() => { history.pushState(null, '', '/labware'); dispatchEvent(new PopStateEvent('popstate')); });
  await page.evaluate(() => { history.pushState(null, '', '/labware?section=cytomat'); dispatchEvent(new PopStateEvent('popstate')); });
  await expect(page.getByRole('combobox', { name: 'Plate at 01', exact: true })).toHaveText('P200');
  state.failSave = false; let release!: () => void; state.saveGate = new Promise<void>(resolve => { release = resolve; });
  await page.getByRole('button', { name: /Save changes/ }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  for (const editor of await page.getByRole('combobox', { name: /^Plate at/ }).all()) await expect(editor).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Edit position 1', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Discard', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('button', { name: /Save changes/ })).toBeDisabled();
  expect(state.writes[1]).toEqual({ updates: [{ cytomat_pos: '1', plate_id: '' }, { cytomat_pos: '01', plate_id: 'P200' }] });
  await page.screenshot({ path: info.outputPath('cytomat-batch.png'), fullPage: true, animations: 'disabled' });
});

test('read-only Cytomat keeps shelf state and unused positions without editors', async ({ page }, info) => {
  const state = await fixture(page, false); await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/labware?section=cytomat');
  await expect(page.getByTestId('cytomat-position-1')).toContainText('P100');
  await expect(page.getByTestId('cytomat-position-2')).toContainText('Empty');
  await expect(page.getByTestId('cytomat-position-4')).toContainText('Unavailable');
  await expect(page.getByRole('region', { name: 'Unused positions', exact: true })).toContainText('P800');
  await expect(page.getByRole('combobox', { name: /^Plate at/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Save changes/ })).toHaveCount(0);
  expect(state.writes).toEqual([]);
  await page.screenshot({ path: info.outputPath('cytomat-read-only.png'), fullPage: true, animations: 'disabled' });
});

test('duplicate Cytomat IDs block only the ambiguous assignments', async ({ page }, info) => {
  const state = await fixture(page, true, true);
  await page.goto('/labware?section=cytomat');
  for (const position of ['1', 'SPARE']) {
    const group = page.getByRole('group', { name: 'Position ' + position, exact: true });
    await expect(group).toHaveCount(1);
    await expect(group).toContainText('Unavailable · duplicate position');
    await expect(group.getByRole('combobox')).toHaveCount(0);
  }
  await expect(page.getByRole('button', { name: 'Edit position 2', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Edit position 01', exact: true })).toBeEnabled();
  expect(state.writes).toEqual([]);
  await page.screenshot({ path: info.outputPath('cytomat-duplicate.png'), fullPage: true, animations: 'disabled' });
});

test('Cytomat refresh keeps shelf geometry and focus stable and editing invalidates late reads', async ({ page }, info) => {
  const state = await fixture(page);
  await page.goto('/labware?section=cytomat');
  const first = page.getByTestId('cytomat-position-1');
  await expect(first).toContainText('P100');
  const before = await first.boundingBox();
  let release!: () => void; state.readGate = new Promise<void>(resolve => { release = resolve; });
  state.staleRead = true;
  const refresh = page.getByRole('button', { name: 'Refresh', exact: true });
  await refresh.focus(); await refresh.press('Enter');
  await expect.poll(() => state.reads).toBeGreaterThan(1);
  await expect(refresh).toHaveAttribute('aria-busy', 'true');
  await expect(page.getByText('Updating…', { exact: true })).toBeVisible();
  await expect(refresh).toBeFocused();
  await expect(page.getByRole('button', { name: 'Edit position 1', exact: true })).toBeEnabled();
  const during = await first.boundingBox();
  expect(during!.y).toBe(before!.y); expect(during!.height).toBe(before!.height);
  await page.getByRole('button', { name: 'Edit position 1', exact: true }).click();
  const editor = page.getByRole('combobox', { name: 'Plate at 1', exact: true });
  await expect(editor).toBeVisible(); release(); state.readGate = null;
  await page.waitForTimeout(1200);
  await expect(editor).toBeEnabled(); await expect(editor).toHaveText('P100');
  const reads = state.reads; await page.waitForTimeout(1200); expect(state.reads).toBe(reads);
  await editor.click(); await page.getByRole('option', { name: 'Empty', exact: true }).click();
  await page.getByRole('button', { name: 'Done editing position 1', exact: true }).click();
  await expect(page.getByRole('combobox', { name: /^Plate at/ })).toHaveCount(0);
  await expect(first).toContainText('Empty'); await expect(first).toContainText('Unsaved');
  expect(state.writes).toEqual([]);
  await page.screenshot({ path: info.outputPath('cytomat-stable-refresh-draft.png'), fullPage: true, animations: 'disabled' });
});

test('Cytomat phone editor supports keyboard closure and resumes clean reads', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 740 });
  const state = await fixture(page); await page.goto('/labware?section=cytomat');
  const edit = page.getByRole('button', { name: 'Edit position 2', exact: true });
  await edit.focus(); await edit.press('Enter');
  const editor = page.getByRole('combobox', { name: 'Plate at 2', exact: true });
  await expect(editor).toBeFocused();
  const done = page.getByRole('button', { name: 'Done editing position 2', exact: true });
  expect((await done.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const reads = state.reads; await page.waitForTimeout(1200); expect(state.reads).toBe(reads);
  await page.screenshot({ path: info.outputPath('cytomat-phone-editor.png'), fullPage: true, animations: 'disabled' });
  await editor.press('Escape');
  await expect(edit).toBeFocused();
  await expect.poll(() => state.reads).toBeGreaterThan(reads);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(state.writes).toEqual([]);
});

test('all nine Cytomat positions fit a short desktop while preserving touch targets', async ({ page }, info) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const state = await fixture(page, true, false, false);
  await page.goto('/labware?section=cytomat');
  const last = page.getByRole('group', { name: 'Position 9', exact: true });
  await expect(last).toContainText('Unused');
  await expect(page.getByRole('region', { name: 'Other positions', exact: true })).toHaveCount(0);
  const bounds = await last.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(720);
  const body = await page.getByTestId('cytomat-register-body').boundingBox();
  expect(Math.abs(bounds!.y + bounds!.height - body!.y - body!.height)).toBeLessThanOrEqual(2);
  const button = await page.getByRole('button', { name: 'Edit position 1', exact: true }).boundingBox();
  expect(button!.height).toBeGreaterThanOrEqual(44);
  expect(button!.width).toBeGreaterThanOrEqual(44);
  expect(state.writes).toEqual([]);
  await info.attach('cytomat-short-desktop-geometry', { body: JSON.stringify({ lastPosition: bounds, editButton: button }), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath('cytomat-nine-positions-1280.png'), animations: 'disabled' });
});

for (const [width, height] of [[3840, 2160], [1920, 1080]]) test(`Cytomat fills remaining workspace with equal shelves at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height }); await fixture(page, true, false, false);
  await page.goto('/labware?section=cytomat');
  const body = page.getByTestId('cytomat-register-body');
  await expect(page.getByRole('group', { name: 'Position 9', exact: true })).toBeVisible();
  const bounds = await body.boundingBox();
  expect(height - bounds!.y - bounds!.height).toBeGreaterThanOrEqual(0);
  expect(height - bounds!.y - bounds!.height).toBeLessThanOrEqual(25);
  const shelves = [];
  for (let position = 1; position <= 9; position++) shelves.push(await page.getByRole('group', { name: 'Position ' + position, exact: true }).boundingBox());
  expect(Math.max(...shelves.map(box => box!.height)) - Math.min(...shelves.map(box => box!.height))).toBeLessThanOrEqual(1.1);
  expect(Math.abs(shelves[8]!.y + shelves[8]!.height - bounds!.y - bounds!.height)).toBeLessThanOrEqual(2);
  expect(await body.evaluate(element => element.scrollHeight - element.clientHeight)).toBeLessThanOrEqual(2);
  await info.attach('full-workspace-shelf-geometry', { body: JSON.stringify({ viewport: { width, height }, body: bounds, shelves }), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath(`cytomat-full-workspace-${width}.png`), animations: 'disabled' });
});

test('Cytomat inline drafts survive desktop-phone resizing with one usable scroll area', async ({ page }, info) => {
  const state = await fixture(page); await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/labware?section=cytomat');
  await page.getByRole('button', { name: 'Edit position 1', exact: true }).click();
  const editor = page.getByRole('combobox', { name: 'Plate at 1', exact: true });
  await editor.click(); await page.getByRole('option', { name: 'Empty', exact: true }).click();
  await editor.evaluate(element => { (window as any).__cytomatEditor = element; });
  const body = page.getByTestId('cytomat-register-body');
  expect(await body.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  const before = await page.getByRole('group', { name: 'Position 2', exact: true }).boundingBox();
  await page.waitForTimeout(1200);
  expect(await page.getByRole('group', { name: 'Position 2', exact: true }).boundingBox()).toEqual(before);
  for (const viewport of [{ width: 1280, height: 720 }, { width: 320, height: 740 }, { width: 1280, height: 420 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    await expect(editor).toHaveText('Empty');
    expect(await editor.evaluate(element => element === (window as any).__cytomatEditor)).toBe(true);
    const expectedOverflow = viewport.width < 900 || viewport.height === 420 ? 'visible' : 'auto';
    await expect.poll(() => body.evaluate(element => getComputedStyle(element).overflowY)).toBe(expectedOverflow);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: info.outputPath(`cytomat-draft-resize-${viewport.width}x${viewport.height}.png`), fullPage: true, animations: 'disabled' });
  }
  expect(state.writes).toEqual([]);
});

test('Cytomat uses CSS workspace dimensions on a high-DPI desktop', async ({ browser, baseURL }, info) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  try {
    const page = await context.newPage(); await fixture(page, true, false, false);
    await page.goto('/labware?section=cytomat');
    const body = page.getByTestId('cytomat-register-body'); await expect(body).toBeVisible();
    const bounds = await body.boundingBox();
    expect(bounds!.width).toBeGreaterThan(1600);
    expect(1080 - bounds!.y - bounds!.height).toBeLessThanOrEqual(25);
    expect(await body.evaluate(element => getComputedStyle(element).transform)).toBe('none');
    await info.attach('high-dpi-css-geometry', { body: JSON.stringify({ cssBounds: bounds, deviceScaleFactor: 2 }), contentType: 'application/json' });
    await page.screenshot({ path: info.outputPath('cytomat-1920-at-2x.png'), animations: 'disabled' });
  } finally { await context.close(); }
});
