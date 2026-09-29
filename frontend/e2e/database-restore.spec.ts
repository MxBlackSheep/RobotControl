import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for the Database Restore dialog. The restore API answers a failed
 * restore with HTTP 200 and { success: false, message, data.error_details }.
 * - A success:false answer for a managed .bak or a browsed .bck shows "Restore Completed"
 *   instead of "Restore Failed", or turns on maintenance mode.
 * - The failure dialog hides the reason: message or error_details is missing, or an
 *   empty text is shown instead of a fallback.
 * - A failed restore closes the confirmation dialog or clears its choices, so retrying
 *   means starting over.
 * - A real success stops showing "Restore Completed" or stops turning on maintenance.
 * - A non-2xx answer no longer shows its `detail`.
 * - One click sends the restore request more than once.
 * - Selecting a .bck opens an obsolete modal instead of showing the path inline.
 * - A response after the shared 10 s timeout falsely fails, enables Cancel/Restore
 *   while pending, or loses the actual success/failure response.
 * - Browser responses must use the real success/data/items envelope. Typing must not
 *   request partial paths; stale responses and old selections must not survive navigation.
 * - Parent navigation must retain drive roots; errors must allow retry.
 * - A typed "/" path must show the server's resolved path, and Parent must not cut
 *   characters from a path without "\".
 * - Completed restores must retain backend warnings and use warning styling.
 * The full 660 s timeout and real SQL timing are not exercised by these fixtures.
 * Real SQL Server restores and the failure body shape are checked by
 * backend/e2e/backup_restore_check.py.
 */
const evidence = process.env.ROBOTCONTROL_E2E_EVIDENCE || '../test-output/database-restore-verification';
const failed = { success: false, message: 'Database restore failed', data: { success: false, error_details: 'SQL Server error: The media family on device is incorrectly formed.' } };
const bak = { filename: 'EvoYeast_20260101_120000.bak', file_size: 2048, file_size_formatted: '2 KB', created_date: '2026-01-01T12:00:00', description: 'Fixture backup', is_valid: true };
const bckPath = 'C:\\Backups\\nightly.bck';

async function openRestore(page: any, answer: { status?: number; json: any }) {
  mkdirSync(evidence, { recursive: true });
  const sent: any[] = [];
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (r: any) => r.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
  await page.route('**/api/admin/backup/list', (r: any) => r.fulfill({ json: { success: true, data: [bak] } }));
  await page.route('**/api/system/browse?*', (r: any) => r.fulfill({ json: { success: true, data: { items: [{ name: 'nightly.bck', path: bckPath, is_directory: false }] } } }));
  await page.route('**/api/admin/backup/restore', (r: any) => { sent.push(r.request().postDataJSON()); return r.fulfill({ status: answer.status ?? 200, json: answer.json }); });
  await page.goto('/database?section=restore');
  return sent;
}

async function chooseBak(page: any) {
  // The MUI Select is not linked to its "Select Backup File" label, so it has no accessible name.
  await page.getByRole('main').getByRole('combobox').click();
  await page.getByRole('option', { name: bak.filename, exact: false }).click();
}

