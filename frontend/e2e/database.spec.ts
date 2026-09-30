import { expect, Page, test } from '@playwright/test';

/** Failure cases for the read-only table and SQL viewer:
 * - Narrow screens show the selected table or SQL, not the whole catalogue above it;
 *   Back keeps selection, search draft and scroll. Wide data scrolls locally, never the
 *   whole page. Reading and close controls stay reachable in short windows.
 * - Expand does not re-request data, clear filters or reset Find; Escape restores focus.
 * - The row inspector shows hidden columns and distinguishes NULL, empty and long values.
 *   Copy reports a clipboard failure instead of claiming success.
 * - Search applies on submit, sort direction persists, and older responses never replace
 *   the current selection. A failed refresh keeps useful rows without calling them fresh.
 * - Viewing never calls procedure execution or any other write endpoint.
 * - Escape in an open Find field closes Find (outside the expanded view).
 * - Restore messages (no backups, a failed backup) appear inline, never as a second
 *   dialog stacked over the restore screen or the create-backup dialog.
 */
const rows = Array.from({ length: 57 }, (_, index) => ({
  ID: index + 1,
  Name: `Sample ${String(index + 1).padStart(2, '0')}`,
  Notes: index === 0 ? 'Long complete value: ' + 'laboratory inspection '.repeat(50) : `Observation ${index + 1}`,
  Missing: null,
  Empty: '',
  LongColumnNameForResponsiveInspection: 'Preserved column value',
}));
const sql = '-- Inspection fixture\nCREATE PROCEDURE InspectSamples\n  @sample_id int,\n  @description nvarchar(200)\nAS\nBEGIN\n  SELECT * FROM Samples;\n  SELECT N\'Unicode Ω 中文\';\nEND;';

async function fixtures(page: Page) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/database/tables?*', route => route.fulfill({ json: { success: true, data: {
    table_details: [{ name: 'ViewerSamples', has_data: true, is_important: true }, { name: 'EmptyTable', has_data: false, is_important: true }],
  } } }));
  await page.route('**/api/database/tables/ViewerSamples?*', async route => {
    const query = new URL(route.request().url()).searchParams;
    let selected = rows.filter(row => !query.get('search') || Object.values(row).some(value => String(value).toLowerCase().includes(query.get('search')!.toLowerCase())));
    const filters = JSON.parse(query.get('filters') || '{}');
    for (const [column, filter] of Object.entries(filters) as [string, { value: string; operator: string }][]) {
      selected = selected.filter(row => String(row[column as keyof typeof row]).includes(filter.value));
    }
    if (query.get('sort_direction') === 'desc') selected = [...selected].reverse();
    const limit = Number(query.get('limit') || 25), offset = (Number(query.get('page') || 1) - 1) * limit;
    await route.fulfill({ json: { success: true, data: { columns: Object.keys(rows[0]), rows: selected.slice(offset, offset + limit), total_count: selected.length } } });
  });
  await page.route('**/api/database/tables/EmptyTable?*', route => route.fulfill({ json: { success: true, data: { columns: ['ID'], rows: [], total_count: 0 } } }));
  await page.route('**/api/database/stored-procedures?*', route => route.fulfill({ json: { success: true, data: {
    procedures: [{ name: 'InspectSamples', type: 'PROCEDURE', definition: sql, created_date: '2026-09-01T10:00:00', modified_date: '2026-09-20T12:00:00', parameters: [
      { name: '@sample_id', data_type: 'int', mode: 'IN', max_length: null },
      { name: '@description', data_type: 'nvarchar', mode: 'IN', max_length: 200 },
    ] }],
    functions: [{ name: 'SampleCount', type: 'FUNCTION', definition: 'CREATE FUNCTION SampleCount() RETURNS int AS BEGIN RETURN 57; END', parameters: [] }],
  } } }));
}

async function assertNoPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

test.beforeEach(async ({ page }) => fixtures(page));

