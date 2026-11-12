import { expect, test, type Page } from '@playwright/test';
import { signIn as signInCookie } from './sign-in';

/** Failure cases for PyHSL schedules and the Run page, against faked replies:
 * Schedule form
 * - The protocol list cannot be searched by name or ID, or offers a mode the protocol does not allow.
 * - A PyHSL schedule saves without a protocol PyHSL accepted, or in another mode than the one chosen.
 * - A refused protocol or an unreadable list hides Run Control's reason; Retry does not recover the list.
 * Run page (PyHSL's Monitoring API view; every visible behaviour, owner's rule for this page)
 * - The view runs with RobotControl's origin (it could reach the sign-in tokens), or gets the bodies changed.
 * - The view does not follow light or dark, or does not redraw with a new reading.
 * - The 1.87 MB deck is read on every refresh or while the run read fails, or not read again for another run
 *   (also when the active run changes without a reload) or after a failed read.
 * - An unreachable Run Control loses the last reading or reads as healthy; its warning makes the page scroll.
 * - Without a run, the page does not say whether no run is active, Run Control is closed or its state is unknown.
 * - Before the first reading the view space is empty instead of "Loading".
 * - A failed script or deck read leaves an empty space instead of "Run view not shown: <reason>", or the view
 *   does not return without a reload once Run Control answers again.
 * - An ended run has no Show report, a failed report hides its reason, or PyHSL's report runs script inside
 *   RobotControl's page.
 * PyHSL's own drawing is checked in PyHSL; here a stub with the same global shows what it receives.
 * Server-side cases are in backend/e2e/pyhsl_runner_check.py and pyhsl_client_check.py.
 */
const runId = 'a'.repeat(32);
const otherRun = 'b'.repeat(32);
const listed = (id: string, name: string, modes: string[]) => ({ id, name, revision: '048271bb', modes, description: '' });
const protocols = [listed('water_transfer', 'Water Transfer', ['simulation', 'real']),
  listed('pyhsl_test_automation', 'Automation Test', ['simulation', 'test', 'real']), listed('stack_shuttle', 'Stack Shuttle', ['simulation'])];
const checked = { name: 'Automation Test', revision: '048271bb',
  parameters: { round: { label: 'Round', type: 'choice', default: 'first', choices: ['first', 'second'] } } };
// Same global and call as PyHSL's /monitor.js; it writes what it was given so the page's part can be checked.
const stub = `window.PyHSLMonitor = { mount(element, input) {
  element.dataset.mounts = String(Number(element.dataset.mounts || 0) + 1);
  element.innerHTML = '<p>Stub view · ' + input.state.status + ' · ' + input.theme + ' · deck ' + input.deck.layout + ' · mount ' + element.dataset.mounts + '</p>'
    + '<p id="origin">origin ' + String(window.origin) + '</p><p id="received">' + JSON.stringify(input) + '</p>';
} };`;

async function signIn(page: Page) {
  await signInCookie(page);
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: {
    user_id: 'operator', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
}

async function openPyHslForm(page: Page, writes: unknown[]) {
  await page.route('**/api/scheduling/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      writes.push(route.request().postDataJSON());
      return route.fulfill({ status: 409, json: { detail: 'Fixture keeps this draft open.' } });
    }
    let data: unknown = [];
    if (path.endsWith('/status/queue')) data = { is_running: true, queue: { running_jobs: 0, queued_jobs: 0 }, manual_recovery: { active: false, storage_healthy: true, pending_recoveries: [] } };
    else if (path.endsWith('/experiments/available')) data = { experiments: [] };
    else if (path.endsWith('/experiments/library')) data = { methods: [] };
    return route.fulfill({ json: { success: true, data } });
  });
  await page.goto('/scheduling?section=schedules');
  await page.getByRole('button', { name: /new schedule|create schedule/i }).first().click();
  const editor = page.getByRole('dialog', { name: 'Create schedule', exact: true });
  await expect(editor.getByRole('checkbox', { name: 'Run in VENUS Simulation Mode' })).toBeVisible();
  await editor.getByRole('button', { name: 'PyHSL protocol', exact: true }).click();
  await expect(editor.getByRole('checkbox', { name: 'Run in VENUS Simulation Mode' })).toHaveCount(0);
  return editor;
}