async function chooseBck(page: any) {
  await page.getByRole('tab', { name: 'Browse Files (.bck)' }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  await page.getByRole('button', { name: 'nightly.bck', exact: false }).click();
  await expect(page.getByRole('alert')).toContainText(`Path: ${bckPath}`);
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Select File', exact: true }).click();
  await expect(page.getByLabel('Selected .bck File')).toHaveValue(bckPath);
}

async function confirmRestore(page: any) {
  await page.getByRole('button', { name: 'Restore Database', exact: true }).click();
  const confirm = page.getByRole('dialog').filter({ hasText: 'Confirmation Required' });
  await confirm.getByRole('checkbox').nth(0).check();
  await confirm.getByRole('checkbox').nth(1).check();
  await confirm.getByRole('button', { name: 'Restore Database', exact: true }).click();
  return confirm;
}

async function expectFailure(page: any, confirm: any, text: string[], shot: string) {
  const status = page.getByRole('dialog', { name: 'Restore Failed' });
  await expect(status).toBeVisible();
  for (const t of text) await expect(status).toContainText(t);
  await page.screenshot({ path: `${evidence}/${shot}.png`, animations: 'disabled' });
  await expect(page.getByText('Restore Completed')).toHaveCount(0);
  await expect(page.getByText('Database Maintenance In Progress')).toHaveCount(0);
  // The confirmation stays open with its choices so the user can retry or cancel.
  // It is hidden from the accessibility tree while the status dialog is on top.
  await status.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(status).toHaveCount(0);
  await expect(confirm).toBeVisible();
  await expect(confirm.getByRole('checkbox').nth(0)).toBeChecked();
  await expect(confirm.getByRole('checkbox').nth(1)).toBeChecked();
}

test('failed .bak restore shows Restore Failed with the reason and no maintenance', async ({ page }) => {
  const sent = await openRestore(page, { json: failed });
  await chooseBak(page);
  const confirm = await confirmRestore(page);
  await expectFailure(page, confirm, [failed.message, failed.data.error_details], 'bak-failed');
  expect(sent).toEqual([{ filename: bak.filename }]);
});

for (const succeeds of [true, false]) {
  test(`slow restore preserves pending state then reports ${succeeds ? 'success' : 'failure'}`, async ({ page }, testInfo) => {
    await openRestore(page, { json: failed });
    await page.unroute('**/api/admin/backup/restore');
    const requests: unknown[] = [];
    await page.route('**/api/admin/backup/restore', async route => {
      requests.push(route.request().postDataJSON());
      await new Promise(resolve => setTimeout(resolve, 12_000));
      await route.fulfill({ json: succeeds ? { success: true } : failed });
    });
    await chooseBak(page);
    const startedAt = Date.now();
    const confirm = await confirmRestore(page);
    await page.waitForTimeout(10_500);
    await expect(confirm.getByRole('button', { name: 'Restoring...' })).toBeDisabled();
    await expect(confirm.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled();
    await expect(page.getByText('Restore Failed')).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('restore-pending-after-10s.png'), animations: 'disabled' });
    if (succeeds) {
      await expect(page.getByRole('dialog', { name: 'Restore Completed' })).toBeVisible();
      await expect(confirm).toHaveCount(0);
    } else {
      await expectFailure(page, confirm, [failed.message, failed.data.error_details], 'slow-failed');
    }
    expect(requests).toEqual([{ filename: bak.filename }]);
    await testInfo.attach('restore-timing.json', {
      contentType: 'application/json',
      body: JSON.stringify({ requests, elapsedMs: Date.now() - startedAt, responseDelayMs: 12_000 }),
    });
  });
}

test('failed .bck restore shows Restore Failed with the reason and no maintenance', async ({ page }) => {
  const sent = await openRestore(page, { json: failed });
  await chooseBck(page);
  const confirm = await confirmRestore(page);
  await expectFailure(page, confirm, [failed.message, failed.data.error_details], 'bck-failed');
  expect(sent).toEqual([{ file_path: bckPath }]);
});

test('failed restore without details or message still explains itself', async ({ page }) => {
  const sent = await openRestore(page, { json: { success: false, message: 'Backup file not found', data: { error_details: null } } });
  await chooseBak(page);
  const confirm = await confirmRestore(page);
  await expectFailure(page, confirm, ['Backup file not found'], 'failed-message-only');
  // Retry from the still-open confirmation; this time the body has no message at all.
  await page.unroute('**/api/admin/backup/restore');
  await page.route('**/api/admin/backup/restore', (r: any) => { sent.push(r.request().postDataJSON()); return r.fulfill({ json: { success: false } }); });
  await confirm.getByRole('button', { name: 'Restore Database', exact: true }).click();
  await expectFailure(page, confirm, ['Failed to restore backup'], 'failed-empty');
  expect(sent).toHaveLength(2);
});

test('HTTP error restore shows the server detail', async ({ page }) => {
  const sent = await openRestore(page, { status: 500, json: { detail: 'An unexpected error occurred during database restore' } });
  await chooseBak(page);
  const confirm = await confirmRestore(page);
  await expectFailure(page, confirm, ['An unexpected error occurred during database restore'], 'http-500');
  expect(sent).toHaveLength(1);
});

test('successful restore shows Restore Completed and turns on maintenance', async ({ page }) => {
  const sent = await openRestore(page, { json: { success: true, message: 'Database restored successfully', data: { success: true } } });
  await chooseBak(page);
  const confirm = await confirmRestore(page);
  await expect(page.getByText('Restore Completed')).toBeVisible();
  await expect(page.getByText('Database Maintenance In Progress')).toBeVisible();
  await expect(confirm).toHaveCount(0);
  await expect(page.getByText('Restore Failed')).toHaveCount(0);
  await page.screenshot({ path: `${evidence}/success.png`, animations: 'disabled' });
  expect(sent).toHaveLength(1);
});


test('restore completion displays server warnings', async ({ page }) => {
  const warning = 'Database connectivity check after restore timed out';
  await openRestore(page, { json: { success: true, message: 'Database restored successfully', data: { warnings: [warning] } } });
  await chooseBak(page);
  await confirmRestore(page);
  const dialog = page.getByRole('dialog', { name: 'Restore Completed with Warnings' });
  await expect(dialog).toContainText(warning);
  await expect(dialog.locator('.MuiAlert-standardWarning')).toBeVisible();
  await page.screenshot({ path: `${evidence}/completed-with-warnings.png`, animations: 'disabled' });
});

