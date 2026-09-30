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
 * Real SQL Server restores, timeouts and the failure body shape are checked by
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

test('successful restore shows warnings and turns on maintenance', async ({ page }) => {
  const warning = 'Database connectivity check after restore timed out';
  const sent = await openRestore(page, { success: true, message: 'Database restored successfully', data: { warnings: [warning] } });
  // The MUI Select is not linked to its "Select Backup File" label, so it has no accessible name.
  await page.getByRole('main').getByRole('combobox').click();
  await page.getByRole('option', { name: bak.filename, exact: false }).click();
  const confirm = await confirmRestore(page);

  const dialog = page.getByRole('dialog', { name: 'Restore Completed with Warnings' });
  await expect(dialog).toContainText(warning);
  await expect(page.getByText('Database Maintenance In Progress')).toBeVisible();
  await expect(confirm).toHaveCount(0);
  await page.screenshot({ path: `${evidence}/completed-with-warnings.png`, animations: 'disabled' });
  expect(sent).toEqual([{ filename: bak.filename }]);
});
