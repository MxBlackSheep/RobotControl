import { test, expect } from '@playwright/test';

// System status (connection facts are shown in cards, not a collapsed disclosure):
// - Process CPU or cached JPEG throughput is presented as live-view utilization/health.
// - Enabled configuration is mistaken for a connected camera or recording state.
// - A missing/non-boolean enabled field is mislabeled as disabled or enabled.
// - Incomplete database/size fields imply disconnection or print undefined capacity; an
//   incomplete connection reply looks like an empty, healthy list.
// - The Databases card shows only the built-in connection (once "EvoYeast, mode primary"), or a
//   failing or unknown connection reads as connected; a failure message is hidden or detached
//   from its connection.
// - Showing details creates another polling owner or loses the retained stale reading.
// - Connection identifiers or session counts overflow a 320px screen or trap keyboard focus.
// - An expired access token makes System Status reads fail with 401 forever instead of
//   renewing the sign-in once.
// Keyboard shortcuts:
// - Alt+number stops navigating, or navigates while a dialog is open.
// - ? no longer opens the help list, or the list disagrees with the shortcuts that work.
// Robot attention banner (every page; hidden while all is well and status is current):
// - An active recovery is missing from pages other than Scheduling (banner link and rail badge).
// - A failed read hides the last known recovery; the banner must say how old its data is.
// - A failed or malformed first read looks like "all clear" instead of "Robot status unavailable".
// - The queue reply is older than the scheduler reply and hides its recovery (the higher
//   safety revision must win); a reply without recovery state clears the other's.
// - An acknowledged recovery whose queued jobs still wait for Resume shows as all clear.
// Overview:
// - A run past the user's estimate shows a bar stuck at 100 % or reads the estimate as a
//   promised end; the bar must stop claiming progress and say how far past the estimate it is.
// - A running job without a known start or estimate shows NaN, "0 min" or a false bar.
// - One panel's failed read (e.g. Recent runs) blanks the page instead of offering Retry.
// - A failed robot status read shows "Nothing running" as if the robot were idle.
// - The phone navigation button disappears with the status bar.
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
  // One connection fails and one reports a state this screen does not know: neither is healthy.
  await page.route('**/api/monitoring/databases', route => route.fulfill({ json: { data: {
    built_in: { id: 'built-in', name: 'Built-in Hamilton connection', access: 'built-in', server: 'Fixture server', database: 'Fixture DB', uses: ['Hamilton run records'], state: 'failed', message: 'Login timeout expired.' },
    connections: [{ id: 'reader', name: 'Lab reader', access: 'read', server: 'Fixture server', database: 'Fixture DB', uses: [], state: 'checking' }],
    checked_at: new Date().toISOString() } } }));
  await page.goto('/system-status');
  const databases = page.getByRole('region', { name: 'Databases', exact: true });
  await expect(databases.getByTitle('1 cannot connect', { exact: true })).toBeVisible();
  await expect(databases.getByTitle('Cannot connect', { exact: true })).toBeVisible();
  await expect(databases.getByTitle('Unknown', { exact: true })).toBeVisible();
  await expect(databases.getByText('Login timeout expired.', { exact: true })).toBeVisible();
  await expect(databases.getByTitle('Connected', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Live view', exact: true }).getByTitle('Unavailable', { exact: true })).toBeVisible();
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
  const banner = page.getByRole('region', { name: 'Robot status' });

  await page.goto('/database');
  const recovery = banner.getByRole('link', { name: '1 run needs recovery' });
  await expect(recovery).toHaveAttribute('href', '/scheduling?section=recovery');
  await expect(page.getByRole('link', { name: 'Scheduling, recovery requires attention' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('status-recovery.png'), animations: 'disabled' });

  reply = 'fail';
  await page.clock.fastForward(40000);
  await expect(banner).toContainText(/Robot status updated \d+ s ago/);
  await expect(recovery).toBeVisible();
  await page.screenshot({ path: info.outputPath('status-stale.png'), animations: 'disabled' });

  for (const failure of ['fail', 'malformed'] as const) {
    reply = failure;
    await page.goto('/labware');
    await expect(banner).toContainText('Robot status unavailable');
    await expect(page.getByRole('link', { name: 'Scheduling', exact: true })).toBeVisible();
  }
  await page.screenshot({ path: info.outputPath('status-unavailable.png'), animations: 'disabled' });

  // Overview never reads a failed status as an idle robot.
  await page.goto('/');
  await expect(page.getByRole('region', { name: 'Now running' })).toContainText('Robot status is unavailable');
  await expect(page.getByText('Nothing running')).toHaveCount(0);
});

test('robot status takes the newer recovery from either reply and keeps a Resume hold visible', async ({ page }, info) => {
  await page.clock.install();
  const clear = (revision: number) => ({ active: false, storage_healthy: true, safety_revision: revision, resume_required: false, pending_recoveries: [] });
  let queue: object = clear(8);
  let scheduler: object | undefined = { active: true, storage_healthy: true, safety_revision: 9, pending_recoveries: [{ schedule_id: 'feed-2', experiment_name: 'Cell feeding stack 2' }] };
  await page.route('**/api/scheduling/status/queue', route => route.fulfill({ json: { success: true, data: { queue: { queued_jobs: 1, running_job_details: [] }, manual_recovery: queue } } }));
  await page.route('**/api/scheduling/status/scheduler', route => route.fulfill({ json: { success: true,
    data: scheduler === undefined ? { is_running: true } : { is_running: true, manual_recovery: scheduler } } }));
  const banner = page.getByRole('region', { name: 'Robot status' });
  const rail = page.getByRole('link', { name: 'Scheduling, recovery requires attention' });

  await page.goto('/database');
  await expect(banner.getByRole('link', { name: '1 run needs recovery' })).toBeVisible();
  await expect(rail).toBeVisible();

  // Acknowledged: no pending run, but queued jobs wait for Resume.
  queue = { ...clear(10), resume_required: true };
  scheduler = { ...clear(10), resume_required: true };
  await page.clock.fastForward(16000);
  await expect(banner.getByRole('link', { name: 'Queued jobs paused until Resume' })).toBeVisible();
  await expect(rail).toBeVisible();
  await page.screenshot({ path: info.outputPath('status-resume-hold.png'), animations: 'disabled' });

  // A scheduler reply without recovery state does not clear the queue's.
  scheduler = undefined;
  await page.clock.fastForward(16000);
  await expect(banner.getByRole('link', { name: 'Queued jobs paused until Resume' })).toBeVisible();

  queue = clear(11);
  await page.clock.fastForward(16000);
  await expect(rail).toHaveCount(0);
  await expect(banner).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Scheduling', exact: true })).toBeVisible();
});

test('Overview shows elapsed time against the estimate and keeps other panels when one read fails', async ({ page }, info) => {
  const now = new Date('2026-09-30T14:30:00');
  // Schedule dates are local; the monitor's launched_at includes a UTC offset.
  const local = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  await page.clock.install({ time: now });
  await page.route('**/api/scheduling/status/queue', route => route.fulfill({ json: { success: true, data: {
    queue: { queued_jobs: 1, running_job_details: [{ schedule_id: 'wash', experiment_name: 'Daily tip wash', experiment_path: 'Methods\\Wash\\DailyTipWash.hsl',
      estimated_duration: 60, monitoring: { state: 'monitoring', launched_at: new Date(now.getTime() - 42 * 60000).toISOString(), inactivity_seconds: 18, threshold_minutes: 3 } }] },
    hamilton: { is_running: true }, manual_recovery: { active: false, storage_healthy: true, safety_revision: 3, pending_recoveries: [] } } } }));
  await page.route('**/api/scheduling/list?*', route => route.fulfill({ json: { success: true, data: [
    { schedule_id: 'qc', experiment_name: 'Plate reader QC', experiment_path: 'qc.hsl', schedule_type: 'once', estimated_duration: 20, is_active: true, archived: false, next_run: local(new Date(now.getTime() + 90 * 60000)) },
    { schedule_id: 'deck', experiment_name: 'Weekly deck cleanup', experiment_path: 'deck.hsl', schedule_type: 'weekly', estimated_duration: 30, is_active: true, archived: false, next_run: local(new Date(now.getTime() + 30 * 60000)) },
  ] } }));
  await page.route('**/api/monitoring/system-health', route => route.fulfill({ json: { data: { database: { is_connected: true } } } }));
  let historyFails = true;
  await page.route('**/api/scheduling/executions/history?*', route => historyFails
    ? route.fulfill({ status: 503, json: { detail: 'History unavailable' } })
    : route.fulfill({ json: { success: true, data: [{ execution_id: 'e1', experiment_name: 'Daily tip wash', status: 'completed', start_time: '2026-09-29T13:45:00', duration_minutes: 58 }] } }));

  await page.goto('/');
  const running = page.getByRole('region', { name: 'Now running' });
  await expect(running).toContainText('Started 13:48 · 42 min of about 60 min');
  await expect(running).toContainText('Log active 18 s ago · alert after 3 min silent');
  await expect(running.getByRole('progressbar', { name: 'Elapsed time against the estimate' })).toHaveAttribute('aria-valuenow', '70');
  // Soonest first, whatever order the list arrives in.
  await expect(page.getByRole('region', { name: 'Up next' })).toContainText(/Today 15:00Weekly deck cleanupWeekly30 min.*Today 16:00Plate reader QCOnce20 min/);
  const health = page.getByRole('region', { name: 'Instrument health' });
  await expect(health).toContainText('SQL ServerConnected');
  await expect(health).toContainText('HxRunRunning');
  await expect(health).toContainText('CameraRecording');
  const recent = page.getByRole('region', { name: 'Recent runs' });
  await expect(recent).toContainText('Could not load recent runs.');
  await expect(page.getByRole('region', { name: 'Needs attention' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Robot status' })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('overview-within-estimate.png'), fullPage: true, animations: 'disabled' });

  historyFails = false;
  await recent.getByRole('button', { name: 'Retry' }).click();
  await expect(recent).toContainText('Completed');

  // Past the user's estimate: no percentage, and the text says by how much.
  await page.clock.fastForward(30 * 60000);
  await expect(running).toContainText('72 min · 12 min past the 60 min estimate');
  await expect(running.getByRole('progressbar', { name: 'Running past the estimate' })).toBeVisible();
  await expect(running.getByRole('progressbar', { name: 'Elapsed time against the estimate' })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('overview-past-estimate.png'), fullPage: true, animations: 'disabled' });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  await page.screenshot({ path: info.outputPath('overview-phone.png'), fullPage: true, animations: 'disabled' });
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
        database: { is_connected: false, mode: 'primary', database_name: 'EvoYeast', server_name: 'LOCALHOST\\HAMILTON' },
      } } });
    });
    await page.route('**/api/monitoring/databases', route => route.fulfill({ json: { data: {
      built_in: { id: 'built-in', name: 'Built-in Hamilton connection', access: 'built-in', server: 'LOCALHOST\\HAMILTON', database: 'EvoYeast',
        uses: ['Hamilton run records', 'Labware', 'Backup and restore'], state: 'connected', message: null },
      connections: [
        { id: 'writer', name: 'EvoYeast writer for the evening preparation steps', access: 'operation', server: 'fixture-server-with-a-very-long-hostname.internal',
          database: 'Fixture database with a long identifier', uses: ['Select EvoYeast experiment (changes)', 'Before-run step of 2 active schedules'], state: 'failed',
          message: "Cannot use connection 'EvoYeast writer for the evening preparation steps'. Check the connection settings, account permissions and query." },
        { id: 'reader', name: 'EvoYeast reader', access: 'read', server: 'LOCALHOST\\HAMILTON', database: 'EvoYeast',
          uses: ['Tables and Stored procedures', 'Culture history', 'Select EvoYeast experiment'], state: 'connected', message: null }],
      checked_at: new Date().toISOString() } } }));
    await page.goto('/system-status');
    await expect(page.getByRole('region', { name: 'Live view', exact: true }).getByTitle('Enabled', { exact: true })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'CPU usage', exact: true })).toHaveAttribute('aria-valuenow', '4');
    // Connection facts are shown in their cards, as in the approved mock (no disclosure).
    const databases = page.getByRole('region', { name: 'Databases', exact: true });
    await expect(databases.getByTitle('1 cannot connect', { exact: true })).toBeVisible();
    await expect(databases.getByText('Built-in · Hamilton run records · Labware · Backup and restore', { exact: true })).toBeVisible();
    await expect(databases.getByText('Database changes · Select EvoYeast experiment (changes) · Before-run step of 2 active schedules', { exact: true })).toBeVisible();
    await expect(databases.getByText('fixture-server-with-a-very-long-hostname.internal / Fixture database with a long identifier', { exact: true })).toBeVisible();
    await expect(databases.getByText("Cannot use connection 'EvoYeast writer for the evening preparation steps'.", { exact: false })).toBeVisible();
    await expect(page.getByText(/Connection mode|primary/)).toHaveCount(0);
    await expect(page.getByText('2 of 4 slots in use', { exact: true })).toBeVisible();
    await expect(page.getByText(/Utilization|Bandwidth|Recording active|Robot healthy/i)).toHaveCount(0);
    expect(healthRequests).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: info.outputPath(`connections-${width}.png`), fullPage: true, animations: 'disabled' });
  });
}

