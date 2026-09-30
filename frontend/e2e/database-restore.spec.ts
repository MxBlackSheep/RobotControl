import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for the Database Restore dialog, against faked API answers. The restore
 * API answers a failed restore with HTTP 200 and { success: false, message, data }.
 * - A success:false answer for a browsed .bck shows "Restore Completed" or turns on
 *   maintenance mode, or hides the reason or recovery warnings.
 * - A failed restore closes the confirmation or clears its choices, so retrying means
 *   starting over.
 * - A success stops turning on maintenance or drops the server's warnings.
 * - One click sends the restore request more than once, or sends the wrong body.
 * - A response beyond the shared 10 s timeout must keep the confirmation busy and
 *   eventually display completion; the SQL check cannot detect a browser timeout.
 * - Stale listings must not change the backup being selected; navigating clears old
 *   selection, and slow responses must retain the next path draft.
 * Real SQL Server restores, runner timeouts and the failure body shape are checked by
 * backend/e2e/backup_restore_check.py.
 */
const evidence = process.env.ROBOTCONTROL_E2E_EVIDENCE || '../test-output/database-restore-verification';
const bak = { filename: 'EvoYeast_20260101_120000.bak', file_size: 2048, file_size_formatted: '2 KB', created_date: '2026-01-01T12:00:00', description: 'Fixture backup', is_valid: true };
const bckPath = 'C:\\Backups\\nightly.bck';

async function openRestore(page: any, answer: any) {
  mkdirSync(evidence, { recursive: true });
  const sent: any[] = [];
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (r: any) => r.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
  await page.route('**/api/admin/backup/list', (r: any) => r.fulfill({ json: { success: true, data: [bak] } }));
  await page.route('**/api/system/browse?*', (r: any) => r.fulfill({ json: { success: true, data: { items: [{ name: 'nightly.bck', path: bckPath, is_directory: false }] } } }));
  await page.route('**/api/admin/backup/restore', (r: any) => { sent.push(r.request().postDataJSON()); return r.fulfill({ json: answer }); });
  await page.goto('/database?section=restore');
  return sent;
}

async function confirmRestore(page: any) {
  await page.getByRole('button', { name: 'Restore Database', exact: true }).click();
  const confirm = page.getByRole('dialog').filter({ hasText: 'Confirmation Required' });
  await confirm.getByRole('checkbox').nth(0).check();
  await confirm.getByRole('checkbox').nth(1).check();
  await confirm.getByRole('button', { name: 'Restore Database', exact: true }).click();
  return confirm;
}