test('a PyHSL schedule is chosen by search and saves in a mode its protocol allows', async ({ page }) => {
  await signIn(page);
  const writes: any[] = [];
  const checks: any[] = [];
  await page.route('**/api/pyhsl/protocols', route => route.fulfill({ json: protocols }));
  await page.route('**/api/pyhsl/validate', route => {
    checks.push(route.request().postDataJSON());
    return route.fulfill({ json: { protocol: checked } });
  });
  const editor = await openPyHslForm(page, writes);
  const field = editor.getByRole('combobox', { name: 'Protocol' });

  await field.click();
  await expect(page.getByRole('option')).toHaveText([/Automation Test/, /Stack Shuttle/, /Water Transfer/]);
  await field.fill('stack_sh');
  await expect(page.getByRole('option')).toHaveText([/Stack Shuttle/]);
  await field.fill('automation');
  await page.getByRole('option', { name: /Automation Test/ }).click();

  const modes = editor.getByRole('group', { name: 'Mode' });
  await expect(modes.getByRole('button')).toHaveText(['Simulation', 'Test', 'Real']);
  await expect(modes.getByRole('button', { name: 'Simulation' })).toHaveAttribute('aria-pressed', 'true');
  await modes.getByRole('button', { name: 'Test' }).click();
  await expect.poll(() => checks.at(-1)?.mode).toBe('test');
  await editor.getByRole('combobox', { name: 'Round' }).click();
  await page.getByRole('option', { name: 'second', exact: true }).click();
  await editor.getByRole('button', { name: 'Create schedule', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ runner: 'pyhsl', protocol_id: 'pyhsl_test_automation', parameters: { round: 'second' }, mode: 'test', experiment_name: 'Automation Test' });
});

test('an unreadable list or a refused protocol shows the reason and nothing is saved', async ({ page }) => {
  await signIn(page);
  const writes: unknown[] = [];
  let listUp = false;
  await page.route('**/api/pyhsl/protocols', route => listUp
    ? route.fulfill({ json: protocols })
    : route.fulfill({ status: 503, json: { detail: 'PyHSL is not running' } }));
  await page.route('**/api/pyhsl/validate', route => route.fulfill({ status: 400, json: { detail: 'Water Transfer needs its lab folder; nothing was started' } }));
  const editor = await openPyHslForm(page, writes);

  await expect(editor.getByText('PyHSL is not running')).toBeVisible();
  listUp = true;
  await editor.getByRole('button', { name: 'Retry' }).click();
  await editor.getByRole('combobox', { name: 'Protocol' }).fill('water');
  await page.getByRole('option', { name: /Water Transfer/ }).click();
  await expect(editor.getByRole('group', { name: 'Mode' }).getByRole('button')).toHaveText(['Simulation', 'Real']);
  await expect(editor.getByText('Water Transfer needs its lab folder', { exact: false })).toBeVisible();
  await editor.getByRole('button', { name: 'Create schedule', exact: true }).click();
  await expect(editor.getByText('Choose a protocol')).toBeVisible();
  expect(writes).toEqual([]);
});

