import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
const evidence = process.env.ROBOTCONTROL_E2E_EVIDENCE || '../test-output/database-workspace-verification';
async function login(page: any) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/auth/me', (route: any) => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'Fixture', role: 'admin', session_is_local: true } } }));
}

test('simplified settings show one viewer and an explicit existing lab connection', async ({page}) => {
  mkdirSync(evidence,{recursive:true}); await login(page);
  await page.route('**/api/database/tools/viewer-sources', r => r.fulfill({json:[{id:'primary',name:'Lab results',database:'EvoYeast',revision:'1'}]}));
  await page.route('**/api/database/tables?*', r => r.fulfill({json:{success:true,data:{table_details:[{name:'[dbo].[Experiments]'}]}}}));
  await page.goto('/database');
  await expect(page.getByText('Lab results · EvoYeast',{exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Database connection'})).toHaveCount(0);
  await page.screenshot({path:`${evidence}/viewer.png`});
  await page.route('**/api/database/tools/scheduling-settings', r => r.fulfill({json:{active:{adapter:'evoyeast'},saved:{adapter:'evoyeast'},target:{server:'LAB-SQL',database:'EvoYeast'},pending:false,schedules:[]}}));
  await page.goto('/database?section=settings');
  await expect(page.getByRole('heading',{name:'Schedule preparation'})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Laboratory database'})).toHaveCount(0);
  await page.screenshot({path:`${evidence}/settings-collapsed.png`,fullPage:true});
  await page.getByRole('button',{name:'Change setup',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Laboratory database'})).toContainText('Existing laboratory connection');
  await page.getByRole('heading',{name:'Schedule preparation'}).scrollIntoViewIfNeeded();
  await page.screenshot({path:`${evidence}/settings-expanded.png`,animations:'disabled'});
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
