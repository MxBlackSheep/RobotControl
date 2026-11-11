import { expect, test, type Page, type Route } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for a schedule's stored fields and its "Before this run" step:
 * - A record under review (review_reason) reads as Active or Inactive, hides its reason,
 *   offers Archive, or is listed in the calendar or as a coming run.
 * - Editing it opens with its stored type chosen (a type the form no longer offers would be
 *   saved silently): Save must be refused until a type is picked; the other fields open from
 *   the stored values and the save sends the opened version. A successful save clears the
 *   chip; a refused save keeps the draft and the chip.
 * - The database step: a timing edit never sends it (the server keeps it); a non-admin sees it
 *   read-only; an administrator's change sends tool and inputs; a rejected save keeps them.
 * - The Simulation switch: it opens with the saved mode, an edit sends the mode shown, and a
 *   rejected save keeps it. A queued schedule shows why it is waiting.
 * Server-side review cases are in backend/e2e/stored_data_check.py; preparation cases in
 * backend/e2e/scheduling_lab_check.py and backend/e2e/preparation_step_check.py; mode cases in
 * backend/e2e/simulation_mode_check.py.
 */
const evidence = '../test-output/scheduling-lab-verification';
const stored = (extra: Record<string, unknown>) => ({ schedule_type: 'once', estimated_duration: 20, log_inactivity_threshold_minutes: 3,
  is_active: true, created_by: 'operator', created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00', prerequisites: [],
  notification_contacts: [], preparation: null, review_reason: null, ...extra });

/** A local session and the Scheduling routes; a write goes to `write` (default: 409, the draft stays open). */
async function scheduling(page: Page, options: { role?: 'admin' | 'user'; list: () => object[]; queued?: object[];
  write?: (route: Route) => Promise<void> }) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
    user_id: 'operator', username: 'operator', role: options.role ?? 'admin', session_is_local: true, session: { is_local: true } } } }));
  await page.route('**/api/scheduling/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      return options.write ? options.write(route) : route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
    }
    let data: unknown = [];
    if (path.endsWith('/list')) data = new URL(route.request().url()).searchParams.get('archived_only') === 'true' ? [] : options.list();
    else if (path.endsWith('/status/queue')) data = { is_running: true, queue: { running_jobs: 0, queued_jobs: options.queued?.length ?? 0, queued_job_details: options.queued ?? [] },
      manual_recovery: { active: false, storage_healthy: true, pending_recoveries: [] } };
    else if (path.endsWith('/experiments/available')) data = { experiments: options.list().map((item: any) => ({ name: item.experiment_name, path: item.experiment_path })) };
    else if (path.endsWith('/experiments/library')) data = { methods: [] };
    return route.fulfill({ json: { success: true, data } });
  });
}

const reason = "schedule type 'cron' is no longer supported";
// A stored next run must still not read as a coming run.
const review = stored({ schedule_id: 'old-cron', experiment_name: 'Old cron method', experiment_path: 'C:\\Methods\\old-cron.med',
  schedule_type: 'cron', estimated_duration: 25, next_run: '2026-12-01T10:00:00', review_reason: reason });
const coming = stored({ schedule_id: 'wash', experiment_name: 'Daily wash', experiment_path: 'C:\\Methods\\wash.med',
  schedule_type: 'daily', next_run: '2026-12-01T09:00:00' });

test('a record under review shows its reason, cannot run, and saving it with a type clears the chip', async ({ page }) => {
  mkdirSync(evidence, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 844 });
  let current: Record<string, unknown> = review;
  const writes: any[] = [];
  await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: [] }));
  await scheduling(page, { list: () => [current, coming], write: async route => {
    writes.push(route.request().postDataJSON());
    current = { ...review, schedule_type: writes[0].schedule_type, review_reason: null, updated_at: '2026-09-25T11:00:00' };
    await route.fulfill({ json: { success: true, data: current } });
  } });
  await page.goto('/scheduling?section=calendar');
  await expect(page.getByText('Daily wash', { exact: true })).toBeVisible();
  await expect(page.getByText('Old cron method', { exact: true })).toHaveCount(0);
  await page.goto('/scheduling?section=schedules');
  const row = page.getByRole('button', { name: 'Open Old cron method', exact: true });
  await expect(row).toContainText('Needs review');
  await expect(row).toContainText(reason);
  await expect(row).not.toContainText('10:00');
  await row.click();
  const detail = page.getByTestId('schedule-detail');
  await expect(detail.getByText(`Needs review: ${reason}`)).toBeVisible();
  await expect(detail.getByText('No run until reviewed', { exact: true })).toBeVisible();
  await expect(detail.getByRole('button', { name: /Archive schedule|Restore schedule/ })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: 'Delete schedule', exact: true })).toBeEnabled();
  await page.screenshot({ path: `${evidence}/review-row.png` });

  await detail.getByRole('button', { name: 'Edit schedule', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
  const type = editor.getByRole('combobox', { name: 'Schedule Type' });
  await expect(type).not.toContainText(/Run Once|Fixed Interval|Daily|Weekly|Cron/);
  await expect(editor.getByLabel('Estimated duration (minutes)', { exact: true })).toHaveValue('25');
  await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
  await expect(editor.getByText('Choose a schedule type')).toBeVisible();
  expect(writes).toEqual([]);
  await type.click();
  await page.getByRole('option', { name: 'Daily', exact: true }).click();
  await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ schedule_type: 'daily', experiment_path: review.experiment_path, estimated_duration: 25,
    expected_updated_at: review.updated_at });
  await expect(row).toContainText('Active');
  await expect(row).not.toContainText('Needs review');
  await expect(detail.getByText(`Needs review: ${reason}`)).toHaveCount(0);
});

