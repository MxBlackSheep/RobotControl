import { test, expect } from '@playwright/test';

// Failure scenarios recorded before the compact connection-details change:
// - Process CPU or cached JPEG throughput is presented as live-view utilization/health.
// - Enabled configuration is mistaken for a connected camera or recording state.
// - A missing/non-boolean enabled field is mislabeled as disabled or enabled.
// - Incomplete database/size fields imply disconnection or print undefined capacity.
// - Database failures disappear inside a disclosure that was collapsed before data arrived.
// - Opening details creates another polling owner or loses the retained stale reading.
// - Connection identifiers or session counts overflow a 320px screen or trap keyboard focus.
// Keyboard shortcuts:
// - Alt+number stops navigating, or navigates while a dialog is open.
// - ? no longer opens the help list, or the list disagrees with the shortcuts that work.

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
  await expect(page.getByText('Live view unavailable', { exact: true })).toBeVisible();
  expect(healthRequests).toBe(1);
  failed = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('Stale data', { exact: true })).toBeVisible();
  expect(healthRequests).toBe(2);
  await page.setViewportSize({ width: 320, height: 740 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath('monitoring-phone.png') });
});

for (const width of [320, 1280]) {
  test(`connection details stay compact and report only supported facts at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 740 });
    let healthRequests = 0;
    await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
    await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: { status: {
      enabled: true, active_session_count: 2, max_sessions: 4,
      resource_usage_percent: 137, total_bandwidth_mbps: 12.3,
    } } } }));
    await page.route('**/api/monitoring/system-health', route => {
      healthRequests++;
      return route.fulfill({ json: { data: {
        sampled_at: new Date().toISOString(), system: { cpu_percent: 4, memory_percent: 12, disk_percent: 25 },
        database: { is_connected: false, mode: 'primary', database_name: 'Fixture database with a long identifier',
          server_name: 'fixture-server-with-a-very-long-hostname.internal', error_message: 'Database connection refused.' },
      } } });
    });
    await page.goto('/system-status');
    await expect(page.getByText('Live view enabled', { exact: true })).toBeVisible();
    await expect(page.getByText('Database connection refused.', { exact: true })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'CPU usage', exact: true })).toHaveAttribute('aria-valuenow', '4');
    const disclosure = page.getByRole('button', { name: 'Connection details', exact: true });
    await expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByText('Fixture database with a long identifier', { exact: true })).not.toBeVisible();
    await disclosure.focus();
    await page.keyboard.press('Enter');
    await expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByText('Fixture database with a long identifier', { exact: true })).toBeVisible();
    await expect(page.getByText('2 of 4 slots in use', { exact: true })).toBeVisible();
    await expect(page.getByText(/Utilization|Bandwidth|Recording active|Robot healthy/i)).toHaveCount(0);
    expect(healthRequests).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: info.outputPath(`connections-${width}.png`), fullPage: true, animations: 'disabled' });
    await page.keyboard.press('Enter');
    await expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    await expect(disclosure).toBeFocused();
  });
}

test('live view configuration stays unknown when the status contract is incomplete', async ({ page }) => {
  let status: Record<string, unknown> = {};
  await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/monitoring/system-health', route => route.fulfill({ json: { data: {
    sampled_at: new Date().toISOString(), system: { cpu_percent: 4, memory_percent: 12, disk_percent: 25, memory_total_gb: 16, disk_total_gb: 500 },
    database: {},
  } } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: { status } } }));
  await page.goto('/system-status');
  await expect(page.getByText('Live view unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Database unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText(/undefined|NaN/)).toHaveCount(0);
  status = { enabled: 'true' };
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('Updated', { exact: true })).toBeVisible();
  await expect(page.getByText('Live view unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText(/^Live view (enabled|disabled)$/)).toHaveCount(0);
});

test('administration gives storage health its own local section', async ({ page }) => {
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
  await page.goto('/admin?section=storage');
  await expect(page.getByRole('heading', { name: 'Storage health', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'User Accounts', exact: true })).toHaveCount(0);
});

test('keyboard shortcuts navigate, show their help and yield to dialogs', async ({ page }) => {
  await page.route('**/api/monitoring/**', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ status: 503, json: {} }));
  await page.goto('/about');
  await page.keyboard.press('Alt+6');
  await expect(page).toHaveURL(/\/system-status$/);
  await page.keyboard.press('?');
  const help = page.getByRole('dialog', { name: 'Keyboard Shortcuts' });
  await expect(help).toBeVisible();
  for (const text of ['Go to Scheduling', 'Go Back', 'Show Keyboard Shortcuts (this dialog)']) {
    await expect(help.getByText(text, { exact: true })).toBeVisible();
  }
  await page.keyboard.press('Alt+8');
  await expect(page).toHaveURL(/\/system-status$/);
  await page.keyboard.press('Escape');
  await expect(help).toBeHidden();
  await page.keyboard.press('Alt+8');
  await expect(page).toHaveURL(/\/about$/);
});