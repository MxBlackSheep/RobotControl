import { expect, Page, test } from '@playwright/test';
import { routeDatabaseViewer, viewerRows as rows } from './database-fixture';

/** Failure cases for the read-only table and SQL viewer:
 * - Narrow screens show the selected table or SQL, not the whole catalogue above it;
 *   Back keeps selection, search draft and scroll. Wide data scrolls locally, never the
 *   whole page. Reading and close controls stay reachable in short windows.
 * - Phones (under 600 px) scroll a table with the page, not in a box (the owner saw 1.5
 *   of 32 rows): at least 6 rows show at 390x844 and 375x667, nothing in the workspace
 *   scrolls vertically, headings stay pinned and aligned with their columns after a
 *   sideways swipe, the Row column stays put, the right-edge fade marks more columns, and
 *   the paging bar stays on screen and shows the next page from its first row. Search
 *   still applies on Enter and Expand stays reachable through More.
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
async function assertNoPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await routeDatabaseViewer(page);
});

for (const size of [{ width: 390, height: 844 }, { width: 1920, height: 1080 }]) {
  test(`table and SQL inspection at ${size.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(size);
    const phone = size.width < 600;
    const count = (total: number) => page.getByText(phone ? `1–${Math.min(total, 25)} of ${total}` : `${total} matching rows`, { exact: true });
    const expand = async () => {
      if (!phone) return page.getByRole('button', { name: 'Expand table' }).click();
      await page.getByRole('button', { name: 'More table options' }).click();
      await page.getByRole('menuitem', { name: 'Expand table' }).click();
    };
    const writes: string[] = [];
    page.on('request', request => { if (request.url().includes('/api/database/') && request.method() !== 'GET') writes.push(request.url()); });
    await page.goto('/database?section=tables');
    await page.getByRole('button', { name: /ViewerSamples Has data/ }).click();
    await expect(count(57)).toBeVisible();
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
    await expect(count(1)).toBeVisible();
    await expand();
    await expect(page.getByRole('dialog', { name: 'Expanded table ViewerSamples' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Search all supported columns' })).toHaveValue('Sample 02');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: phone ? 'More table options' : 'Expand table' })).toBeFocused();
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
  await expect(page.getByText('1–25 of 57', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'More table options' }).click();
  await page.getByRole('menuitem', { name: 'Expand table' }).click();
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

/** Rows between the pinned headings and the paging bar, and where those two sit on screen. */
const phoneTableLayout = (page: Page) => page.evaluate(() => {
  const heading = [...document.querySelectorAll('th')].find(cell => cell.textContent === 'OD' && !cell.closest('[aria-hidden="true"]'))!;
  const strip = heading.closest('table')!.parentElement!.getBoundingClientRect();
  const bar = document.querySelector('.MuiTablePagination-root')!.parentElement!.getBoundingClientRect();
  const rows = [...document.querySelectorAll('button[aria-label^="Inspect row"]')].map(button => button.closest('tr')!.getBoundingClientRect());
  return {
    rows: rows.filter(row => row.top >= strip.bottom - 1 && row.bottom <= bar.top + 1).length,
    stripTop: strip.top, barBottom: bar.bottom, viewport: innerHeight,
    header: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--app-header-height')),
  };
});

for (const size of [{ width: 390, height: 844 }, { width: 375, height: 667 }]) {
  test(`phone table scrolls with the page, keeps headings, Row column and paging at ${size.width}x${size.height}`, async ({ page }, testInfo) => {
    await page.setViewportSize(size);
    await page.goto('/database?section=tables');
    await page.getByRole('button', { name: /dbo\.ActivePlateView/ }).click();
    await expect(page.getByText('1–25 of 32', { exact: true })).toBeVisible();
    const workspace = page.getByLabel('Database table workspace');
    // One scroll: nothing inside the workspace scrolls vertically.
    expect(await workspace.evaluate(root => [...root.querySelectorAll('*')].filter(element =>
      /auto|scroll/.test(getComputedStyle(element).overflowY) && element.scrollHeight > element.clientHeight + 1).length)).toBe(0);
    // The pinned headings are the only ones screen readers and the keyboard reach.
    await expect(page.getByRole('button', { name: 'OD', exact: true })).toHaveCount(1);
    if (size.height >= 844) expect((await phoneTableLayout(page)).rows).toBeGreaterThanOrEqual(6);
    await testInfo.attach(`phone-table-${size.width}-open`, { body: await page.screenshot(), contentType: 'image/png' });

    await page.mouse.wheel(0, 600);
    await expect.poll(async () => { const layout = await phoneTableLayout(page); return Math.abs(layout.stripTop - layout.header); }).toBeLessThan(1);
    const scrolled = await phoneTableLayout(page);
    expect(scrolled.rows).toBeGreaterThanOrEqual(6);
    expect(scrolled.barBottom).toBeLessThanOrEqual(scrolled.viewport + 1);
    expect(scrolled.barBottom).toBeGreaterThan(scrolled.viewport - 60);

    // Sideways: the Row column stays, headings follow their columns, the fade ends at the last column.
    const rows = page.getByLabel('dbo.ActivePlateView rows');
    const fade = () => page.getByLabel('Database table workspace').evaluate(root =>
      [...root.querySelectorAll('div')].filter(element => getComputedStyle(element).backgroundImage.includes('linear-gradient')).length);
    expect(await fade()).toBe(1);
    const rowButton = page.getByRole('button', { name: 'Inspect row 10', exact: true });
    const before = (await rowButton.boundingBox())!.x;
    await rows.evaluate(element => { element.scrollLeft = element.scrollWidth; });
    await expect.poll(fade).toBe(0);
    expect((await rowButton.boundingBox())!.x).toBeCloseTo(before, 0);
    const odHeading = (await page.getByRole('columnheader', { name: 'OD', exact: true }).boundingBox())!;
    const odCell = (await page.getByRole('button', { name: 'View OD, row 10', exact: true }).locator('xpath=..').boundingBox())!;
    expect(Math.abs(odHeading.x - odCell.x)).toBeLessThan(1);
    expect(Math.abs(odHeading.width - odCell.width)).toBeLessThan(1);
    await testInfo.attach(`phone-table-${size.width}-scrolled`, { body: await page.screenshot(), contentType: 'image/png' });

    // Paging from the bottom bar shows the next page from its first row.
    await page.getByRole('button', { name: 'Go to next page' }).click();
    await expect(page.getByText('26–32 of 32', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Inspect row 26', exact: true })).toBeInViewport();
    await page.getByRole('textbox', { name: 'Search all supported columns' }).fill('Waiting for read');
    await page.getByRole('textbox', { name: 'Search all supported columns' }).press('Enter');
    await expect(page.getByText('1–7 of 7', { exact: true })).toBeVisible();
    await page.setViewportSize({ width: 320, height: 568 });
    await assertNoPageOverflow(page);
  });
}

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