test('failed .bck restore shows the reason and keeps the confirmation for retry', async ({ page }) => {
  const warning = 'Database may still be in single-user mode';
  const failed = { success: false, message: 'Database restore failed', data: { success: false, error_details: 'SQL Server error: The media family on device is incorrectly formed.', warnings: [warning] } };
  const sent = await openRestore(page, failed);
  await page.getByRole('tab', { name: 'Browse Files (.bck)' }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  await page.getByRole('button', { name: 'nightly.bck', exact: false }).click();
  await page.getByRole('button', { name: 'Select File', exact: true }).click();
  await expect(page.getByLabel('Selected .bck File')).toHaveValue(bckPath);
  const confirm = await confirmRestore(page);

  const status = page.getByRole('dialog', { name: 'Restore Failed' });
  for (const t of [failed.message, failed.data.error_details, warning]) await expect(status).toContainText(t);
  await page.screenshot({ path: `${evidence}/bck-failed.png`, animations: 'disabled' });
  await expect(page.getByText('Database Maintenance In Progress')).toHaveCount(0);
  // The confirmation stays open with its choices so the user can retry or cancel.
  await status.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(confirm).toBeVisible();
  await expect(confirm.getByRole('checkbox').nth(0)).toBeChecked();
  await expect(confirm.getByRole('checkbox').nth(1)).toBeChecked();
  expect(sent).toEqual([{ file_path: bckPath }]);
});

test('slow successful restore stays pending, then shows warnings and maintenance', async ({ page }) => {
  const warning = 'Database connectivity check after restore timed out';
  const sent = await openRestore(page, { success: true, message: 'Database restored successfully', data: { warnings: [warning] } });
  await page.getByRole('main').getByRole('combobox').click();
  await page.getByRole('option', { name: bak.filename, exact: false }).click();
  await page.route('**/api/admin/backup/restore', async route => {
    sent.push(route.request().postDataJSON());
    await new Promise(resolve => setTimeout(resolve, 12_000));
    await route.fulfill({ json: { success: true, message: 'Database restored successfully', data: { warnings: [warning] } } });
  });
  const confirm = await confirmRestore(page);
  await page.waitForTimeout(10_500);
  await expect(confirm.getByRole('button', { name: 'Restoring...' })).toBeDisabled();
  await expect(confirm.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled();
  await expect(page.getByText('Restore Failed')).toHaveCount(0);

  const dialog = page.getByRole('dialog', { name: 'Restore Completed with Warnings' });
  await expect(dialog).toContainText(warning);
  await expect(page.getByText('Database Maintenance In Progress')).toBeVisible();
  await expect(confirm).toHaveCount(0);
  await page.screenshot({ path: `${evidence}/completed-with-warnings.png`, animations: 'disabled' });
  expect(sent).toEqual([{ filename: bak.filename }]);
});


test('backup selection survives stale listings and preserves the next path draft', async ({ page }) => {
  await openRestore(page, { success: false });
  await page.unroute('**/api/system/browse?*');
  const paths: string[] = [];
  let releaseOld!: () => void;
  let releaseCurrent!: () => void;
  const old = new Promise<void>(resolve => { releaseOld = resolve; });
  const current = new Promise<void>(resolve => { releaseCurrent = resolve; });
  await page.route('**/api/system/browse?*', async route => {
    const path = new URL(route.request().url()).searchParams.get('path')!;
    paths.push(path);
    if (path === 'C:\\slow') await old;
    if (path === 'D:\\Backups') await current;
    await route.fulfill({ json: { success: true, data: { current_path: path, items: [{
      name: path === 'C:\\slow' ? 'obsolete.bck' : 'current.bck',
      path: `${path}\\current.bck`, is_directory: false,
    }] } } });
  });
  await page.getByRole('tab', { name: 'Browse Files (.bck)' }).click();
  await page.getByRole('button', { name: 'Browse', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Browse for .bck Backup Files' });
  const input = dialog.getByLabel('Current Directory');
  const select = dialog.getByRole('button', { name: 'Select File' });
  await dialog.getByRole('button', { name: 'current.bck', exact: false }).click();
  await expect(select).toBeEnabled();
  await input.fill('C:\\slow');
  expect(paths).toEqual(['C:\\']);
  await input.press('Enter');
  await expect.poll(() => paths.at(-1)).toBe('C:\\slow');
  await expect(select).toBeDisabled();
  await input.fill('D:\\Backups');
  await input.press('Enter');
  await expect.poll(() => paths.at(-1)).toBe('D:\\Backups');
  await input.fill('D:\\next');
  releaseCurrent();
  await expect(dialog.getByRole('button', { name: 'current.bck', exact: false })).toBeVisible();
  await expect(input).toHaveValue('D:\\next');
  const staleResponse = page.waitForResponse(response => new URL(response.url()).searchParams.get('path') === 'C:\\slow');
  releaseOld();
  await staleResponse;
  await expect(dialog.getByText('obsolete.bck')).toHaveCount(0);
  await expect(input).toHaveValue('D:\\next');
  await input.press('Enter');
  await expect.poll(() => paths.at(-1)).toBe('D:\\next');
  await dialog.getByRole('button', { name: 'current.bck', exact: false }).click();
  await select.click();
  await expect(page.getByLabel('Selected .bck File')).toHaveValue('D:\\next\\current.bck');
  await page.screenshot({ path: `${evidence}/selected-backup-after-pending-listings.png`, animations: 'disabled' });
});