test('live view configuration stays unknown when the status contract is incomplete', async ({ page }) => {
  let status: Record<string, unknown> = {};
  await page.route('**/api/monitoring/experiments', route => route.fulfill({ json: { data: [] } }));
  await page.route('**/api/monitoring/system-health', route => route.fulfill({ json: { data: {
    sampled_at: new Date().toISOString(), system: { cpu_percent: 4, memory_percent: 12, disk_percent: 25, memory_total_gb: 16, disk_total_gb: 500 },
    database: {},
  } } }));
  await page.route('**/api/monitoring/databases', route => route.fulfill({ json: { data: {} } }));
  await page.route('**/api/camera/streaming/status', route => route.fulfill({ json: { data: { status } } }));
  await page.goto('/system-status');
  await expect(page.getByRole('region', { name: 'Live view', exact: true }).getByTitle('Unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Databases', exact: true }).getByTitle('Unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText(/undefined|NaN/)).toHaveCount(0);
  status = { enabled: 'true' };
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('Updated', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Live view', exact: true }).getByTitle('Unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Live view', exact: true }).getByTitle(/^(Enabled|Disabled)$/)).toHaveCount(0);
});

test('administration gives storage health its own local section', async ({ page }) => {
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
  await page.goto('/admin?section=storage');
  await expect(page.getByRole('tab', { name: 'Storage health', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: 'User accounts', exact: true })).toHaveCount(0);
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
  await expect(page.getByRole('region', { name: 'Live view', exact: true }).getByTitle('Unavailable', { exact: true })).toBeVisible();
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
  await expect(page.getByRole('heading', { name: 'System status', exact: true })).toBeVisible();
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