/** Run Control as the page sees it through RobotControl's relays; each reply can be changed mid-test. */
async function runControl(page: Page) {
  const fake = {
    script: stub as string | null,
    deckUp: true,
    states: { [runId]: { run_id: runId, status: 'waiting_for_next', revision: 1 }, [otherRun]: { run_id: otherRun, status: 'running', revision: 9 } } as Record<string, object | null>,
    deckReads: 0,
    scriptReads: 0,
    report: '<h1>Fixture report</h1><script>parent.document.title = "escaped"</script>' as string | null,
    // Run Control as RobotControl's monitor last read it; the page follows its active run without ?run=.
    status: { state: 'running', reason: null, run: { run_id: runId, status: 'waiting_for_next' } as object | null,
      reviews: { known: true, blocked: false, run_ids: [] } } as Record<string, unknown>,
  };
  await page.route('**/api/pyhsl/status', route => route.fulfill({ json: { ...fake.status, checked_at: new Date().toISOString() } }));
  await page.route('**/api/pyhsl/monitor.js', route => {
    fake.scriptReads += 1;
    return fake.script ? route.fulfill({ contentType: 'text/plain', body: fake.script })
      : route.fulfill({ status: 502, json: { detail: 'Run Control returned HTTP 404' } });
  });
  await page.route('**/api/pyhsl/deck', route => {
    fake.deckReads += 1;
    return fake.deckUp ? route.fulfill({ json: { layout: 'lab-deck', model: { labware: {} }, geometry: { labware: {} } } })
      : route.fulfill({ status: 504, json: { detail: 'Run Control did not answer in time' } });
  });
  await page.route('**/api/pyhsl/runs/*', route => {
    const id = new URL(route.request().url()).pathname.split('/').pop()!;
    const state = fake.states[id];
    return state ? route.fulfill({ json: state }) : route.fulfill({ status: 503, json: { detail: 'Run Control is unreachable' } });
  });
  await page.route('**/api/pyhsl/runs/*/report', route => fake.report
    ? route.fulfill({ contentType: 'text/html', body: fake.report })
    : route.fulfill({ status: 502, json: { detail: 'Run Control report is too large' } }));
  return fake;
}

const view = (page: Page) => page.frameLocator('iframe[title="Run view"]');
/** The app scrolls only inside `main`; the Run page must fit it. */
const pageScrolls = (page: Page) => page.locator('main').evaluate(main => main.scrollHeight > main.clientHeight);

test('the Run page shows PyHSL\'s view in a sealed frame with the bodies unchanged, and follows the theme', async ({ page }) => {
  await signIn(page);
  await runControl(page);
  await page.goto(`/pyhsl?run=${runId}`);
  await expect(page.getByRole('heading', { name: 'PyHSL run' })).toBeVisible();
  await expect(view(page).getByText(/Stub view · waiting_for_next · light · deck lab-deck/)).toBeVisible();
  await expect(page.locator('iframe[title="Run view"]')).toHaveAttribute('sandbox', 'allow-scripts');
  await expect(view(page).locator('#origin')).toHaveText('origin null');
  expect(JSON.parse(await view(page).locator('#received').innerText())).toEqual({
    deck: { layout: 'lab-deck', model: { labware: {} }, geometry: { labware: {} } },
    state: { run_id: runId, status: 'waiting_for_next', revision: 1 }, theme: 'light' });
  for (const name of ['Stop', 'Pause', 'Next', 'Show report']) await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
  await expect(view(page).getByText(/· dark ·/)).toBeVisible();
});

test('the Run page reads the deck once per run, redraws each reading and keeps the last one when Run Control is gone', async ({ page }) => {
  await signIn(page);
  const fake = await runControl(page);
  await page.goto(`/pyhsl?run=${runId}`);
  await expect(view(page).getByText(/mount 1$/)).toBeVisible();

  fake.states[runId] = { run_id: runId, status: 'running', revision: 2 };
  await expect(view(page).getByText(/Stub view · running ·/)).toBeVisible({ timeout: 15000 });
  expect(fake.deckReads).toBe(1);

  fake.states[runId] = null;
  await expect(page.getByText(/Run Control not reachable since \d\d:\d\d/)).toBeVisible({ timeout: 15000 });
  await expect(view(page).getByText(/Stub view · running ·/)).toBeVisible();

  await page.goto(`/pyhsl?run=${otherRun}`);
  await expect(view(page).getByText(/Stub view · running ·/)).toBeVisible();
  expect(fake.deckReads).toBe(2);
});

