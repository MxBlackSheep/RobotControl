import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for the schedule's "Before this run" step:
 * - A schedule saved with the retired EvoYeast adapter tokens loses them silently: the form
 *   must show Needs review with the old steps, prefill the EvoYeast package step (experiment
 *   visible, reset tables, saved order) for an administrator and send it on save, never send
 *   tokens; a non-admin sees it read-only and a timing edit sends neither; a package that is
 *   not installed is named and the prefill kept. Tokens without a prefill (batch example)
 *   still let an administrator resolve the review: saving sends an explicit step (none).
 * - The database step: a timing edit never sends it (the server keeps it); a non-admin sees it
 *   read-only; an administrator's change sends tool and inputs; a rejected save keeps them.
 * Server-side preparation cases are in backend/e2e/scheduling_lab_check.py and
 * backend/e2e/preparation_step_check.py.
 */
const evidence = '../test-output/scheduling-lab-verification';
const oldTokens = ['ResetHamiltonTables:Runtime', 'ScheduledToRun', 'EvoYeastExperiment:42|set'];
const suggestion = { tool_id: 'evoyeast-experiment', inputs: { experiment_id: 42, reset_tables: true, table_list: 'Runtime', reset_first: true } };
const evoyeastTool = { id: 'evoyeast-experiment', name: 'Select EvoYeast experiment', package_version: '1.0.0', target: 'EvoYeast writer · LAB / EvoYeast',
  setup_needed: false, inputs: [
    { name: 'experiment_id', label: 'Experiment', type: 'lookup', required: false, choices: [], lookup: { parameters: [], value_type: 'integer' } },
    { name: 'reset_tables', label: 'Reset Hamilton tables', type: 'boolean', required: false, choices: [] },
    { name: 'table_list', label: 'Tables to reset (comma-separated; blank resets all)', type: 'text', required: false, choices: [] },
    { name: 'reset_first', label: 'Reset tables before selecting the experiment', type: 'boolean', required: false, choices: [] }] };

for (const [role, width, installed] of [['admin', 1280, true], ['admin', 390, false], ['user', 390, true]] as const) {
  test(`old EvoYeast selection needs review: ${role} at ${width}px${installed ? '' : ', package not installed'}`, async ({ page }) => {
    mkdirSync(evidence, { recursive: true });
    await page.setViewportSize({ width, height: 844 });
    const message = "This schedule's EvoYeast selection moved to a database step. A local administrator must review and save the schedule before it runs.";
    const schedule = { schedule_id: 'lab-reference', experiment_name: 'Reference method', experiment_path: 'C:\\Methods\\reference.med',
      schedule_type: 'interval', interval_hours: 6, estimated_duration: 20, log_inactivity_threshold_minutes: 3, is_active: true,
      created_by: 'operator', created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00', prerequisites: oldTokens, notification_contacts: [],
      preparation: null, legacy_preparation: { steps: oldTokens, suggestion, message }, preparation_state: 'needs_review' };
    const writes: any[] = [];
    await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
    await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
      user_id: 'operator', username: 'operator', role, session_is_local: true, session: { is_local: true } } } }));
    await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: installed ? [evoyeastTool] : [] }));
    await page.route('**/api/database/tools/preparations/evoyeast-experiment/choices/experiment_id', route => route.fulfill({ json: {
      options: [{ value: 42, label: 'Reference (42)' }, { value: 41, label: 'Previous (41)' }], has_more: false } }));
    await page.route('**/api/scheduling/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() !== 'GET') {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
      }
      let data: unknown = [];
      if (path.endsWith('/list')) data = [schedule];
      else if (path.endsWith('/status/scheduler')) data = { is_running: true };
      else if (path.endsWith('/status/queue')) data = { queue: { running_jobs: 0, queued_jobs: 0 }, manual_recovery: { active: false, storage_healthy: true, pending_recoveries: [] } };
      else if (path.endsWith('/experiments/available')) data = { experiments: [{ name: schedule.experiment_name, path: schedule.experiment_path }] };
      else if (path.endsWith('/experiments/library')) data = { methods: [] };
      return route.fulfill({ json: { success: true, data } });
    });
    await page.goto('/scheduling?section=schedules');
    await page.getByRole('button', { name: 'Open Reference method', exact: true }).click();
    await expect(page.getByText('Old EvoYeast selection · needs review', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
    await expect(editor.getByText(message)).toBeVisible();
    await expect(editor.getByText(`Saved before: ${oldTokens.join(', ')}`)).toBeVisible();
    await expect(editor.getByText('Needs review', { exact: true })).toBeVisible();
    await expect(editor.getByRole('radio')).toHaveCount(0);
    await editor.getByText(message).scrollIntoViewIfNeeded();
    if (role === 'user') {
      await expect(editor.getByText('Database step: none')).toBeVisible();
      await expect(editor.getByRole('combobox', { name: 'Database step' })).toHaveCount(0);
      await page.screenshot({ path: `${evidence}/old-selection-user-${width}.png` });
      await editor.getByLabel('Estimated duration (minutes)', { exact: true }).fill('42');
      await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
      await expect.poll(() => writes.length).toBe(1);
      expect(writes[0]).not.toHaveProperty('preparation');
      expect(writes[0]).not.toHaveProperty('prerequisites');
      return;
    }
    const step = editor.getByRole('combobox', { name: 'Database step' });
    if (!installed) {
      await expect(step).toContainText('evoyeast-experiment · not installed');
      await expect(editor.getByText('Package evoyeast-experiment is not installed.', { exact: false })).toBeVisible();
      await page.screenshot({ path: `${evidence}/old-selection-not-installed-${width}.png` });
      await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
      await expect.poll(() => writes.length).toBe(1);
      // The prefill is still what a save sends; the server refuses an uninstalled tool.
      expect(writes[0].preparation).toEqual(suggestion);
      return;
    }
    await expect(step).toContainText('Select EvoYeast experiment');
    await expect(editor.getByRole('combobox', { name: 'Experiment', exact: true })).toHaveValue('Reference (42)');
    await expect(editor.getByRole('checkbox', { name: 'Reset Hamilton tables' })).toBeChecked();
    await expect(editor.getByLabel('Tables to reset (comma-separated; blank resets all)')).toHaveValue('Runtime');
    await expect(editor.getByRole('checkbox', { name: 'Reset tables before selecting the experiment' })).toBeChecked();
    await editor.getByText('Runs before the method starts, writing to EvoYeast writer', { exact: false }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${evidence}/old-selection-admin-${width}.png` });
    await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].preparation).toEqual(suggestion);
    expect(writes[0]).not.toHaveProperty('prerequisites');
    // A rejected save keeps the dialog and the prefilled step.
    await expect(editor).toBeVisible();
    await expect(editor.getByRole('combobox', { name: 'Experiment', exact: true })).toHaveValue('Reference (42)');
  });
}

test('old tokens without a prefill: an administrator save sends an explicit step', async ({ page }) => {
  mkdirSync(evidence, { recursive: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const message = "This schedule's old preparation (Batch:B-01) cannot be carried over: unsupported step Batch:B-01. A local administrator must choose its database step and save the schedule before it runs.";
  const schedule = { schedule_id: 'batch-reference', experiment_name: 'Batch method', experiment_path: 'C:\\Methods\\batch.med',
    schedule_type: 'once', estimated_duration: 20, log_inactivity_threshold_minutes: 3, is_active: false,
    created_by: 'operator', created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00', prerequisites: ['Batch:B-01'], notification_contacts: [],
    preparation: null, legacy_preparation: { steps: ['Batch:B-01'], suggestion: null, message }, preparation_state: 'needs_review' };
  const writes: any[] = [];
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
    user_id: 'operator', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
  await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: [evoyeastTool] }));
  await page.route('**/api/scheduling/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      writes.push(route.request().postDataJSON());
      return route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
    }
    let data: unknown = [];
    if (path.endsWith('/list')) data = [schedule];
    else if (path.endsWith('/status/scheduler')) data = { is_running: true };
    else if (path.endsWith('/status/queue')) data = { queue: { running_jobs: 0, queued_jobs: 0 }, manual_recovery: { active: false, storage_healthy: true, pending_recoveries: [] } };
    else if (path.endsWith('/experiments/available')) data = { experiments: [{ name: schedule.experiment_name, path: schedule.experiment_path }] };
    else if (path.endsWith('/experiments/library')) data = { methods: [] };
    return route.fulfill({ json: { success: true, data } });
  });
  await page.goto('/scheduling?section=schedules');
  await page.getByRole('button', { name: 'Open Batch method', exact: true }).click();
  await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
  await expect(editor.getByText(message)).toBeVisible();
  await expect(editor.getByText('Saving replaces the old preparation with the step below.')).toBeVisible();
  await expect(editor.getByRole('combobox', { name: 'Database step' })).toContainText('None');
  await editor.getByText(message).scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${evidence}/old-selection-batch-390.png` });
  await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  // Explicit null: the server clears the tokens; omitting the key would keep the schedule blocked.
  expect(writes[0]).toHaveProperty('preparation', null);
  expect(writes[0]).not.toHaveProperty('prerequisites');
});

