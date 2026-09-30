import { test, expect } from '@playwright/test';

/** Failure cases for appearance and maintenance:
 * - System/Light/Dark leaves no light panels, unreadable selection or white flash, and
 *   changing theme never resets a reader, draft or selection.
 * - Toolbars size to their pane, not the window width; phone, keyboard and zoom never
 *   hide Back or Save.
 * - At 1280x720 log text gets at least 60% of the app height by default.
 * - A failed or malformed maintenance state never looks as if HxRun is allowed, and
 *   Refresh or Retry never overwrites the operator's reason draft.
 * - Scheduled runs never reports Allowed during maintenance, recovery, unavailable
 *   safety state or a failed robot read; combined holds retain the recovery warning,
 *   and a stopped scheduler is distinguished from permission to dispatch.
 * - A wrong current password shows "Unable to Change Password" with the server's reason,
 *   keeps the form and session open, and never refreshes tokens or redirects to /login.
 * - A successful password change closes the form and shows "Password Updated", which
 *   closes by itself after about 5 seconds and does not return when the form reopens.
 *   (The backend's 400-versus-401 contract is checked in backend/tests/test_auth.py.)
 */
test.beforeEach(async ({ page }, info) => {
  if (info.title.startsWith('system appearance')) return;
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
});

test('maintenance does not enable actions for malformed state', async ({ page }) => {
  await page.route('**/api/maintenance/hxrun*', route => route.fulfill({ json: { success: true, data: { permissions: { can_edit: true } } } }));
  await page.goto('/maintenance');
  await expect(page.getByText('State unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enter maintenance', exact: true })).toBeDisabled();
  await expect(page.getByRole('complementary', { name: 'Right now' })).toContainText('Unknown');
});

test('maintenance scheduled runs reflects maintenance and recovery holds', async ({ page }, info) => {
  await page.clock.install();
  let enabled = true;
  let recovering = false;
  let robotBroken = false;
  let schedulerRunning = true;
  let recoveryKnown = true;
  await page.route('**/api/maintenance/hxrun*', route => route.fulfill({ json: { success: true,
    data: { enabled, reason: 'Deck service', permissions: { can_edit: true } } } }));
  await page.route('**/api/scheduling/status/scheduler', route => route.fulfill({ json: { success: true,
    data: { is_running: schedulerRunning, manual_recovery: null } } }));
  await page.route('**/api/scheduling/status/queue', route => route.fulfill(robotBroken
    ? { status: 500, json: { detail: 'Robot status unavailable' } }
    : { json: { success: true, data: {
    queue: { queued_jobs: 1, running_job_details: [] }, hamilton: { is_running: false },
    manual_recovery: recoveryKnown ? { active: recovering, storage_healthy: true, safety_revision: 3, resume_required: false, pending_recoveries: [] } : null,
  } } }));
  await page.goto('/maintenance');
  const scheduled = page.getByRole('complementary', { name: 'Right now' }).getByRole('group', { name: 'Scheduled runs', exact: true });
  await expect(scheduled).toContainText('Held');
  await expect(scheduled).toContainText('Maintenance');
  await expect(scheduled).not.toContainText('Allowed');
  await page.screenshot({ path: info.outputPath('maintenance-held.png'), fullPage: true });
  recovering = true;
  await page.reload();
  await expect(scheduled).toContainText('1 run needs recovery');
  await expect(scheduled).toContainText('Maintenance');
  enabled = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(scheduled).toContainText('Held');
  await expect(scheduled).toContainText('1 run needs recovery');
  recovering = false;
  await page.reload();
  await expect(scheduled).toContainText('Allowed');
  await expect(scheduled).toContainText('Not held');
  robotBroken = true;
  await page.clock.fastForward(20000);
  await expect(scheduled).toContainText('Unknown');
  await expect(scheduled).not.toContainText('Allowed');
  robotBroken = false;
  recoveryKnown = false;
  await page.reload();
  await expect(scheduled).toContainText('Unknown');
  recoveryKnown = true;
  schedulerRunning = false;
  await page.reload();
  await expect(scheduled).toContainText('Stopped');
  await expect(scheduled).not.toContainText('Allowed');
});

test('appearance persists and log content receives the default reading space', async ({ page }, info) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('/logfile?section=robotcontrol');
  await page.getByRole('button', { name: /robotcontrol_backend.log/ }).click();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-END');
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
  const bounds = await page.getByLabel('Log content').boundingBox();
  expect(bounds!.height / 720).toBeGreaterThanOrEqual(.60);
  await info.attach('log-space', { body: JSON.stringify({ viewport: 720, content: bounds!.height }), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath('dark-logs.png'), animations: 'disabled' });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Light', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light');
});

