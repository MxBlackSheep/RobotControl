import { test, expect } from '@playwright/test';
import path from 'node:path';

/** Failure cases: Delivery Logs must show pending, sent, error and partially refused mail
 * accurately. Server-side delivery cases are in backend/e2e/notification_delivery_check.py.
 */
const evidence = process.env.ROBOTCONTROL_E2E_EVIDENCE || '../test-output/database-verification';

async function login(page: any) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (route: any) => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
  await page.route('**/api/database/tables?*', (route: any) => route.fulfill({ json: { success: true, data: { table_details: [] } } }));
}

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
  await page.screenshot({ path: path.join(evidence, 'delivery-logs.png') });
  const before = requests;
  await expect.poll(() => requests, { timeout: 8000 }).toBeGreaterThan(before);
  await page.getByRole('combobox', { name: 'Status', exact: true }).click();
  await page.getByRole('option', { name: 'Sent', exact: true }).click();
  await expect(rows.getByText('pending', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Apply', exact: true }).click();
  await expect(rows.getByText('pending', { exact: true })).toHaveCount(0);
  await expect(rows.getByText('sent', { exact: true })).toBeVisible();
});