for (const role of ['admin', 'user'] as const) {
  test(`database step before the run: ${role}`, async ({ page }) => {
    mkdirSync(evidence, { recursive: true });
    const preparation = { tool_id: 'log-run', package_id: 'log-run', tool_name: 'Log the run', package_version: '1.0.0', inputs: { note: 'nightly' } };
    const schedule = { schedule_id: 'prepared', experiment_name: 'Prepared method', experiment_path: 'C:\\Methods\\prepared.med',
      schedule_type: 'once', estimated_duration: 20, log_inactivity_threshold_minutes: 3, is_active: false, created_by: 'operator',
      created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00', prerequisites: [], notification_contacts: [],
      preparation, preparation_state: 'needs_review' };
    const writes: any[] = [];
    await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
    await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
      user_id: 'operator', username: 'operator', role, session: { is_local: true } } } }));
    await page.route('**/api/database/tools/catalogue?kind=preparation', route => route.fulfill({ json: [
      { id: 'log-run', name: 'Log the run', package_version: '1.0.1', target: 'Writer · LAB / EvoYeast', setup_needed: false,
        inputs: [{ name: 'note', label: 'Note', type: 'text', required: false, choices: [] }] }] }));
    await page.route('**/api/scheduling/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() !== 'GET') {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ status: 409, json: { detail: 'The package changed. Review the step again.' } });
      }
      let data: unknown = [];
      if (path.endsWith('/list')) data = [schedule];
      else if (path.endsWith('/status/scheduler')) data = { is_running: true };
      else if (path.endsWith('/status/queue')) data = { queue: { running_jobs: 0, queued_jobs: 0 }, manual_recovery: { active: false, storage_healthy: true, pending_recoveries: [] } };
      else if (path.endsWith('/experiments/available')) data = { experiments: [{ name: schedule.experiment_name, path: schedule.experiment_path }] };
      else if (path.endsWith('/experiments/library')) data = { methods: [] };
      return route.fulfill({ json: { success: true, data } });
    });
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
