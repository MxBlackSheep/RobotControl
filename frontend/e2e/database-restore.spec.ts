import { expect, test } from '@playwright/test';

/** Failure cases for starting a database restore:
 * - A restore that succeeds after more than 10 s (the shared API timeout) is reported as
 *   "Restore Failed: Request timed out" instead of "Restore Started".
 * - While a long restore is in progress, Restore and Cancel become usable again and a
 *   second restore request can be sent.
 * Not checked here: the restore limit covering the backend RESTORE_TIMEOUT (600 s) plus
 * margin, and other requests keeping the shared 10 s limit; see RESTORE_REQUEST_TIMEOUT_MS
 * in DatabaseRestore.tsx.
 */
const backup = {
  filename: 'slow_restore_fixture.bak',
  file_size: 52428800,
  file_size_formatted: '50.0 MB',
  created_date: '2026-09-28T09:00:00',
  description: 'Fixture for a restore slower than the shared API timeout',
  is_valid: true,
  database_name: 'EvoYeast',
  sql_server: 'LOCALHOST\\HAMILTON',
};
const RESTORE_DELAY_MS = 12_000;

test('restore answered after more than 10 s still shows Restore Started', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/admin/backup/list', route => route.fulfill({ json: { success: true, data: [backup] } }));
  const restoreRequests: { body: unknown; answeredAfterMs: number }[] = [];
  await page.route('**/api/admin/backup/restore', async route => {
    const started = Date.now();
    await new Promise(resolve => setTimeout(resolve, RESTORE_DELAY_MS));
    restoreRequests.push({ body: route.request().postDataJSON(), answeredAfterMs: Date.now() - started });
    await route.fulfill({ json: { success: true, data: { success: true, backup_filename: backup.filename }, message: 'Database restored successfully' } });
  }, { times: 5 });

  await page.goto('/database?section=restore');
  await page.locator('.MuiFormControl-root', { hasText: 'Select Backup File' }).getByRole('combobox').click();
  await page.getByRole('option', { name: new RegExp(backup.filename) }).click();
  await page.getByRole('button', { name: 'Restore Database', exact: true }).click();

  const confirm = page.getByRole('dialog').filter({ hasText: 'Restore Database - Confirmation Required' });
  await confirm.getByRole('checkbox', { name: /permanently replace all current database data/ }).check();
  await confirm.getByRole('checkbox', { name: /temporarily unavailable during the restore/ }).check();
  const clickedAt = Date.now();
  await confirm.getByRole('button', { name: 'Restore Database', exact: true }).click();

  // Past the shared 10 s timeout the request must still be pending, not failed.
  await page.waitForTimeout(10_500);
  await expect(confirm.getByRole('button', { name: 'Restoring...' })).toBeDisabled();
  await expect(confirm.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled();
  await expect(page.getByText('Restore Failed')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('restore-still-running-after-10s.png') });

  const started = page.getByRole('dialog').filter({ hasText: 'Restore Started' });
  await expect(started).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Restore Failed')).toHaveCount(0);
  await expect(confirm).toHaveCount(0);
  const shownAfterMs = Date.now() - clickedAt;

  expect(restoreRequests).toHaveLength(1);
  expect(restoreRequests[0].body).toEqual({ filename: backup.filename });
  expect(restoreRequests[0].answeredAfterMs).toBeGreaterThan(10_000);
  await page.screenshot({ path: testInfo.outputPath('restore-started-after-slow-response.png') });
  await testInfo.attach('restore-timing.json', {
    contentType: 'application/json',
    body: JSON.stringify({ restoreRequests, shownAfterMs }, null, 2),
  });
});
