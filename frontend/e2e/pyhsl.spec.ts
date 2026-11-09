import { expect, test, type Page } from '@playwright/test';

/** Failure cases for PyHSL schedules and the Run page, against faked replies:
 * - A PyHSL schedule can be saved without a checked protocol, or in a mode other than Simulation.
 * - A refused protocol hides Run Control's reason, or a failed check still allows saving.
 * - The Run page offers a control, reads an unreachable Run Control as a healthy run, or loses
 *   the last reading when a read fails; a needed review or a waiting prompt is not shown.
 * - PyHSL's report runs script inside RobotControl's page.
 * Server-side cases are in backend/e2e/pyhsl_runner_check.py and pyhsl_client_check.py.
 */
const running = { run_id: 'a'.repeat(32), protocol: 'pyhsl_test_automation', status: 'running', host_status: 'open', mode: 'simulation',
  completed_count: 4, error: null, origin: 'machine', created_at: '2026-11-09T15:36:00+00:00', updated_at: '2026-11-09T15:36:30+00:00',
  protocol_revision: '048271bb', current: { operation: 'initialize', status: 'dispatched' }, prompt: { waiting: false, text: null }, requires_review: null };
const protocol = { name: 'Automation Test', revision: '048271bb',
  parameters: { round: { label: 'Round', type: 'choice', default: 'first', choices: ['first', 'second'] } } };

async function signIn(page: Page) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
    user_id: 'operator', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
}

test('a PyHSL schedule needs a checked protocol and saves in Simulation', async ({ page }) => {
  await signIn(page);
  const writes: any[] = [];
  let refuse = true;
  await page.route('**/api/pyhsl/validate', route => refuse
    ? route.fulfill({ status: 400, json: { detail: 'No protocol with this ID is imported on this PC; nothing was started' } })
    : route.fulfill({ json: { protocol } }));
  await page.route('**/api/scheduling/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      writes.push(route.request().postDataJSON());
      return route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
    }
    let data: unknown = [];
    if (path.endsWith('/status/scheduler')) data = { is_running: true };
    else if (path.endsWith('/status/queue')) data = { queue: { running_jobs: 0, queued_jobs: 0 }, manual_recovery: { active: false, storage_healthy: true, pending_recoveries: [] } };
    else if (path.endsWith('/experiments/available')) data = { experiments: [] };
    else if (path.endsWith('/experiments/library')) data = { methods: [] };
    return route.fulfill({ json: { success: true, data } });
  });
  await page.goto('/scheduling?section=schedules');
  await page.getByRole('button', { name: /new schedule|create schedule/i }).first().click();
  const editor = page.getByRole('dialog', { name: 'Create schedule', exact: true });
  await editor.getByRole('button', { name: 'PyHSL protocol', exact: true }).click();
  await expect(editor.getByRole('checkbox', { name: 'Simulation', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'Simulation', exact: true })).toBeDisabled();

  await editor.getByLabel('Protocol ID').fill('not_imported');
  await editor.getByRole('button', { name: 'Check', exact: true }).click();
  await expect(editor.getByText('No protocol with this ID is imported on this PC', { exact: false })).toBeVisible();
  await editor.getByRole('button', { name: 'Create schedule', exact: true }).click();
  await expect(editor.getByText('Check the protocol first')).toBeVisible();
  expect(writes).toEqual([]);

  refuse = false;
  await editor.getByLabel('Protocol ID').fill('pyhsl_test_automation');
  await editor.getByRole('button', { name: 'Check', exact: true }).click();
  await expect(editor.getByText('Automation Test', { exact: true })).toBeVisible();
  await editor.getByRole('combobox', { name: 'Round' }).click();
  await page.getByRole('option', { name: 'second', exact: true }).click();
  await editor.getByRole('button', { name: 'Create schedule', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ runner: 'pyhsl', protocol_id: 'pyhsl_test_automation', parameters: { round: 'second' }, mode: 'simulation', experiment_name: 'Automation Test' });
});

test('the Run page is read-only, reports a review and a prompt, and keeps the last reading when Run Control is gone', async ({ page }) => {
  await signIn(page);
  let reply: Record<string, unknown> | null = { ...running, prompt: { waiting: true, text: 'Load the plate' } };
  await page.route(`**/api/pyhsl/runs/${running.run_id}`, route => reply
    ? route.fulfill({ json: reply })
    : route.fulfill({ status: 503, json: { detail: 'Run Control is unreachable' } }));
  await page.route(`**/api/pyhsl/runs/${running.run_id}/journal?*`, route => route.fulfill({ json: {
    events: new URL(route.request().url()).searchParams.get('after') === '0'
      ? [{ revision: 3, at: '2026-11-09T15:36:10+00:00', event: 'device_intent', text: 'Switch every channel off' }, { revision: 2, at: null, event: 'bridge_building', text: null }]
      : [], next: 3 } }));
  await page.route(`**/api/pyhsl/runs/${running.run_id}/report`, route => route.fulfill({ contentType: 'text/html', body: '<h1>Fixture report</h1><script>parent.document.title = "escaped"</script>' }));
  await page.goto(`/pyhsl?run=${running.run_id}`);
  const panel = page.getByRole('region', { name: 'Run', exact: true });
  await expect(panel).toContainText('pyhsl_test_automation');
  await expect(panel).toContainText('Simulation');
  await expect(panel).toContainText('Load the plate');
  await expect(page.getByRole('region', { name: 'Steps' })).toContainText('Switch every channel off');
  for (const name of ['Stop', 'Pause', 'Resume', 'Abort']) await expect(page.getByRole('button', { name })).toHaveCount(0);

  reply = null;
  await expect(page.getByText(/Run Control not reachable since/)).toBeVisible({ timeout: 15000 });
  await expect(panel).toContainText('Unknown');
  await expect(panel).toContainText('pyhsl_test_automation');

  reply = { ...running, status: 'completed', host_status: 'closed', requires_review: true };
  await expect(panel.getByText('Record the Run review in Run Control', { exact: false })).toBeVisible({ timeout: 15000 });
  await panel.getByRole('button', { name: 'Show report', exact: true }).click();
  const frame = page.frameLocator('iframe[title="PyHSL report"]');
  await expect(frame.getByRole('heading', { name: 'Fixture report' })).toBeVisible();
  await expect(page.locator('iframe[title="PyHSL report"]')).toHaveAttribute('sandbox', '');
  await expect(page).not.toHaveTitle('escaped');
});