test('browser submits paths explicitly, ignores old responses and preserves drive roots', async ({ page }) => {
  await openRestore(page, { json: failed });
  await page.unroute('**/api/system/browse?*');
  const paths: string[] = [];
  let releaseOld!: () => void;
  const old = new Promise<void>(resolve => { releaseOld = resolve; });
  await page.route('**/api/system/browse?*', async route => {
    const path = new URL(route.request().url()).searchParams.get('path')!;
    paths.push(path);
    if (path === 'C:\\slow') await old;
    await route.fulfill({ json: { success: true, data: { items: [{
      name: path === 'C:\\slow' ? 'obsolete.bck' : 'current.bck',
      path: `${path}\\current.bck`, is_directory: false,
    }] } } });
  });
  await page.getByRole('tab', { name: 'Browse Files (.bck)' }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Browse for .bck Backup Files' });
  const input = dialog.getByLabel('Current Directory');
  await expect(dialog.getByRole('button', { name: 'current.bck', exact: false })).toBeVisible();
  await dialog.getByRole('button', { name: 'current.bck', exact: false }).click();
  await expect(dialog.getByRole('button', { name: 'Select File' })).toBeEnabled();
  const count = paths.length;
  await input.fill('C:\\slow');
  await page.waitForTimeout(300);
  expect(paths).toHaveLength(count);
  await input.press('Enter');
  await expect.poll(() => paths.at(-1)).toBe('C:\\slow');
  await expect(dialog.getByRole('button', { name: 'Select File' })).toBeDisabled();
  await input.fill('D:\\Users');
  await dialog.getByRole('button', { name: 'Go', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'current.bck', exact: false })).toBeVisible();
  releaseOld();
  await page.waitForTimeout(300);
  await expect(dialog.getByText('obsolete.bck')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Parent Directory' }).click();
  await expect(input).toHaveValue('D:\\');
  await expect.poll(() => paths.at(-1)).toBe('D:\\');
  await expect(dialog.getByRole('button', { name: 'Parent Directory' })).toBeDisabled();
  await page.screenshot({ path: `${evidence}/browser-drive-root.png`, animations: 'disabled' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(input).toHaveValue('D:\\');
  await page.screenshot({ path: `${evidence}/browser-drive-root-phone.png`, animations: 'disabled' });
  await page.setViewportSize({ width: 1280, height: 720 });
  await dialog.getByRole('button', { name: 'current.bck', exact: false }).click();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Select File' })).toBeDisabled();
});

test('browser uses the server path so Parent works after a typed forward-slash path', async ({ page }) => {
  await openRestore(page, { json: failed });
  await page.unroute('**/api/system/browse?*');
  const paths: string[] = [];
  await page.route('**/api/system/browse?*', route => {
    const path = new URL(route.request().url()).searchParams.get('path')!;
    paths.push(path);
    // Mirrors Path(path).resolve() in backend/api/system.py on Windows.
    return route.fulfill({ json: { success: true, data: { current_path: path.replace(/\//g, '\\'), items: [] } } });
  });
  await page.getByRole('tab', { name: 'Browse Files (.bck)' }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Browse for .bck Backup Files' });
  const input = dialog.getByLabel('Current Directory');
  await input.fill('C:/Backups/Robot');
  await input.press('Enter');
  await expect(input).toHaveValue('C:\\Backups\\Robot');
  await dialog.getByRole('button', { name: 'Parent Directory' }).click();
  await expect.poll(() => paths.at(-1)).toBe('C:\\Backups');
  await expect(input).toHaveValue('C:\\Backups');
});

test('browser reports a directory error and allows retry', async ({ page }) => {
  await openRestore(page, { json: failed });
  await page.route('**/api/system/browse?*', route => route.fulfill({ status: 400, json: { detail: 'Directory is unavailable' } }));
  await page.getByRole('tab', { name: 'Browse Files (.bck)' }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Browse for .bck Backup Files' });
  await expect(dialog.getByRole('alert')).toContainText('Directory is unavailable');
  await page.unroute('**/api/system/browse?*');
  await page.route('**/api/system/browse?*', route => route.fulfill({ json: { success: true, data: { items: [] } } }));
  await dialog.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(dialog.getByRole('alert')).toHaveCount(0);
  await expect(dialog.getByText('No items found')).toBeVisible();
});


test('failed restore retains recovery warnings', async ({ page }) => {
  const warning = 'Database may still be in single-user mode';
  await openRestore(page, { json: { ...failed, data: { ...failed.data, warnings: [warning] } } });
  await chooseBak(page);
  const confirm = await confirmRestore(page);
  await expectFailure(page, confirm, [failed.message, warning], 'failed-recovery-warning');
});
