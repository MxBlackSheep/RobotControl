import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => { await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin')); });

test('monitoring has one refresh owner and shows stale and unknown services accurately', async ({ page }, info) => {
  let healthRequests = 0, failed = false;
  await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ status: 503, json: {} }));
  await page.route('**/api/monitoring/system-health', route => {
    healthRequests++;
    return route.fulfill(failed ? { status: 503, json: {} } : { json: { data: {
      sampled_at: new Date().toISOString(), system: { cpu_percent: 4, memory_percent: 12, disk_percent: 25 },
      database: { is_connected: false, mode: 'primary', database_name: 'Fixture DB', server_name: 'Fixture server' },
    } } });
  });
  await page.goto('/system-status');
  await expect(page.getByText('Database disconnected', { exact: true })).toBeVisible();
  await expect(page.getByText('Streaming unavailable', { exact: true })).toBeVisible();
  expect(healthRequests).toBe(1);
  failed = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('Stale data', { exact: true })).toBeVisible();
  expect(healthRequests).toBe(2);
  await page.setViewportSize({ width: 320, height: 740 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath('monitoring-phone.png') });
});

test('administration gives storage health its own local section', async ({ page }) => {
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
  await page.goto('/admin?section=storage');
  await expect(page.getByRole('heading', { name: 'Storage health', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'User Accounts', exact: true })).toHaveCount(0);
});
