import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';

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