test('a refused save of a record under review keeps the draft and the chip', async ({ page }) => {
  mkdirSync(evidence, { recursive: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const writes: any[] = [];
  await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: [] }));
  await scheduling(page, { list: () => [review], write: async route => {
    writes.push(route.request().postDataJSON());
    await route.fulfill({ status: 400, json: { detail: 'Daily schedules need a start time' } });
  } });
  await page.goto('/scheduling?section=schedules');
  await page.getByRole('button', { name: 'Open Old cron method', exact: true }).click();
  await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
  await editor.getByRole('combobox', { name: 'Schedule Type' }).click();
  await page.getByRole('option', { name: 'Daily', exact: true }).click();
  await editor.getByLabel('Estimated duration (minutes)', { exact: true }).fill('40');
  await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
  await expect(editor.getByText('Daily schedules need a start time')).toBeVisible();
  expect(writes).toHaveLength(1);
  await expect(editor.getByRole('combobox', { name: 'Schedule Type' })).toContainText('Daily');
  await expect(editor.getByLabel('Estimated duration (minutes)', { exact: true })).toHaveValue('40');
  await page.screenshot({ path: `${evidence}/review-refused-390.png` });
  await editor.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Discard changes', exact: true }).click();
  await expect(page.getByTestId('schedule-detail').getByText(`Needs review: ${reason}`)).toBeVisible();
});

for (const role of ['admin', 'user'] as const) {
  test(`database step before the run: ${role}`, async ({ page }) => {
    mkdirSync(evidence, { recursive: true });
    const preparation = { tool_id: 'log-run', package_id: 'log-run', tool_name: 'Log the run', package_version: '1.0.0', inputs: { note: 'nightly' } };
    const schedule = stored({ schedule_id: 'prepared', experiment_name: 'Prepared method', experiment_path: 'C:\\Methods\\prepared.med',
      is_active: false, preparation, preparation_state: 'needs_review' });
    const writes: any[] = [];
    await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: [
      { id: 'log-run', name: 'Log the run', package_version: '1.0.1', target: 'Writer · LAB / EvoYeast', setup_needed: false,
        inputs: [{ name: 'note', label: 'Note', type: 'text', required: false, choices: [] }] }] }));
    await scheduling(page, { role, list: () => [schedule], write: async route => {
      writes.push(route.request().postDataJSON());
      await route.fulfill({ status: 409, json: { detail: 'The package changed. Review the step again.' } });
    } });
    await page.goto('/scheduling?section=schedules');
    await page.getByRole('button', { name: 'Open Prepared method', exact: true }).click();
    await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
    await expect(editor.getByText('Needs review', { exact: true })).toBeVisible();
    if (role === 'user') {
      await expect(editor.getByText('Database step: Log the run · v1.0.0')).toBeVisible();
      await expect(editor.getByText('Only a local administrator can change this step.')).toBeVisible();
      await expect(editor.getByRole('combobox', { name: 'Database step' })).toHaveCount(0);
      await editor.getByLabel('Estimated duration (minutes)', { exact: true }).fill('25');
      await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
      await expect.poll(() => writes.length).toBe(1);
      expect(writes[0]).not.toHaveProperty('preparation');
      await page.screenshot({ path: `${evidence}/database-step-user.png` });
      return;
    }
    await expect(editor.getByRole('combobox', { name: 'Database step' })).toContainText('Log the run');
    await expect(editor.getByText('The package or its connection changed after this step was saved.', { exact: false })).toBeVisible();
    const note = editor.getByLabel('Note', { exact: true });
    await expect(note).toHaveValue('nightly');
    await note.fill('weekly');
    await editor.getByText('Runs before the method starts, writing to Writer · LAB / EvoYeast', { exact: false }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${evidence}/database-step-admin.png` });
    await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].preparation).toEqual({ tool_id: 'log-run', inputs: { note: 'weekly' } });
    // A rejected save keeps the dialog and the edited step.
    await expect(editor).toBeVisible();
    await expect(note).toHaveValue('weekly');
  });
}

for (const [saved, sent] of [['real', 'simulation'], ['simulation', 'real']] as const) {
  test(`Simulation switch: a ${saved} schedule edited to ${sent}`, async ({ page }) => {
    const waiting = 'VENUS is in Simulation Mode; this schedule is real. Turn it off in VENUS: Settings > Simulation Mode.';
    const schedule = stored({ schedule_id: 'nightly', experiment_name: 'Nightly method', experiment_path: 'C:\\Methods\\nightly.med', mode: saved });
    const writes: any[] = [];
    await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: [] }));
    await scheduling(page, { list: () => [schedule], queued: [{ schedule_id: 'nightly', experiment_name: 'Nightly method', waiting_reason: waiting }],
      write: async route => {
        writes.push(route.request().postDataJSON());
        await route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
      } });
    await page.goto('/scheduling?section=schedules');
    await page.getByRole('button', { name: 'Open Nightly method', exact: true }).click();
    const detail = page.getByTestId('schedule-detail');
    await expect(detail.getByText(`Waiting: ${waiting}`)).toBeVisible();
    await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
    const toggle = editor.getByLabel('Run in VENUS Simulation Mode');
    await expect(toggle).toBeChecked({ checked: saved === 'simulation' });
    await toggle.click();
    await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].mode).toBe(sent);
    await expect(toggle).toBeChecked({ checked: sent === 'simulation' });
  });
}
