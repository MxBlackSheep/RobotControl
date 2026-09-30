import { test, expect } from '@playwright/test';

// Failure scenarios recorded before the compact connection-details change:
// - Process CPU or cached JPEG throughput is presented as live-view utilization/health.
// - Enabled configuration is mistaken for a connected camera or recording state.
// - A missing/non-boolean enabled field is mislabeled as disabled or enabled.
// - Incomplete database/size fields imply disconnection or print undefined capacity.
// - Database failures disappear inside a disclosure that was collapsed before data arrived.
// - Opening details creates another polling owner or loses the retained stale reading.
// - Connection identifiers or session counts overflow a 320px screen or trap keyboard focus.
// - An expired access token makes System Status reads fail with 401 forever instead of
//   renewing the sign-in once.
// Keyboard shortcuts:
// - Alt+number stops navigating, or navigates while a dialog is open.
// - ? no longer opens the help list, or the list disagrees with the shortcuts that work.
// Robot status bar (shown on every page):
// - An active recovery is missing from pages other than Scheduling (bar link and rail badge).
// - A failed read hides the last known recovery or keeps saying "Live"; the bar must say
//   how old its data is.
// - A failed or malformed first read shows "Scheduler running" instead of "Status unavailable".
// Unrelated 503s (the backend has no "database restarting" 503; restore success is checked
// in database-restore.spec.ts):
// - A camera or scheduler 503 opens "Database Maintenance In Progress", blocks later
//   requests or Alt+number, or hides the caller's own message.

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

test('robot status keeps a recovery visible on every page and never reads a failed status as all clear', async ({ page }, info) => {
  await page.clock.install();
  let reply: 'recovery' | 'fail' | 'malformed' = 'recovery';
  // Same envelope as GET /api/scheduling/status/queue.
  await page.route('**/api/scheduling/status/queue', route => reply === 'recovery'
    ? route.fulfill({ json: { success: true, data: {
        queue: { queued_jobs: 0, running_job_details: [{ schedule_id: 'wash', experiment_name: 'Daily tip wash' }] },
        manual_recovery: { active: true, storage_healthy: true, safety_revision: 4, pending_recoveries: [{ schedule_id: 'feed-2', experiment_name: 'Cell feeding stack 2' }] } } } })
    : reply === 'fail'
      ? route.fulfill({ status: 503, json: { detail: 'Scheduler safety state unavailable' } })
      : route.fulfill({ json: { success: true, data: { queue: { queued_jobs: 0 } } } }));
  const bar = page.getByRole('region', { name: 'Robot status' });

  await page.goto('/database');
  await expect(bar).toContainText('Scheduler running');
  await expect(bar).toContainText('Now Daily tip wash');
  const recovery = bar.getByRole('link', { name: '1 run needs recovery' });
  await expect(recovery).toHaveAttribute('href', '/scheduling?section=recovery');
  await expect(page.getByRole('link', { name: 'Scheduling, recovery requires attention' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('status-recovery.png'), animations: 'disabled' });

  reply = 'fail';
  await page.clock.fastForward(40000);
  await expect(bar).toContainText(/Updated \d+ s ago/);
  await expect(recovery).toBeVisible();
  await expect(bar.getByText('Live', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('status-stale.png'), animations: 'disabled' });

  for (const failure of ['fail', 'malformed'] as const) {
    reply = failure;
    await page.goto('/labware');
    await expect(bar).toContainText('Status unavailable');
    await expect(bar).not.toContainText('Scheduler running');
    await expect(page.getByRole('link', { name: 'Scheduling', exact: true })).toBeVisible();
  }
  await page.screenshot({ path: info.outputPath('status-unavailable.png'), animations: 'disabled' });
});

test('System Status renews an expired sign-in', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('refresh_token', 'saved-refresh'));
  let expired = false, refreshes = 0, rejected = 0;
  await page.route('**/api/auth/refresh', route => {
    refreshes++;
    return route.fulfill({ json: { success: true, data: { access_token: 'e2e-admin' } } });
  });
  await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: { status: { enabled: true } } } }));
  await page.route('**/api/monitoring/system-health', route => {
    if (expired && route.request().headers().authorization === 'Bearer viewer-admin') {
      rejected++;
      return route.fulfill({ status: 401, json: { detail: 'Expired' } });
    }
    return route.fulfill({ json: { data: { sampled_at: new Date().toISOString(),
      system: { cpu_percent: 4, memory_percent: 12, disk_percent: 25 },
      database: { is_connected: true, mode: 'primary', database_name: 'Fixture DB', server_name: 'Fixture server' } } } });
  });
  await page.goto('/system-status');
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled();
  expired = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(() => rejected).toBe(1);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('access_token'))).toBe('e2e-admin');
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled();
  await expect(page.getByText('Stale data', { exact: true })).toHaveCount(0);
  expect(refreshes).toBe(1);
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
  await expect(page.getByRole('tab', { name: 'Storage health', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: 'User Accounts', exact: true })).toHaveCount(0);
});

test('camera and scheduler 503s show their own errors without database maintenance', async ({ page }, info) => {
  const schedulerDetail = 'Scheduler safety state unavailable. Review SQLite storage health and retry.';
  let schedulerRequests = 0;
  await page.route('**/api/monitoring/**', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ status: 503, json: { detail: 'Streaming service unavailable' } }));
  await page.route('**/api/scheduling/**', route => { schedulerRequests++; return route.fulfill({ status: 503, json: { detail: schedulerDetail } }); });
  // Text, not role: a modal under the page's own error dialog is aria-hidden.
  const maintenance = page.getByText('Database Maintenance In Progress');

  // Scheduling uses the shared Axios client, whose interceptor once turned any 503 into maintenance.
  await page.goto('/scheduling');
  const serverError = page.getByRole('dialog', { name: 'Server Error' });
  await expect(serverError).toContainText(schedulerDetail);
  await expect(maintenance).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('scheduler-503.png'), animations: 'disabled' });
  await serverError.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(serverError).toBeHidden();
  // With the page's own error closed, no modal remains and shortcuts navigate.
  await page.keyboard.press('Alt+6');
  await expect(page).toHaveURL(/\/system-status$/);
  await expect(page.getByText('Live view unavailable', { exact: true })).toBeVisible();
  await expect(maintenance).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('camera-503.png'), animations: 'disabled' });
  // Without a reload, later requests still reach the server instead of being held for maintenance.
  const before = schedulerRequests;
  await page.keyboard.press('Alt+7');
  await expect(page).toHaveURL(/\/scheduling$/);
  await expect.poll(() => schedulerRequests).toBeGreaterThan(before);
  await expect(maintenance).toHaveCount(0);
});

test('keyboard shortcuts navigate, show their help and yield to dialogs', async ({ page }) => {
  await page.route('**/api/monitoring/**', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: { status: { enabled: false } } } }));
  await page.goto('/about');
  // Navigation keys are registered only after saved sign-in is verified.
  await expect(page.getByRole('heading', { name: 'About', exact: true })).toBeVisible();
  await page.keyboard.press('Alt+6');
  await expect(page).toHaveURL(/\/system-status$/);
  await expect(page.getByRole('heading', { name: 'System Status', exact: true })).toBeVisible();
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