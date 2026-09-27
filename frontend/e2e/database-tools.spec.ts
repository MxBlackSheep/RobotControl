import { test, expect } from '@playwright/test';
import path from 'node:path';

async function login(page: any) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (route: any) => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
  await page.route('**/api/database/tables?*', (route: any) => route.fulfill({ json: { success: true, data: { table_details: [] } } }));
}

test('local admin installs a report package, previews deletion and downloads Excel', async ({ page }) => {
  await login(page);
  await page.goto('/database?section=packages');
  await expect(page.getByText('Culture history · 1.0.0')).toBeVisible();
  await page.locator('input[type=file]').setInputFiles(path.resolve('../recovery/database-verification/culture-history.zip'));
  await page.getByRole('button', { name: 'Install package' }).click();
  await expect(page.getByRole('button', { name: 'Install package' })).toBeDisabled();
  await page.goto('/database?section=operations');
  await page.getByRole('combobox', { name: 'Experiment', exact: true }).fill('43');
  await page.getByRole('option', { name: /43 · Delete fixture/ }).click();
  await page.getByRole('button', { name: 'Review operation' }).click();
  await expect(page.getByRole('dialog')).toContainText('Permanently delete');
  await page.getByLabel('Type 43 to confirm').fill('42');
  await expect(page.getByRole('button', { name: 'Confirm operation' })).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.goto('/database?section=retrieval');
  await page.getByRole('combobox', { name: 'Experiment', exact: true }).fill('42');
  await page.getByRole('option', { name: /42 · Yeast/ }).click();
  await page.getByRole('button', { name: 'Generate Excel' }).click();
  await expect(page.getByRole('button', { name: 'Download Excel' })).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download Excel' }).click();
  expect((await download).suggestedFilename()).toContain('Experiment_42_CultureHistory');
  await page.screenshot({ path: '../recovery/database-verification/desktop-report.png' });
});

test('phone report form fits and retains a completed download', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto('/database?section=retrieval');
  await page.getByRole('combobox', { name: 'Experiment', exact: true }).fill('42');
  await page.getByRole('option', { name: /42 · Yeast/ }).click();
  await page.getByRole('button', { name: 'Generate Excel' }).click();
  await expect(page.getByRole('button', { name: 'Download Excel' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: '../recovery/database-verification/phone-report.png' });
});

test('Delivery Logs displays pending, sent, error and partial results', async ({ page }) => {
  await login(page);
  let requests = 0;
  await page.route('**/api/scheduling/notifications/logs*', route => { requests++; const filter = new URL(route.request().url()).searchParams.get('status'); return route.fulfill({ json: { success: true, data: ['pending', 'sent', 'error', 'partial'].filter(status => !filter || status === filter).map((status, i) => ({
    log_id: `fixture-${i}`, status, event_type: 'smtp_test', recipients: ['fixture@example.com'], attachments: [], triggered_at: '2026-09-27T12:00:00',
  })) } }); });
  await page.goto('/scheduling?section=notifications');
  await page.getByRole('tab', { name: 'Delivery Logs' }).click();
  const rows = page.getByRole('table');
  for (const status of ['pending', 'sent', 'error', 'partial']) await expect(rows.getByText(status, { exact: true })).toBeVisible();
  await page.screenshot({ path: '../recovery/database-verification/delivery-logs.png' });
  const before = requests;
  await expect.poll(() => requests, { timeout: 8000 }).toBeGreaterThan(before);
  await page.getByRole('combobox', { name: 'Status', exact: true }).click();
  await page.getByRole('option', { name: 'Sent', exact: true }).click();
  await expect(rows.getByText('pending', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Apply', exact: true }).click();
  await expect(rows.getByText('pending', { exact: true })).toHaveCount(0);
  await expect(rows.getByText('sent', { exact: true })).toBeVisible();
});