test('a failed script or deck read says "Run view not shown" in the view\'s place, and the view returns without a reload', async ({ page }) => {
  await signIn(page);
  const fake = await runControl(page);
  fake.script = null;
  await page.goto(`/pyhsl?run=${runId}`);
  await expect(page.getByRole('alert')).toHaveText('Run view not shown: Run Control returned HTTP 404');
  // The script is asked for again with the next reading; Run Control failing is not RobotControl's connection failing.
  await expect.poll(() => fake.scriptReads, { timeout: 15000 }).toBeGreaterThanOrEqual(2);
  await expect(page.getByText('Connection to RobotControl lost')).toHaveCount(0);
  fake.script = stub;
  await expect(view(page).getByText(/Stub view ·/)).toBeVisible({ timeout: 15000 });

  fake.deckUp = false;
  const reads = fake.deckReads;
  await page.reload();
  await expect(page.getByRole('alert')).toHaveText('Run view not shown: Run Control did not answer in time');
  fake.deckUp = true;
  await expect(view(page).getByText(/Stub view ·/)).toBeVisible({ timeout: 15000 });
  expect(fake.deckReads - reads).toBe(2);
});

test('an ended run offers Show report, and the report runs no script', async ({ page }) => {
  await signIn(page);
  const fake = await runControl(page);
  fake.states[runId] = { run_id: runId, status: 'completed', revision: 40 };
  await page.goto(`/pyhsl?run=${runId}`);
  await expect(view(page).getByText(/Stub view · completed ·/)).toBeVisible();
  await page.getByRole('button', { name: 'Show report', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Report' });
  await expect(dialog.frameLocator('iframe[title="PyHSL report"]').getByRole('heading', { name: 'Fixture report' })).toBeVisible();
  await expect(dialog.locator('iframe[title="PyHSL report"]')).toHaveAttribute('sandbox', '');
  await expect(page).not.toHaveTitle('escaped');
});

test('without a run the page says why, and before the first reading the view says Loading', async ({ page }) => {
  await signIn(page);
  const fake = await runControl(page);
  for (const [state, text] of [['running', 'No run is active.'], ['not_running', 'PyHSL is not running.'], ['unknown', 'PyHSL state is unknown.']]) {
    fake.status = { ...fake.status, state, run: null };
    await page.goto('/pyhsl');
    await expect(page.getByText(text, { exact: true })).toBeVisible();
  }

  fake.states[runId] = null;
  await page.goto(`/pyhsl?run=${runId}`);
  await expect(page.getByText('Loading', { exact: true })).toBeVisible();
  await expect(page.getByText('Run Control not reachable.', { exact: true })).toBeVisible();
  expect(fake.deckReads).toBe(0);
  expect(await pageScrolls(page)).toBe(false);
});

test('the page follows the active run in place, reads its deck, and a warning never makes it scroll', async ({ page }) => {
  await signIn(page);
  const fake = await runControl(page);
  await page.goto('/pyhsl');
  await expect(view(page).getByText(/Stub view · waiting_for_next ·/)).toBeVisible();
  expect(await pageScrolls(page)).toBe(false);

  // The next scheduled run starts; the status is read every 15 s and the page changes run without a reload.
  fake.status = { ...fake.status, run: { run_id: otherRun, status: 'running' } };
  await expect(view(page).getByText(/Stub view · running ·/)).toBeVisible({ timeout: 25000 });
  expect(fake.deckReads).toBe(2);

  fake.states[otherRun] = null;
  await expect(page.getByText(/Run Control not reachable since \d\d:\d\d/)).toBeVisible({ timeout: 15000 });
  await expect.poll(() => pageScrolls(page)).toBe(false);
});

test('a report that cannot be read says why', async ({ page }) => {
  await signIn(page);
  const fake = await runControl(page);
  fake.states[runId] = { run_id: runId, status: 'failed', revision: 12 };
  fake.report = null;
  await page.goto(`/pyhsl?run=${runId}`);
  await page.getByRole('button', { name: 'Show report', exact: true }).click();
  await expect(page.getByText('Run Control report is too large')).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Report' })).toHaveCount(0);
});