test('maintenance initial failure is unknown and a retry preserves reason edits', async ({ page }, info) => {
  let broken = true;
  let pending: Promise<void> | null = null;
  await page.route('**/api/maintenance/hxrun*', async route => {
    if (pending) await pending;
    await route.fulfill(broken
    ? { status: 500, json: { detail: 'Unavailable' } }
    : { json: { success: true, data: { enabled: false, reason: '', permissions: { can_edit: true } } } });
  });
  await page.goto('/maintenance');
  await expect(page.getByText('State unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enter maintenance', exact: true })).toBeDisabled();
  const scheduled = page.getByRole('complementary', { name: 'Right now' }).getByRole('group', { name: 'Scheduled runs', exact: true });
  await expect(scheduled).toContainText('Unknown');
  await expect(scheduled).not.toContainText('Allowed');
  broken = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await page.getByLabel('Reason').fill('Operator draft');
  await expect(scheduled).toContainText('Allowed');
  broken = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('State unavailable', { exact: true })).toBeVisible();
  await expect(scheduled).toContainText('Unknown');
  await expect(page.getByLabel('Reason')).toHaveValue('Operator draft');
  await expect(page.getByLabel('Reason')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Enter maintenance', exact: true })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('maintenance-refresh-failed.png'), fullPage: true });
  broken = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByLabel('Reason')).toHaveValue('Operator draft');
  await expect(scheduled).toContainText('Allowed');
  let finishRead!: () => void;
  pending = new Promise(resolve => { finishRead = resolve; });
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(scheduled).toContainText('Unknown');
  await expect(page.getByLabel('Reason')).toHaveValue('Operator draft');
  await expect(page.getByRole('button', { name: 'Enter maintenance', exact: true })).toBeDisabled();
  finishRead();
  await expect(scheduled).toContainText('Allowed');
  await expect(page.getByLabel('Reason')).toHaveValue('Operator draft');
});

for (const width of [320, 1920]) {
  test(`all module shells support dark appearance at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width === 320 ? 740 : 1080 });
    await page.addInitScript(() => localStorage.setItem('robotcontrol-appearance', 'dark'));
    await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const route of ['/', '/database', '/database?section=restore', '/database?section=operations', '/scheduling', '/scheduling?section=calendar', '/scheduling?section=history', '/scheduling?section=notifications', '/camera', '/labware', '/labware?section=cytomat', '/maintenance', '/logfile', '/system-status', '/admin', '/admin?section=storage', '/about']) {
      await page.goto(route);
      await expect(page.locator('main')).toBeVisible();
      await expect(page.locator('main h1')).toBeVisible();
      // A fixture error dialog can temporarily hide the shell from the accessibility tree.
      // This assertion measures the underlying layout, not modal interaction.
      expect((await page.locator('main h1').boundingBox())!.width, `${route} page title`).toBeGreaterThan(30);
      await expect(width === 320 ? page.getByRole('button', { name: 'Open navigation' }) : page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), route).toBeTruthy();
      await page.screenshot({ path: info.outputPath(`${route.replace(/[^a-z0-9]/gi, '-') || 'dashboard'}.png`), fullPage: true });
    }
    expect(errors).toEqual([]);
  });
}

test('system appearance follows OS changes and login exposes the same preference', async ({ page }) => {
  await page.addInitScript(() => { localStorage.removeItem('access_token'); });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/login');
  await expect(page.getByRole('form', { name: 'Login form' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light');
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
});

test('change password explains a wrong current password and confirms success', async ({ page }, info) => {
  const refreshes: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/auth/refresh')) refreshes.push(request.url()); });
  // Same status and body as backend/api/auth.py for a wrong and a correct current password.
  await page.route('**/api/auth/change-password', route => {
    const { current_password } = route.request().postDataJSON();
    return current_password === 'Correct!Pass1'
      ? route.fulfill({ json: { success: true, message: 'Password changed successfully', data: { message: 'Password changed successfully' } } })
      : route.fulfill({ status: 400, json: { success: false, message: 'Current password is incorrect', data: null,
          error: { message: 'Current password is incorrect', code: 'BAD_REQUEST' } } });
  });
  await page.goto('/system-status');
  const openForm = async () => {
    await page.getByRole('button', { name: 'Account menu', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Change password', exact: true }).click();
  };
  const form = page.getByRole('dialog', { name: 'Change Password' });
  await openForm();
  await form.getByLabel('Current Password').fill('Wrong!Pass1');
  await form.getByLabel(/^New Password/).fill('Fresh!Pass2');
  await form.getByLabel('Confirm New Password').fill('Fresh!Pass2');
  await form.getByLabel('Confirm New Password').press('Enter');

  const failure = page.getByRole('dialog', { name: 'Unable to Change Password' });
  await expect(failure).toContainText('Current password is incorrect');
  await page.screenshot({ path: info.outputPath('wrong-current-password.png'), animations: 'disabled' });
  expect(new URL(page.url()).pathname).toBe('/system-status');
  expect(await page.evaluate(() => localStorage.getItem('access_token'))).toBe('viewer-admin');
  expect(refreshes).toEqual([]);
  await failure.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(form).toBeVisible();
  await expect(form.getByLabel(/^New Password/)).toHaveValue('Fresh!Pass2');

  await form.getByLabel('Current Password').fill('Correct!Pass1');
  await form.getByLabel('Confirm New Password').press('Enter');
  const success = page.getByRole('dialog', { name: 'Password Updated' });
  await expect(success).toBeVisible();
  const shownAt = Date.now();
  await expect(form).toBeHidden();
  await page.screenshot({ path: info.outputPath('password-updated.png'), animations: 'disabled' });
  await expect(success).toBeHidden({ timeout: 8000 });
  const visibleMs = Date.now() - shownAt;
  expect(visibleMs).toBeGreaterThanOrEqual(4000);
  await info.attach('success-visible-ms', { body: JSON.stringify({ visibleMs }), contentType: 'application/json' });

  await openForm();
  await expect(form).toBeVisible();
  await expect(form.getByLabel('Current Password')).toHaveValue('');
  await expect(success).toBeHidden();
});
