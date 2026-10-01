import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for laboratory preparation forms:
 * - Default and batch forms at desktop and phone widths keep saved steps and the saved
 *   selection when option reads fail or arrive late.
 * - The database step: a timing edit never sends it (the server keeps it); a non-admin sees it
 *   read-only; an administrator's change sends tool and inputs; a rejected save keeps them.
 * Server-side preparation cases are in backend/e2e/scheduling_lab_check.py and
 * backend/e2e/preparation_step_check.py.
 */
const evidence = '../test-output/scheduling-lab-verification';
for (const [id, width] of [['evoyeast', 1280], ['batch-sqlite', 390]] as const) {
  test(`${id} preparation at ${width}px preserves saved steps and failed reads`, async ({ page }) => {
    mkdirSync(evidence, { recursive: true });
    await page.setViewportSize({ width, height: 844 });
    const batch = id === 'batch-sqlite';
    const prerequisites = batch ? ['Batch:B-02'] : ['ResetHamiltonTables:Runtime', 'ScheduledToRun', 'EvoYeastExperiment:42|set'];
    const schedule = { schedule_id: 'lab-reference', experiment_name: 'Reference method', experiment_path: 'C:\\Methods\\reference.med',
      schedule_type: 'interval', interval_hours: 6, estimated_duration: 20, log_inactivity_threshold_minutes: 3, is_active: true,
      created_by: 'operator', created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00', prerequisites, notification_contacts: [] };
    const writes: any[] = [];
    let unavailable = false;
    await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
    await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
      user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true },
    } } }));
    await page.route('**/api/scheduling/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() !== 'GET') {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
      }
      if (path.endsWith('/lab/preparation')) {
        if (unavailable) return route.fulfill({ status: 502, json: { detail: 'Cannot load lab choices. Check the lab database connection and schema.' } });
        return route.fulfill({ json: { id, name: batch ? 'Batch example' : 'EvoYeast', selection_step: batch ? 'Batch' : 'EvoYeastExperiment',
          selection_label: batch ? 'Batch' : 'Experiment', preparation_label: batch ? 'Select batch before running' : 'Select experiment before running',
          choices: [{ value: batch ? 'B-02' : '42', label: batch ? 'Sample batch' : 'Reference experiment', selected: !batch }] } });
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
    await page.getByRole('button', { name: 'Edit schedule', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Edit schedule', exact: true });
    await expect(editor.getByRole('radio', { name: batch ? 'Select batch before running' : 'Select experiment before running' })).toBeChecked();
    const choice = editor.getByRole('combobox', { name: batch ? 'Batch' : 'Experiment', exact: true });
    await expect(choice).toContainText(batch ? 'Sample batch' : 'Reference experiment');
    await editor.getByLabel('Estimated duration (minutes)', { exact: true }).fill('42');
    await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].prerequisites).toEqual(prerequisites);
    // A timing edit never sends the database step; the server keeps the saved one.
    expect(writes[0]).not.toHaveProperty('preparation');
    // The fixture returns a conflict so the dialog/draft remains open.
    await page.keyboard.press('Escape');
    if (await page.getByRole('button', { name: 'Keep editing', exact: true }).isVisible()) await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
    await choice.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${evidence}/${id}-${width}.png` });
    unavailable = true;
    const retryRequest = page.waitForResponse(r => r.url().includes('/lab/preparation'));
    // The preparation refresh button is the last icon button before its selector.
    await editor.getByRole('button', { name: 'Refresh lab choices' }).click();
    await retryRequest;
    await expect(editor.getByText('Cannot load lab choices. Check the lab database connection and schema.')).toBeVisible();
    await expect(choice).toContainText(batch ? 'Sample batch' : 'Reference experiment');
    await expect(choice).toBeDisabled();
    unavailable = false;
    await editor.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(choice).toBeEnabled();
    await editor.getByRole('radio', { name: batch ? 'No batch selection' : 'No experiment selection' }).click();
    await editor.getByRole('button', { name: 'Save schedule', exact: true }).click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[1].prerequisites).toEqual(batch ? [] : ['ResetHamiltonTables:Runtime']);
  });
}

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
      if (path.endsWith('/lab/preparation')) return route.fulfill({ json: { id: 'evoyeast', name: 'EvoYeast', selection_step: 'EvoYeastExperiment',
        selection_label: 'Experiment', preparation_label: 'Select experiment before running', choices: [] } });
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
