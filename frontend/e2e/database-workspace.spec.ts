import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

/** Failure cases for database settings screens:
 * - One viewer database is shown; switching it clears the previous table and leaves Restore
 *   separate. The retired "Schedule preparation" setup does not return (schedules use a
 *   database step instead).
 * - Changing a parent choice clears its dependent choices; labels stay readable on phones.
 * - A failed account creation explains the reason (for example a name conflict), keeps
 *   non-secret settings and clears administrator credentials.
 * - Several operation choices each show their own inputs without submitting changes.
 * - Certificate trust is remembered only for the exact server after a successful save.
 * - Assign connections (one dialog, from Database settings and Manage packages): the Reading
 *   connection offers an operation account or the Writing connection a read-only one; a save
 *   sends anything but the declared aliases and the writing connection; a failed save closes
 *   the dialog or loses the selection.
 * - A remote administrator (e.g. through the tunnel) sees local-only sections or requests
 *   them, or is not told those sections exist on the RobotControl computer.
 * Server-side cases are in backend/e2e/database_workspace_check.py.
 */
const evidence = process.env.ROBOTCONTROL_E2E_EVIDENCE || '../test-output/database-workspace-verification';
async function login(page: any) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (route: any) => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
}

test('simplified settings show one viewer and no scheduling adapter setup', async ({page}) => {
  mkdirSync(evidence,{recursive:true}); await login(page);
  await page.route('**/api/database/tools/viewer-sources', r => r.fulfill({json:[{id:'primary',name:'Lab results',database:'EvoYeast',revision:'1'}]}));
  await page.route('**/api/database/tables?*', r => r.fulfill({json:{success:true,data:{table_details:[{name:'[dbo].[Experiments]'}]}}}));
  await page.goto('/database');
  await expect(page.getByText('Lab results · EvoYeast',{exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Database connection'})).toHaveCount(0);
  await page.screenshot({path:`${evidence}/viewer.png`});
  await page.goto('/database?section=settings');
  await expect(page.getByRole('heading',{name:'Package connections'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Schedule preparation'})).toHaveCount(0);
  await page.screenshot({path:`${evidence}/settings.png`,fullPage:true});
});

test('a remote administrator is told which sections need the RobotControl computer', async ({page}) => {
  mkdirSync(evidence,{recursive:true});
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  // The app reads data.session.is_local (backend/api/auth.py); without it, 127.0.0.1 counts as local.
  await page.route('**/api/auth/me', r => r.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session: { is_local: false } } } }));
  const localOnlyRequests: string[] = [];
  await page.route('**/api/database/tools/{packages,sources}**', r => { localOnlyRequests.push(r.request().url()); return r.abort(); });
  await page.goto('/database?section=packages');
  const tabs = page.getByRole('tablist', { name: 'Database sections' });
  await expect(page.getByText('On the RobotControl computer only: Operations, Manage packages, Database settings.')).toBeVisible();
  for (const name of ['Operations', 'Manage packages', 'Database settings']) await expect(tabs.getByRole('tab', { name })).toHaveCount(0);
  await expect(tabs.getByRole('tab', { name: 'Restore' })).toBeVisible();
  expect(localOnlyRequests).toEqual([]);
  await page.screenshot({path:`${evidence}/remote-admin.png`});
});

test('simplified dependent choices clear children and use friendly labels on phone', async ({page}) => {
  mkdirSync(evidence,{recursive:true}); await login(page);
  await page.route('**/api/database/tools/catalogue?kind=report',r => r.fulfill({json:[{id:'plate-export',name:'Plate export',kind:'report',inputs:[
    {name:'experiment_id',label:'Experiment',type:'choice',required:true,choices:['Yeast','Bacteria']},
    {name:'plate_id',label:'Plate',type:'lookup',required:true,choices:[],lookup:{parameters:['experiment_id'],value_type:'integer'}}]}]}));
  await page.route('**/api/database/tools/reports/plate-export/choices/plate_id',r => r.fulfill({json:{options:[{value:11,label:'Growth plate'}],has_more:false}}));
  await page.goto('/database?section=retrieval');
  await expect(page.getByText('Choose Experiment first.',{exact:true})).toBeVisible();
  await page.getByRole('combobox',{name:'Experiment'}).click(); await page.getByRole('option',{name:'Yeast',exact:true}).click();
  await page.getByRole('combobox',{name:'Plate',exact:true}).click(); await page.getByRole('option',{name:'Growth plate · 11'}).click();
  await page.getByRole('combobox',{name:'Experiment'}).click(); await page.getByRole('option',{name:'Bacteria',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Plate',exact:true})).toHaveValue('');
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path:`${evidence}/dependent-phone.png`,animations:'disabled'});
});

test('account setup explains a name conflict and retains settings without credentials', async ({ page }) => {
  mkdirSync(evidence, { recursive: true }); await login(page);
  await page.route('**/api/database/tools/sources/access/create', route => route.fulfill({ status: 400, json: {
    detail: "SQL login 'Hamilton' already exists. Choose a new name, such as RobotControl_ReadOnly. Existing logins are not changed.",
  } }));
  await page.goto('/database?section=packages');
  await page.getByRole('link', { name: 'Database settings', exact: true }).last().click();
  await page.getByRole('button', { name: 'Manage connections', exact: true }).click();
  await page.getByRole('combobox', { name: 'Account setup' }).click();
  await page.getByRole('option', { name: 'Create read-only account', exact: true }).click();
  await page.getByLabel('Name', { exact: true }).fill('ShouLab-ReadOnly');
  await page.getByLabel('Server', { exact: true }).fill('LOCALHOST\\HAMILTON');
  await page.getByRole('textbox', { name: 'Database', exact: true }).fill('EvoYeast');
  await page.getByLabel('New account name', { exact: true }).fill('Hamilton');
  await expect(page.getByText('A new SQL login, e.g. RobotControl_ReadOnly. Do not enter an existing administrator login.')).toBeVisible();
  await page.getByRole('button', { name: 'Review access', exact: true }).click();
  await page.getByLabel('SQL administrator', { exact: true }).fill('fixture-admin');
  await page.getByLabel('Administrator password', { exact: true }).fill('fixture-secret');
  await page.getByLabel("Use RobotControl's Windows account").check();
  await expect(page.getByText('Uses the Windows account running RobotControl, not the browser user. It must be allowed to create SQL logins.')).toBeVisible();
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText("SQL login 'Hamilton' already exists");
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('ShouLab-ReadOnly');
  await expect(page.getByLabel('New account name', { exact: true })).toHaveValue('Hamilton');
  expect(await page.evaluate(() => localStorage.getItem('database-certificate-trust'))).toBeNull();
  await page.screenshot({ path: `${evidence}/account-conflict-desktop.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${evidence}/account-conflict-phone.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByLabel('New account name', { exact: true }).fill('RobotControl_ReadOnly');
  await page.getByRole('button', { name: 'Review access', exact: true }).click();
  await expect(page.getByLabel("Use RobotControl's Windows account")).not.toBeChecked();
  await expect(page.getByLabel('SQL administrator', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Administrator password', { exact: true })).toHaveValue('');
});

test('switching viewer database clears the previous table and leaves restore separate', async ({ page }) => {
  await login(page);
  const profiles=[{id:'a',name:'Lab A',server:'SQL-A',database:'ResultsA'}, {id:'b',name:'Lab B',server:'SQL-B',database:'ResultsB'}];
  let current='a';
  await page.route('**/api/database/tools/viewer-sources', r => r.fulfill({json:profiles.filter(x => x.id===current)}));
  await page.route('**/api/database/tools/sources', r => r.fulfill({json:profiles}));
  await page.route('**/api/database/tools/viewer-source', r => {current=r.request().postDataJSON().source_id; return r.fulfill({json:profiles.filter(x => x.id===current)});});
  await page.route('**/api/database/tables?*', route => route.fulfill({ json: { success: true, data: { table_details: [{ name: new URL(route.request().url()).searchParams.get('source_id') === 'a' ? '[dbo].[Samples]' : '[other].[Readings]' }] } } }));
  await page.route('**/api/database/tables/*?*', route => route.fulfill({ json: { success: true, data: { columns: ['value'], rows: [{ value: 'Sample A' }], total_count: 1 } } }));
  await page.goto('/database');
  await page.getByRole('button', { name: '[dbo].[Samples]', exact: false }).click();
  await expect(page.getByText('Sample A', { exact: true })).toBeVisible();
  await page.goto('/database?section=settings');
  await page.getByRole('combobox', { name: 'Viewer database' }).click();
  await page.getByRole('option', { name: 'Lab B · ResultsB' }).click();
  await page.getByRole('button',{name:'Save viewer database',exact:true}).click();
  await expect(page.getByRole('button',{name:'Save viewer database',exact:true})).toBeDisabled();
  await page.goto('/database');
  await expect(page.getByRole('button', { name: '[other].[Readings]', exact: false })).toBeVisible();
  await expect(page.getByText('Sample A', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await page.screenshot({ path: `${evidence}/viewer-target.png`, animations: 'disabled', fullPage: true });
  await page.goto('/database?section=restore');
  await expect(page.getByRole('combobox', { name: 'Database connection' })).toHaveCount(0);
});


test('multiple operation choices show their own inputs without submitting changes', async ({ page }) => {
  await login(page);
  await page.route('**/api/database/tools/catalogue?kind=operation', route => route.fulfill({ json: [
    { id: 'fixture-a', name: 'Archive experiment', kind: 'operation', package_version: '1.0.0', target: 'Disposable lab', inputs: [{ name: 'id', label: 'Experiment ID', type: 'integer', required: true, choices: [] }] },
    { id: 'fixture-b', name: 'Update plate note', kind: 'operation', package_version: '1.0.0', target: 'Disposable lab', inputs: [{ name: 'plate', label: 'Plate ID', type: 'integer', required: true, choices: [] }, { name: 'note', label: 'Note', type: 'text', required: true, choices: [] }] },
  ] }));
  let executions = 0;
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/operations/')) executions++; });
  await page.goto('/database?section=operations');
  await page.getByRole('spinbutton', { name: 'Experiment ID', exact: false }).fill('42');
  await page.getByRole('combobox', { name: 'Operation', exact: false }).click();
  await page.screenshot({ path: `${evidence}/multiple-operations.png`, animations: 'disabled' });
  await page.getByRole('option', { name: 'Update plate note', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: 'Plate ID', exact: false })).toHaveValue('');
  await expect(page.getByRole('textbox', { name: 'Note', exact: false })).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: 'Experiment ID', exact: false })).toHaveCount(0);
  expect(executions).toBe(0);
});


test('certificate trust is remembered only for a successfully saved exact server', async ({ page }) => {
  await login(page);
  await page.route('**/api/database/tools/sources', route => route.request().method() === 'POST'
    ? route.fulfill({ json: { message: 'Fixture connection saved.' } }) : route.continue());
  await page.goto('/database?section=settings');
  await page.getByRole('button', { name: 'Manage connections', exact: true }).click();
  for (const [label, value] of [['Name','Fixture'],['Server','LAB-SQL'],['Database','Results'],['Account','reader'],['Password','fixture-only']])
    await page.getByRole('dialog').getByLabel(label, { exact: true }).fill(value);
  await page.getByLabel('Trust server certificate', { exact: true }).check();
  await page.getByRole('button', { name: 'Check and save', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Fixture connection saved.');
  await page.getByLabel('Server', { exact: true }).fill('LAB-SQL');
  await expect(page.getByLabel('Trust server certificate', { exact: true })).toBeChecked();
  await page.getByLabel('Server', { exact: true }).fill('ANOTHER-LAB');
  await expect(page.getByLabel('Trust server certificate', { exact: true })).not.toBeChecked();
});

test('assigning package connections offers matching accounts and saves only declared aliases', async ({ page }) => {
  mkdirSync(evidence, { recursive: true }); await login(page);
  const profiles = [{ id: 'reader', name: 'Lab reader', database: 'EvoYeast', access: 'read' }, { id: 'writer', name: 'Lab writer', database: 'EvoYeast', access: 'operation' }];
  const packages = [{ id: 'delete-experiment', name: 'Delete Experiment', version: '1.0.0', sha256: 'a', running: 0, libraries: [], tools: [{ id: 'delete-experiment', name: 'Delete Experiment', kind: 'operation' }] },
    { id: 'plate-report', name: 'Plate report', version: '1.0.0', sha256: 'b', running: 0, libraries: [], tools: [{ id: 'plate-report', name: 'Plate report', kind: 'report' }] }];
  // 'retired' is a stale alias from an earlier version; it must not be sent back.
  const bindings: Record<string, any> = { 'delete-experiment': { aliases: ['primary'], mappings: { retired: 'reader' }, has_operation: true, operation_source: null },
    'plate-report': { aliases: ['plates', 'results'], mappings: {}, has_operation: false, operation_source: null } };
  const saved: any[] = [];
  await page.route('**/api/database/tools/sources', r => r.fulfill({ json: profiles }));
  await page.route('**/api/database/tools/viewer-sources', r => r.fulfill({ json: [] }));
  await page.route('**/api/database/tools/drafts', r => r.fulfill({ json: [] }));
  await page.route('**/api/database/tools/packages', r => r.fulfill({ json: packages }));
  await page.route('**/api/database/tools/packages/*/sources', r => {
    const id = r.request().url().split('/packages/')[1].split('/')[0];
    if (r.request().method() === 'GET') return r.fulfill({ json: bindings[id] });
    saved.push(r.request().postDataJSON());
    return saved.length === 1 ? r.fulfill({ status: 409, json: { detail: 'Package is running. Wait until it finishes.' } }) : r.fulfill({ json: { message: 'Connections assigned.' } });
  });
  await page.goto('/database?section=settings');
  await expect(page.getByText('Reading connection · plates: Not configured · Reading connection · results: Not configured', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Assign', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Assign connections — Delete Experiment' });
  const reading = dialog.getByRole('combobox', { name: /^Reading connection(?! ·)/ }) // a select's name also carries its value;
  const writing = dialog.getByRole('combobox', { name: /^Writing connection/ });
  await reading.click();
  await expect(page.getByRole('option')).toHaveText(['Lab reader · EvoYeast']);
  await page.getByRole('option', { name: 'Lab reader · EvoYeast' }).click();
  await writing.click();
  await expect(page.getByRole('option')).toHaveText(['Not configured', 'Lab writer · EvoYeast']);
  await page.getByRole('option', { name: 'Lab writer · EvoYeast' }).click();
  for (const [width, height] of [[1440, 900], [390, 844]]) for (const scheme of ['light', 'dark'] as const) {
    await page.setViewportSize({ width, height }); await page.emulateMedia({ colorScheme: scheme });
    await page.screenshot({ path: `${evidence}/assign-connections-${width}-${scheme}.png`, animations: 'disabled' });
  }
  await page.emulateMedia({ colorScheme: 'light' }); await page.setViewportSize({ width: 1440, height: 900 });
  await dialog.getByRole('button', { name: 'Save connections', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('Package is running.');
  await expect(reading).toHaveText('Lab reader · EvoYeast');
  await expect(writing).toHaveText('Lab writer · EvoYeast');
  await dialog.getByRole('button', { name: 'Save connections', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.goto('/database?section=packages');
  await page.getByRole('button', { name: 'Connections', exact: true }).nth(1).click();
  const plates = page.getByRole('dialog', { name: 'Assign connections — Plate report' });
  await expect(plates.getByRole('combobox')).toHaveCount(2);
  await expect(plates.getByRole('combobox', { name: /^Writing connection/ })).toHaveCount(0);
  for (const alias of ['plates', 'results']) {
    await plates.getByRole('combobox', { name: new RegExp(`^Reading connection · ${alias}`) }).click();
    await page.getByRole('option', { name: 'Lab reader · EvoYeast' }).click();
  }
  await page.screenshot({ path: `${evidence}/assign-connections-aliases.png`, animations: 'disabled' });
  await plates.getByRole('button', { name: 'Save connections', exact: true }).click();
  await expect(plates).toHaveCount(0);
  expect(saved).toEqual([{ mappings: { primary: 'reader' }, operation_source: 'writer' }, { mappings: { primary: 'reader' }, operation_source: 'writer' },
    { mappings: { plates: 'reader', results: 'reader' }, operation_source: null }]);
});
