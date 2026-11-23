import { test, expect, type Page } from '@playwright/test';
import { signIn } from './sign-in';
import { readFileSync } from 'node:fs';
const manifest = JSON.parse(readFileSync(new URL('../../database_packages/champions-experiment/manifest.json', import.meta.url), 'utf8'));

/** Definition-driven registration: exact manifest defaults/pinned request, optional layout,
 * per-type drafts, refusal/unknown receipts, stale definition recovery and local-admin access.
 * Registration/reuse handoff uses the returned numeric ID, refuses missing/mismatched setup,
 * and never saves or launches; active empty/error/multiple states stay distinct.
 * Whole-count choices and fixed values must agree with the server contract. Faked HTTP
 * checks cannot establish SQL or instrument behaviour. */
const endpoint = '**/api/database/tools/experiments';
export const champions = {...manifest.tools[0], package_id:manifest.id, package_version:manifest.version, sha256:'a'.repeat(64)};
export const incubation = {id:'incubation-check', name:'Incubation study', kind:'experiment', package_id:'incubation-check', package_version:'1.0.0', sha256:'b'.repeat(64), parameters:[
  {name:'DurationHours', label:'Duration', type:'number', default:24, min:1, group:'main'},
  {name:'Condition', label:'Condition', type:'choice', default:'Ambient', allowed:['Ambient','Warm'], group:'main'},
]};
async function open(page:Page, types:object[] = [champions]) {
  await signIn(page);
  await page.route('**/api/auth/me', r => r.fulfill({json:{success:true,data:{user_id:'viewer-admin',username:'Fixture',role:'admin',session:{is_local:true}}}}));
  await page.route(`${endpoint}/types`, r => r.fulfill({json:types}));
  await page.route(`${endpoint}/active`, r => r.fulfill({json:[]}));
  await page.goto('/scheduling?section=experiments');
}
const field = (page:Page, label:string) => page.getByLabel(label,{exact:true});
const register = (page:Page) => page.getByRole('button',{name:'Register',exact:true});
async function choose(page:Page, name:string) {
  await field(page,'Experiment type').click(); await page.getByRole('option',{name,exact:true}).click();
}

