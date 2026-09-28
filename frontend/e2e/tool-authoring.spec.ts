import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
const evidence = process.env.ROBOTCONTROL_E2E_EVIDENCE || '../recovery/tool-authoring-verification';
const report = `from openpyxl import Workbook
TOOL={'name':'Browser plate export','kind':'report','inputs':{
 'experiment':{'label':'Experiment','type':'integer','query':'SELECT ExperimentID AS value, UserDefinedID AS label FROM Experiments'},
 'plate':{'label':'Plate','type':'integer','query':'SELECT PlateID AS value, CAST(PlateID AS nvarchar(40)) AS label FROM Cultures WHERE ? = 42','depends_on':['experiment']}}}
def run(context, inputs):
 b=Workbook(); b.active.append([inputs['experiment'],inputs['plate']]); b.save(context.output_dir/'plate.xlsx'); return 'plate.xlsx'
`;
const operation = `TOOL={'name':'Browser operation','kind':'operation','confirm':'experiment_id','inputs':{'experiment_id':{'label':'Experiment ID','type':'integer'}}}
def preview(context, inputs):
 with context.connection.cursor() as c:
  row=c.execute('SELECT UserDefinedID FROM Experiments WHERE ExperimentID=?',(inputs['experiment_id'],)).fetchone()
 return {'summary':'Delete selected fixture experiment.','details':{'Experiment':inputs['experiment_id'],'Name':row[0]}}
def run(context, inputs):
 raise RuntimeError('Authoring must never execute this function')
`;
async function open(page: any) {
  mkdirSync(evidence,{recursive:true});
  await page.addInitScript(()=>localStorage.setItem('access_token','viewer-admin'));
  await page.route('**/api/auth/me', (r:any)=>r.fulfill({json:{success:true,data:{user_id:'viewer-admin',username:'Fixture',role:'admin',session_is_local:true}}}));
  await page.goto('/database?section=packages');
  await page.getByRole('button',{name:'Add tool',exact:true}).click();
}
test('prepared report Python becomes a dependent form, Excel and enabled tool',async({page})=>{
  await open(page);
  await page.getByLabel('Tool Python files').setInputFiles({name:'report.py',mimeType:'text/x-python',buffer:Buffer.from(report)});
  await expect(page.getByText('Browser plate export',{exact:true})).toBeVisible();
  await page.getByRole('combobox',{name:'Connection for primary'}).click();
  await page.getByRole('option',{name:'Primary',exact:true}).click();
  await page.getByRole('button',{name:'Replace all files',exact:true}).click();
  await page.getByLabel('Tool Python files').setInputFiles({name:'export.py',mimeType:'text/x-python',buffer:Buffer.from(report)});
  await expect(page.getByText('export.py',{exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Connection for primary'})).toContainText('Primary');
  await expect(page.getByRole('button',{name:'Enable report',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Check setup',exact:true}).click();
  await page.getByRole('combobox',{name:'Experiment',exact:true}).click();
  await page.getByRole('option',{name:'Yeast Ω · 42',exact:true}).click();
  await page.getByRole('combobox',{name:'Plate',exact:true}).click();
  await page.getByRole('option',{name:'10 · 10',exact:true}).click();
  await page.getByRole('combobox',{name:'Experiment',exact:true}).click();
  await page.getByRole('option',{name:'Delete fixture · 43',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Plate',exact:true})).toHaveValue('');
  await expect(page.getByRole('button',{name:'Try report',exact:true})).toBeDisabled();
  await page.getByRole('combobox',{name:'Experiment',exact:true}).click();
  await page.getByRole('option',{name:'Yeast Ω · 42',exact:true}).click();
  await page.getByRole('combobox',{name:'Plate',exact:true}).click();
  await page.getByRole('option',{name:'10 · 10',exact:true}).click();
  await page.getByRole('button',{name:'Try report',exact:true}).click();
  await expect(page.getByRole('button',{name:'Download Excel',exact:true})).toBeVisible({timeout:30000});
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download Excel',exact:true}).click();
  await (await download).saveAs(`${evidence}/browser-plate.xlsx`);
  await page.screenshot({path:`${evidence}/report-desktop.png`,fullPage:true});
  await page.getByRole('checkbox',{name:'I reviewed the Python and checked the output'}).check();
  await page.getByRole('button',{name:'Enable report',exact:true}).click();
  await expect(page.getByText('Browser plate export is available in Data retrieval.')).toBeVisible();
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await expect(page.getByText('Browser plate export · 1.0.0',{exact:true})).toBeVisible();
  writeFileSync(`${evidence}/browser-report-source.py`,report);
});

test('prepared operation previews without executing and preserves a phone draft',async({page})=>{
  await page.setViewportSize({width:390,height:844});await open(page);
  await page.getByLabel('Tool Python files').setInputFiles({name:'operation.py',mimeType:'text/x-python',buffer:Buffer.from(operation)});
  await page.getByRole('combobox',{name:'Operation database'}).click();
  await page.getByRole('option',{name:'Disposable fixture · disposable',exact:true}).click();
  await page.getByRole('button',{name:'Save and close',exact:true}).click();
  const row=page.getByText('Browser operation',{exact:true}).locator('..');
  await row.getByRole('button',{name:'Resume'}).click();
  await expect(page.getByRole('combobox',{name:'Operation database'})).toContainText('Disposable fixture');
  await page.getByRole('button',{name:'Check setup',exact:true}).click();
  await page.getByRole('spinbutton',{name:'Experiment ID'}).fill('43');
  await page.getByRole('button',{name:'Try preview',exact:true}).click();
  await expect(page.getByText('Delete selected fixture experiment.',{exact:true})).toBeVisible();
  await expect(page.getByText('Preview only. Execution has not been requested.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Try preview',exact:true})).toBeEnabled();
  await page.evaluate(()=>window.scrollTo(0,0));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path:`${evidence}/operation-phone.png`,fullPage:true});
  await page.setViewportSize({width:1280,height:720});
  await page.screenshot({path:`${evidence}/operation-desktop.png`,fullPage:true});
  await page.getByRole('checkbox',{name:'I reviewed the Python and expected effects'}).check();
  await page.getByRole('button',{name:'Enable operation',exact:true}).click();
  await expect(page.getByText('Browser operation is available in Operations.')).toBeVisible();
  writeFileSync(`${evidence}/browser-operation-source.py`,operation);
});
