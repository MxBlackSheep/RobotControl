import { test, expect } from '@playwright/test';
import { signIn } from './sign-in';
import { mkdirSync } from 'node:fs';

/** Registration: the visible draft must match the SQL request (case-sensitive names,
 * column-major marked wells only). Rectangle and keyboard edits must survive refusals
 * and uncertain outcomes. A success clears the draft; remote/non-admin sessions cannot
 * open this section. These fakes do not verify SQL Server or transaction rollback.
 */
const endpoint = '**/api/database/tools/experiments';
const evidence = '../test-output/experiment-verification';
async function open(page: any) {
  await signIn(page);
  await page.route('**/api/auth/me', r => r.fulfill({json:{success:true,data:{user_id:'viewer-admin',username:'Fixture',role:'admin',session:{is_local:true}}}}));
  await page.goto('/scheduling?section=experiments');
  await expect(page.getByLabel('Experiment ID', {exact:true})).toBeVisible();
}

test('registers the displayed experiment and clears the form after success', async ({page}) => {
  mkdirSync(evidence, {recursive:true});
  await open(page);
  await page.getByLabel('Experiment ID', {exact:true}).fill('Champions test');
  await page.getByLabel('Note', {exact:true}).fill('Round one');
  await page.getByLabel('Schedule now').check();
  await page.getByLabel('TargetWellVolume', {exact:true}).fill('650');
  await page.getByLabel('Empty', {exact:true}).check();
  const a = await page.getByRole('button', {name:'A2: Culture', exact:true}).boundingBox();
  const b = await page.getByRole('button', {name:'B3: Culture', exact:true}).boundingBox();
  await page.mouse.move(a!.x+20,a!.y+20); await page.mouse.down();
  await page.mouse.move(b!.x+20,b!.y+20); await page.mouse.up();
  await expect(page.getByRole('button', {name:'B2: Empty', exact:true})).toBeVisible();
  await page.getByLabel('Media control', {exact:true}).check();
  await page.getByRole('button', {name:'A6: Empty', exact:true}).focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', {name:'A6: Media control', exact:true})).toBeFocused();
  for (const width of [1920,3840]) for (const mode of ['light','dark'] as const) {
    await page.setViewportSize({width,height:width === 1920 ? 1080 : 2160});
    await page.emulateMedia({colorScheme:mode});
    await page.screenshot({path:`${evidence}/experiments-${width}-${mode}.png`,fullPage:true});
  }
  const layout: string[][] = [];
  for (let c=1;c<=12;c++) for (const r of 'ABCDEFGH') {
    const w = `${r}${c}`;
    if (['A2','B2','A3','B3'].includes(w)) continue;
    if (c<=5 || w==='A6') layout.push([w,c===1 || w==='A6' ? 'MediaCtrl' : 'Cells']);
  }
  let body: any;
  await page.route(endpoint, async route => { body=route.request().postDataJSON(); await route.fulfill({json:{status:'succeeded',result:{experiment_id:123}}}); });
  await page.getByRole('button', {name:'Register',exact:true}).click();
  await expect(page.getByText('Experiment 123 registered.',{exact:true})).toBeVisible();
  expect(body).toEqual({token:expect.stringMatching(/^[0-9a-f]{32}$/),user_id:'Champions test',note:'Round one',schedule:1,
    parameters:{TargetWellVolume:650,MaxIteration:20,TopFractionToPropagate:1,BackgroundOD:0.036,InoculationOD:0.03,ODConversionFactor:2.52,FreezeVolume:0.5,V_OD_Sample:150,FreezeGeneration:1,UseFluorescence:1,GFP_scale:4669.1,GFP_RFPdamping:773.1,RFP_scale:2262.3,RFP_GFPdamping:305},layout});
  await expect(page.getByLabel('Experiment ID',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('Note',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('Schedule now')).not.toBeChecked();
});

test('keeps the draft on refusal and unknown outcome, and restricts access', async ({page}) => {
  await open(page);
  await page.getByLabel('Experiment ID',{exact:true}).fill('Retain me');
  await page.getByLabel('Note',{exact:true}).fill('Unsaved note');
  await page.getByLabel('MaxIteration',{exact:true}).fill('12');
  await page.route(endpoint, route => route.fulfill({json:{status:'error',message:'An experiment with this ID already exists.'}}));
  await page.getByRole('button',{name:'Register',exact:true}).click();
  await expect(page.getByText('An experiment with this ID already exists.',{exact:true})).toBeVisible();
  const tokens: string[] = [];
  await page.route(endpoint, route => { tokens.push(route.request().postDataJSON().token); return route.fulfill({json:{status:'unknown',message:'Commit could not be confirmed. Check whether experiment Retain me exists before trying again.'}}); });
  await page.getByRole('button',{name:'Register',exact:true}).click();
  await expect(page.getByText('Commit could not be confirmed.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Register',exact:true}).click();
  await expect.poll(() => tokens.length).toBe(2); expect(tokens[0]).toBe(tokens[1]);
  await expect(page.getByLabel('Experiment ID',{exact:true})).toHaveValue('Retain me');
  await expect(page.getByLabel('Note',{exact:true})).toHaveValue('Unsaved note');
  await expect(page.getByLabel('MaxIteration',{exact:true})).toHaveValue('12');
  await page.route(endpoint, route => route.abort());
  await page.getByRole('button',{name:'Register',exact:true}).click();
  await expect(page.getByText('Outcome unknown.',{exact:false})).toBeVisible();
  await page.getByRole('link',{name:'Database',exact:true}).click();
  await page.getByRole('link',{name:'Scheduling',exact:true}).click();
  await page.getByRole('tab',{name:'Experiments',exact:true}).click();
  await expect(page.getByLabel('Experiment ID',{exact:true})).toHaveValue('Retain me');
  await expect(page.getByText('Outcome unknown.',{exact:false})).toBeVisible();
  for (const [role, local] of [['admin',false],['user',true]] as const) {
    await page.route('**/api/auth/me', r => r.fulfill({json:{success:true,data:{user_id:'fixture',username:'Fixture',role,session:{is_local:local}}}}));
    await page.goto('/scheduling?section=experiments');
    await expect(page.getByLabel('Experiment ID',{exact:true})).toHaveCount(0);
    await expect(page).not.toHaveURL(/section=experiments/);
  }
});