test('registers the displayed definition, keeps per-type drafts and clears only success', async ({page}) => {
  await page.setViewportSize({width:1920,height:1080});
  await open(page,[champions,incubation]);
  await expect(field(page,'UserDefinedID')).toHaveCount(0);
  await choose(page,'Champions');
  await field(page,'UserDefinedID').fill('Champions test');
  await field(page,'Note').fill('Round one');
  await field(page,'Make active in EvoYeast').check();
  await field(page,'Target well volume').fill('650');
  await page.getByRole('button',{name:'Empty',exact:true}).click();
  const a = await page.getByRole('button',{name:'A2: Culture',exact:true}).boundingBox();
  const b = await page.getByRole('button',{name:'B3: Culture',exact:true}).boundingBox();
  await page.mouse.move(a!.x+a!.width/2,a!.y+a!.height/2); await page.mouse.down();
  await page.mouse.move(b!.x+b!.width/2,b!.y+b!.height/2); await page.mouse.up();
  await expect(page.getByRole('button',{name:'B2: Empty',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Media control',exact:true}).click();
  await page.getByRole('button',{name:'A6: Empty',exact:true}).focus(); await page.keyboard.press('Space');
  await expect(page.getByRole('button',{name:'A6: Media control',exact:true})).toBeFocused();
  await choose(page,'Incubation study');
  await expect(page.getByRole('button',{name:'A1: Media control',exact:true})).toHaveCount(0);
  await field(page,'UserDefinedID').fill('Incubation draft');
  await choose(page,'Champions');
  await expect(field(page,'UserDefinedID')).toHaveValue('Champions test');
  await expect(field(page,'Target well volume')).toHaveValue('650');
  const bodies:any[] = [];
  await page.route(endpoint, route => { const body=route.request().postDataJSON(); bodies.push(body); return route.fulfill({json:{status:'succeeded',result:{experiment_id:123,user_defined_id:body.user_defined_id}}}); });
  await register(page).click();
  await expect(page.getByText('Registered. ExperimentID: 123. UserDefinedID: Champions test.',{exact:true})).toBeVisible();
  const layout = champions.layout.default.filter(([well]) => !['A2','B2','A3','B3'].includes(well));
  layout.push(['A6','MediaCtrl']);
  expect(bodies[0]).toEqual({type_id:champions.id,package_version:champions.package_version,sha256:champions.sha256,
    token:expect.stringMatching(/^[0-9a-f]{32}$/),user_defined_id:'Champions test',note:'Round one',schedule:1,
    parameters:{...Object.fromEntries(champions.parameters.map(p => [p.name,p.default])),TargetWellVolume:650},layout});
  await expect(field(page,'UserDefinedID')).toHaveValue('');
  await expect(field(page,'Make active in EvoYeast')).not.toBeChecked();
  await choose(page,'Incubation study');
  await expect(field(page,'UserDefinedID')).toHaveValue('Incubation draft');
  await register(page).click();
  await expect(page.getByText('Registered. ExperimentID: 123. UserDefinedID: Incubation draft.',{exact:true})).toBeVisible();
  expect(bodies[1].parameters).toEqual({DurationHours:24,Condition:'Ambient'});
  expect(bodies[1]).not.toHaveProperty('layout');
});

test('keeps drafts and uncertain tokens through refusal, navigation and definition recovery', async ({page}) => {
  await open(page,[]);
  await expect(page.getByRole('link',{name:'Manage packages',exact:true})).toHaveAttribute('href','/database?section=packages');
  await page.route(`${endpoint}/types`, r => r.fulfill({status:503,json:{detail:'Catalogue unavailable'}}));
  await page.getByRole('button',{name:'Reload types',exact:true}).click();
  await expect(page.getByText('Catalogue unavailable',{exact:true})).toBeVisible();
  await expect(page.getByText('No experiment types installed.',{exact:true})).toHaveCount(0);
  await page.route(`${endpoint}/types`, r => r.fulfill({json:[champions]}));
  await page.getByRole('button',{name:'Reload types',exact:true}).click();
  await expect(field(page,'Experiment type')).toHaveCount(0);
  await register(page).click(); await expect(page.getByText('Enter a UserDefinedID.',{exact:true})).toBeVisible();
  await field(page,'UserDefinedID').fill('Retain me'); await field(page,'Note').fill('Unsaved note');
  await field(page,'Maximum iteration').fill('12');
  await page.route(endpoint,r => r.fulfill({status:400,json:{detail:"UserDefinedID 'Retain me' already has parameters and plate layout."}}));
  await register(page).click();
  await expect(page.getByText("UserDefinedID 'Retain me' already has parameters and plate layout.",{exact:true})).toBeVisible();
  const tokens:string[] = [];
  await page.route(endpoint,r => { tokens.push(r.request().postDataJSON().token); return r.fulfill({json:{status:'unknown',message:'Commit could not be confirmed. Check the database.'}}); });
  await register(page).click(); await expect(page.getByText(/Commit could not be confirmed/)).toBeVisible();
  await register(page).click(); await expect.poll(() => tokens.length).toBe(2); expect(tokens[0]).toBe(tokens[1]);
  await page.route(endpoint,r => r.abort()); await register(page).click();
  await expect(page.getByText(/Outcome unknown/)).toBeVisible();
  await page.getByRole('link',{name:'Database',exact:true}).click();
  await page.getByRole('link',{name:'Scheduling',exact:true}).click();
  await page.getByRole('tab',{name:'Experiments',exact:true}).click();
  await expect(field(page,'UserDefinedID')).toHaveValue('Retain me');
  await expect(field(page,'Note')).toHaveValue('Unsaved note');
  await expect(field(page,'Maximum iteration')).toHaveValue('12');
  await expect(page.getByText(/Outcome unknown/)).toBeVisible();
  await page.route(endpoint,r => r.fulfill({status:409,json:{detail:'Experiment type changed. Reload the page'}}));
  await register(page).click(); await expect(register(page)).toBeDisabled();
  const updated={...champions,sha256:'c'.repeat(64)};
  await page.route(`${endpoint}/types`,r => r.fulfill({json:[updated]}));
  await page.getByRole('button',{name:'Reload types',exact:true}).click();
  await page.getByRole('button',{name:'Use updated definition',exact:true}).click();
  await expect(field(page,'Maximum iteration')).toHaveValue('12'); await expect(register(page)).toBeEnabled();
  await page.route(endpoint,r => r.fulfill({status:400,json:{detail:'Assign a writing connection in Database settings.'}}));
  await register(page).click(); await expect(page.getByText('Assign a writing connection in Database settings.',{exact:true})).toBeVisible();
  for (const [role,local] of [['admin',false],['user',true]] as const) {
    await page.route('**/api/auth/me', r => r.fulfill({json:{success:true,data:{user_id:'fixture',username:'Fixture',role,session:{is_local:local}}}}));
    await page.goto('/scheduling?section=experiments');
    await expect(field(page,'UserDefinedID')).toHaveCount(0); await expect(page).not.toHaveURL(/section=experiments/);
  }
});

test('whole_count disables fractional choices and registration; fixed fields stay at defaults', async ({page}) => {
  await page.setViewportSize({width:1920,height:1080}); await open(page);
  await expect(field(page,'GFP scale')).toHaveAttribute('readonly','');
  await expect(field(page,'GFP scale')).toHaveValue(String(champions.parameters.find(p => p.name==='GFP_scale')!.default));
  await expect(page.getByText('Default',{exact:true})).toHaveCount(4);
  await field(page,'Fraction to propagate').click();
  for(const name of ['0.25','0.5','1']) await expect(page.getByRole('option',{name,exact:true})).toBeEnabled();
  await page.getByRole('option',{name:'0.25',exact:true}).click();
  await page.getByRole('button',{name:'Empty',exact:true}).click();
  for(const well of ['A2','B2','C2','D2','E2']) await page.getByRole('button',{name:`${well}: Culture`,exact:true}).click();
  await expect(page.getByText('27 cultures: 25% keeps 6.75 wells',{exact:true})).toBeVisible();
  await expect(register(page)).toBeDisabled();
  await field(page,'Fraction to propagate').click();
  for(const name of ['0.25','0.5']) await expect(page.getByRole('option',{name,exact:true})).toBeDisabled();
  await page.getByRole('option',{name:'1',exact:true}).click(); await expect(register(page)).toBeEnabled();
});

test('registration and reuse open only a prepared schedule draft; setup refusals keep the receipt', async ({page}) => {
  await open(page);
  const writes:string[] = [];
  await page.route('**/api/scheduling/**', r => {
    if (r.request().method() !== 'GET') writes.push(r.request().url());
    const path = new URL(r.request().url()).pathname;
    const data = path.endsWith('/available') ? {experiments:[]} : [];
    return r.fulfill({json:{success:true,data}});
  });
  const preparation = {tool_id:'evoyeast-experiment',inputs:{experiment_id:123}};
  await page.route('**/api/database/tools/catalogue?kind=preparation', r => r.fulfill({json:[{
    id:preparation.tool_id,name:'Select EvoYeast experiment',package_version:'1.0.1',setup_needed:false,
    inputs:[{name:'experiment_id',label:'Experiment',type:'lookup',required:true,lookup:{parameters:[],value_type:'integer'}}],
  }]}));
  await page.route('**/api/database/tools/preparations/evoyeast-experiment/choices/experiment_id', r => r.fulfill({json:{options:[{value:123,label:'Registered culture (123)'}],has_more:false}}));
  for (const reused of [false,true]) {
    await field(page,'UserDefinedID').fill(reused ? 'Empty existing parent' : 'New culture');
    await page.route(endpoint,r => r.fulfill({json:{status:'succeeded',result:{experiment_id:123,user_defined_id:r.request().postDataJSON().user_defined_id,reused_existing:reused}}}));
    await register(page).click();
    await expect(page.getByText(/Registered. ExperimentID: 123/)).toBeVisible();
    if (reused) await expect(page.getByText(/Existing note retained/)).toBeVisible();
    for (const detail of ['Select EvoYeast experiment is not installed', 'Assign Select EvoYeast experiment read and operation connections to the Experiments database in Database settings.']) {
      await page.route(`${endpoint}/123/schedule-draft`,r => r.fulfill({status:409,json:{detail}}));
      await page.getByRole('button',{name:'Open Scheduling',exact:true}).click();
      await expect(page.getByText(`Scheduling setup needed: ${detail}`,{exact:true})).toBeVisible();
      await expect(page.getByRole('dialog',{name:'Create schedule',exact:true})).toHaveCount(0);
    }
    await page.route(`${endpoint}/123/schedule-draft`,r => r.fulfill({json:preparation}));
    await page.getByRole('button',{name:'Open Scheduling',exact:true}).click();
    const dialog = page.getByRole('dialog',{name:'Create schedule',exact:true});
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button',{name:'Choose method',exact:true})).toBeEnabled();
    await expect(dialog.getByLabel('Start Time')).toHaveValue('');
    await expect(dialog.getByLabel('Database step')).toContainText('Select EvoYeast experiment');
    await expect(dialog.getByRole('combobox',{name:/^Experiment/})).toHaveValue('Registered culture (123)');
    expect(writes).toEqual([]);
    await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.getByRole('tab',{name:'Experiments',exact:true}).click();
  }
});

test('activation distinguishes empty, failed and multiple active snapshots', async ({page}) => {
  await open(page);
  const toggle = field(page,'Make active in EvoYeast');
  await page.route(`${endpoint}/active`,r => r.fulfill({json:[]}));
  await toggle.check(); await expect(page.getByText('Active experiment: None',{exact:true})).toBeVisible();
  await toggle.uncheck();
  await page.route(`${endpoint}/active`,r => r.fulfill({status:409,json:{detail:'Connection unavailable'}}));
  await toggle.check(); await expect(page.getByText('Active experiment unavailable: Connection unavailable')).toBeVisible();
  await expect(page.getByText('Active experiment: None',{exact:true})).toHaveCount(0);
  await toggle.uncheck();
  await page.route(`${endpoint}/active`,r => r.fulfill({json:[{experiment_id:12,user_defined_id:'one'},{experiment_id:13,user_defined_id:'two'}]}));
  await toggle.check(); await expect(page.getByText('Multiple active experiments.',{exact:true})).toBeVisible();
  await expect(page.getByText(/one \(ExperimentID: 12\).*two \(ExperimentID: 13\)/)).toBeVisible();
});
