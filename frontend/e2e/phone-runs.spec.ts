import { test, expect, type Page } from '@playwright/test';

// Phone Runs (a remote session below 600px): a read-only agenda and history.
// - A held schedule drops out of the agenda (holding sets is_active false), so a hold looks like nothing to run.
// - An inactive or archived schedule is listed as if it will run; the running one is missing.
// - Agenda/History is lost on reload (the section must stay in the address).
// - A failed history read blanks the tab instead of offering Retry; a failed run hides its error.
// - The workstation's own browser, narrowed below 600px, loses the full Scheduling page (and an open draft).

const now = new Date('2026-09-30T14:30:00');
const local = (minutes: number) => { const date = new Date(now.getTime() + minutes * 60000); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19); };
const schedule = (id: string, name: string, next: number, extra: Record<string, unknown> = {}) => ({ schedule_id: id, experiment_name: name,
  experiment_path: `C:\\Methods\\${name.replace(/\W/g, '')}.hsl`, schedule_type: 'interval', interval_hours: 12, estimated_duration: 45,
  is_active: true, archived: false, recovery_required: false, start_time: local(next), next_run: local(next), ...extra });
const signIn = (page: Page, isLocal: boolean) => page.route('**/api/auth/me', route => route.fulfill({ json: {
  success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: isLocal, session: { is_local: isLocal } } } }));

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: now });
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/scheduling/status/queue', route => route.fulfill({ json: { success: true, data: {
    queue: { queued_jobs: 0, running_job_details: [{ schedule_id: 'wash', experiment_name: 'Daily tip wash', estimated_duration: 60,
      monitoring: { state: 'monitoring', launched_at: new Date(now.getTime() - 42 * 60000).toISOString(), inactivity_seconds: 18, threshold_minutes: 3 } }] },
    hamilton: { is_running: true }, manual_recovery: { active: false, storage_healthy: true, safety_revision: 3, pending_recoveries: [] } } } }));
  await page.route('**/api/scheduling/list?*', route => route.fulfill({ json: { success: true, data: [
    schedule('wash', 'Daily tip wash', 23 * 60 + 15),
    schedule('deck', 'Weekly deck cleanup', 60, { schedule_type: 'weekly' }),
    schedule('qc', 'Plate reader QC', 90, { is_active: false }),
    schedule('feed2', 'Cell feeding · stack 2', 330, { is_active: false, recovery_required: true, recovery_note: 'No log activity for 3 min.' }),
    schedule('feed1', 'Cell feeding · stack 1', 330),
    schedule('old', 'Old calibration', 120, { archived: true }),
    schedule('later', 'Pipette calibration', 5 * 24 * 60),
  ] } }));
});

test('the agenda lists what will run today and tomorrow, including a held run', async ({ page }) => {
  await signIn(page, false);
  await page.goto('/scheduling');
  await expect(page.locator('main h1')).toHaveText('Runs');
  const today = page.getByRole('region', { name: 'Today' });
  // The running schedule leads Today in place of its next time (tomorrow 13:45).
  await expect(today).toContainText(/^Today\s*RunningDaily tip wash/);
  await expect(today).toContainText('15:30Weekly deck cleanup');
  await expect(today).toContainText('20:00Cell feeding · stack 2Held');
  await expect(today).toContainText('20:00Cell feeding · stack 1');
  await expect(today).not.toContainText('Plate reader QC');
  await expect(today).not.toContainText('Old calibration');
  await expect(page.getByRole('region', { name: 'Tomorrow' })).toHaveCount(0);
  await expect(page.getByText('Pipette calibration')).toHaveCount(0);
  // A held row opens its note; editing is workstation work.
  await today.getByRole('button', { name: /Cell feeding · stack 2/ }).click();
  await expect(today).toContainText('No log activity for 3 min.');
  await expect(today).toContainText('Edit on the workstation.');
  await expect(page.getByRole('button', { name: /Create schedule|Edit|Archive|Delete/ })).toHaveCount(0);
});

test('history survives a failed read, keeps its view on reload and shows a failed run\'s error', async ({ page }) => {
  await signIn(page, false);
  let fails = true;
  await page.route('**/api/scheduling/executions/history?*', route => fails
    ? route.fulfill({ status: 503, json: { detail: 'History unavailable' } })
    : route.fulfill({ json: { success: true, data: [
      { execution_id: 'e1', experiment_name: 'Daily tip wash', status: 'running', start_time: local(-42) },
      { execution_id: 'e2', experiment_name: 'Plate reader QC', status: 'failed', start_time: local(-24 * 60 - 30), duration_minutes: 12, error_message: 'Reader door open' },
      { execution_id: 'e3', experiment_name: 'Cell feeding · stack 1', status: 'completed', start_time: local(-18 * 60 - 30), duration_minutes: 54 },
    ] } }));
  await page.goto('/scheduling');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page).toHaveURL(/section=history/);
  await expect(page.getByText('Could not load run history.')).toBeVisible();
  fails = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  const yesterday = page.getByRole('region', { name: 'Yesterday' });
  await expect(yesterday).toContainText('20:00Cell feeding · stack 154 min');
  await expect(yesterday).toContainText('Plate reader QCFailed');
  await yesterday.getByRole('button', { name: /Plate reader QC/ }).click();
  await expect(yesterday).toContainText('Reader door open');
  await expect(page.getByRole('region', { name: 'Today' })).toContainText('Daily tip washRunning');
  await page.reload();
  await expect(page.getByRole('button', { name: 'History', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('the workstation browser keeps the full Scheduling page when narrowed', async ({ page }) => {
  await signIn(page, true);
  await page.goto('/scheduling');
  await expect(page.getByRole('button', { name: 'Create schedule' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Runs view' })).toHaveCount(0);
});