for (const size of [{ width: 390, height: 844 }, { width: 1920, height: 1080 }]) {
  test(`table and SQL inspection at ${size.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(size);
    const writes: string[] = [];
    page.on('request', request => { if (request.url().includes('/api/database/') && request.method() !== 'GET') writes.push(request.url()); });
    await page.goto('/database?section=tables');
    await page.getByRole('button', { name: /ViewerSamples Has data/ }).click();
    await expect(page.getByText('57 matching rows')).toBeVisible();
    await assertNoPageOverflow(page);
    await page.getByRole('button', { name: 'Inspect row 1', exact: true }).click();
    const record = page.getByRole('dialog', { name: /Row 1/ });
    await expect(record.getByText('NULL', { exact: true })).toBeVisible();
    await expect(record.getByText('(empty string)', { exact: true })).toBeVisible();
    await expect(record.getByText('LongColumnNameForResponsiveInspection', { exact: true })).toBeVisible();
    await expect(record.getByText(rows[0].Notes, { exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByRole('textbox', { name: 'Search all supported columns' }).fill('Sample 02');
    await page.getByRole('button', { name: 'Apply', exact: true }).click();
    await expect(page.getByText('1 matching rows')).toBeVisible();
    await page.getByRole('button', { name: 'Expand table' }).click();
    await expect(page.getByRole('dialog', { name: 'Expanded table ViewerSamples' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Search all supported columns' })).toHaveValue('Sample 02');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Expand table' })).toBeFocused();
    if (size.width < 900) {
      await page.getByRole('button', { name: 'Back to tables' }).click();
      await page.getByRole('button', { name: /ViewerSamples Has data/ }).click();
      await expect(page.getByRole('textbox', { name: 'Search all supported columns' })).toHaveValue('Sample 02');
    }
    await testInfo.attach(`table-${size.width}`, { body: await page.screenshot(), contentType: 'image/png' });

    await page.goto('/database?section=procedures');
    await page.getByRole('button', { name: /InspectSamples/ }).click();
    await expect(page.getByRole('region', { name: 'SQL definition' })).toContainText('CREATE PROCEDURE');
    await page.getByRole('button', { name: 'Find in SQL', exact: true }).click();
    await page.getByRole('textbox', { name: 'Find in SQL' }).fill('SELECT');
    await expect(page.getByText('1 of 2 matches', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Next match' }).click();
    await expect(page.getByText('2 of 2 matches', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Expand SQL' }).click();
    await expect(page.getByRole('dialog', { name: 'Expanded SQL definition' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Find in SQL' })).toHaveValue('SELECT');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Expand SQL' })).toBeFocused();
    await page.getByRole('textbox', { name: 'Find in SQL' }).press('Escape');
    await expect(page.getByRole('textbox', { name: 'Find in SQL' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Find in SQL', exact: true }).click();
    await expect(page.getByRole('textbox', { name: 'Find in SQL' })).toHaveValue('SELECT');
    await page.getByRole('tab', { name: 'Parameters (2)' }).click();
    await expect(page.getByText('@description', { exact: true })).toBeVisible();
    await page.getByRole('tab', { name: 'SQL definition' }).click();
    await assertNoPageOverflow(page);
    await testInfo.attach(`sql-${size.width}`, { body: await page.screenshot(), contentType: 'image/png' });
    expect(writes).toEqual([]);
  });
}

test('failed refresh retains table data and SQL copy failure is explained', async ({ page }, testInfo) => {
  await page.goto('/database?section=tables');
  await page.getByRole('button', { name: /ViewerSamples Has data/ }).click();
  await expect(page.getByText('57 matching rows')).toBeVisible();
  // A plain read error, so the check is about retained rows rather than service outages.
  await page.route('**/api/database/tables/ViewerSamples?*', route => route.fulfill({ status: 500, json: { detail: 'Fixture read unavailable' } }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Previous rows' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'View Name, row 1', exact: true })).toHaveText('Sample 01');
  await page.goto('/database?section=procedures');
  await page.getByRole('button', { name: /InspectSamples/ }).click();
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('Unavailable')) } }));
  await page.getByRole('button', { name: 'Copy SQL' }).click();
  await expect(page.getByText('Copy unavailable. Select and copy the text below.', { exact: true })).toBeVisible();
  await testInfo.attach('read-failure-and-copy-fallback', { body: await page.screenshot(), contentType: 'image/png' });
});

test('short narrow windows keep reading and close controls reachable', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 390 });
  await page.goto('/database?section=tables');
  await page.getByRole('button', { name: /ViewerSamples Has data/ }).click();
  await expect(page.getByText('57 matching rows')).toBeVisible();
  await page.getByRole('button', { name: 'Expand table' }).click();
  expect((await page.getByLabel('ViewerSamples rows').boundingBox())!.height).toBeGreaterThanOrEqual(119);
  await page.getByRole('button', { name: 'Close expanded table' }).click();
  await page.goto('/database?section=procedures');
  await page.getByRole('button', { name: /InspectSamples/ }).click();
  await page.getByRole('button', { name: 'Expand SQL' }).click();
  expect((await page.getByRole('region', { name: 'SQL definition' }).boundingBox())!.height).toBeGreaterThanOrEqual(119);
  await assertNoPageOverflow(page);
  await testInfo.attach('short-narrow-sql', { body: await page.screenshot(), contentType: 'image/png' });
  await page.getByRole('button', { name: 'Close expanded SQL' }).click();
  await expect(page.getByRole('button', { name: 'Expand SQL' })).toBeVisible();
});

test('restore messages stay inline instead of stacking dialogs', async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/admin/backup/list', route => route.fulfill({ json: { success: true, data: [] } }));
  await page.route('**/api/admin/backup/create', route => route.fulfill({ status: 500, json: { detail: 'Backup folder is not writable' } }));
  await page.goto('/database?section=restore');
  await expect(page.getByRole('alert').filter({ hasText: 'No managed backup files found' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await page.getByRole('button', { name: 'Create Managed Backup', exact: true }).click();
  const create = page.getByRole('dialog', { name: 'Create Managed Backup' });
  await create.getByRole('textbox', { name: 'Backup Description' }).fill('Before restore check');
  await create.getByRole('button', { name: 'Create Backup', exact: true }).click();
  await expect(create.getByRole('alert').filter({ hasText: 'Backup folder is not writable' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath('restore-create-failure.png') });
});