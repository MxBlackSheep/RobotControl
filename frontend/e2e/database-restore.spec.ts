import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for the Database Restore dialog. The restore API answers a failed
 * restore with HTTP 200 and { success: false, message, data.error_details }.
 * - A success:false answer for a managed .bak or a browsed .bck shows "Restore Started"
 *   instead of "Restore Failed", or turns on maintenance mode.
 * - The failure dialog hides the reason: message or error_details is missing, or an
 *   empty text is shown instead of a fallback.
 * - A failed restore closes the confirmation dialog or clears its choices, so retrying
 *   means starting over.
 * - A real success stops showing "Restore Started" or stops turning on maintenance.
 * - A non-2xx answer no longer shows its `detail`.
 * - One click sends the restore request more than once.
 * Real SQL Server restores and the failure body shape are checked by
 * backend/e2e/backup_restore_check.py (added on the fix/restore-from-path branch).
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
  await page.route('**/api/system/browse?*', (r: any) => r.fulfill({ json: { items: [{ name: 'nightly.bck', path: bckPath, is_directory: false }] } }));
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
  // Choosing a file opens an info note titled "Application Error" that covers Select File.
  await page.getByRole('alertdialog').getByRole('button').click();
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
  await expect(page.getByText('Restore Started')).toHaveCount(0);
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

test('successful restore shows Restore Started and turns on maintenance', async ({ page }) => {
  const sent = await openRestore(page, { json: { success: true, message: 'Database restored successfully', data: { success: true } } });
  await chooseBak(page);
  const confirm = await confirmRestore(page);
  await expect(page.getByText('Restore Started')).toBeVisible();
  await expect(page.getByText('Database Maintenance In Progress')).toBeVisible();
  await expect(confirm).toHaveCount(0);
  await expect(page.getByText('Restore Failed')).toHaveCount(0);
  await page.screenshot({ path: `${evidence}/success.png`, animations: 'disabled' });
  expect(sent).toHaveLength(1);
});
