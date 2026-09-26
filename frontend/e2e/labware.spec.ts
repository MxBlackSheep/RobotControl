import { expect, Page, test } from '@playwright/test';

async function fixtures(page:Page, canUpdate=true) {
  await page.addInitScript(()=>localStorage.setItem('access_token','viewer-admin'));
  const permissions={role:'admin',is_local_session:canUpdate,can_update:canUpdate};
  const tips={grid:{rows:8,cols:12,positions_per_rack:96},auto_refresh_ms:1000,status_order:['clean','dirty','empty'],status_colors:{clean:'#2e7d32',dirty:'#c62828',empty:'#607d8b'},unknown_status:'empty',refreshed_at:'2026-09-26T12:00:00Z',permissions,families:[
    {family_id:'tips300',display_name:'300 µL tips',left_racks:['Rack A'],right_racks:['Rack B'],reset_map:{},tips:{'Rack A':Object.fromEntries(Array.from({length:96},(_,i)=>[String(i+1),'clean'])),'Rack B':{}}},
    {family_id:'tips1000',display_name:'1000 µL tips',left_racks:['Rack C'],right_racks:[],reset_map:{},tips:{'Rack C':{}}},
  ]};
  const cytomat={rows:[{cytomat_pos:'A1',plate_id:'P100'},{cytomat_pos:'A2',plate_id:''}],plate_options:['','P100','P200'],auto_refresh_ms:1000,permissions,refreshed_at:'2026-09-26T12:00:00Z'};
  const state={reads:0,writes:[] as any[],failRead:false,failSave:false,saveGate:null as Promise<void>|null};
  await page.route('**/api/labware/tip-tracking', async route=>{
    if(route.request().method()==='PUT') {
      const payload=route.request().postDataJSON();state.writes.push(payload);
      if(state.saveGate)await state.saveGate;
      if(state.failSave)return route.fulfill({status:500,json:{message:'Save failed'}});
      const family=tips.families.find(f=>f.family_id===payload.family)!;
      for(const edit of payload.updates){(family.tips as any)[edit.labware_id] ||= {}; (family.tips as any)[edit.labware_id][edit.position_id]=edit.status;}
      return route.fulfill({json:{data:{family:payload.family,requested_count:payload.updates.length,updated_count:payload.updates.length}}});
    }
    state.reads++;
    return state.failRead?route.fulfill({status:500,json:{message:'Tip service unavailable'}}):route.fulfill({json:{data:tips}});
  });
  await page.route('**/api/labware/cytomat',async route=>{
    if(route.request().method()==='PUT'){
      const payload=route.request().postDataJSON();state.writes.push(payload);
      if(state.saveGate)await state.saveGate;
      if(state.failSave)return route.fulfill({status:500,json:{message:'Save failed'}});
      for(const edit of payload.updates)cytomat.rows.find(row=>row.cytomat_pos===edit.cytomat_pos)!.plate_id=edit.plate_id;
      return route.fulfill({json:{data:{requested_count:payload.updates.length,updated_count:payload.updates.length}}});
    }
    state.reads++;
    return state.failRead?route.fulfill({status:500,json:{message:'Cytomat service unavailable'}}):route.fulfill({json:{data:cytomat}});
  });
  return state;
}

test('selected rack has keyboard access and saves cannot lose newer edits',async({page},info)=>{
  const state=await fixtures(page);
  await page.goto('/labware');
  await page.getByRole('button',{name:'Open rack Rack A'}).click();
  await page.getByRole('button',{name:'Map',exact:true}).click();
  const first=page.getByRole('button',{name:'Tip 1, clean',exact:true});
  await first.focus();await first.press('ArrowDown');
  await expect(page.getByRole('button',{name:'Tip 2, clean',exact:true})).toBeFocused();
  const bottom=page.getByRole('button',{name:'Tip 8, clean',exact:true});
  await bottom.focus();await bottom.press('ArrowDown');
  await expect(bottom).toBeFocused();
  await page.getByRole('button',{name:'Tip 2, clean',exact:true}).click();
  await page.getByRole('combobox',{name:'New status'}).click();
  await page.getByRole('option',{name:'dirty',exact:true}).click();
  await page.getByRole('button',{name:'Apply status',exact:true}).click();
  const reads=state.reads;await page.waitForTimeout(1200);expect(state.reads).toBe(reads);
  let release!:()=>void;state.saveGate=new Promise<void>(resolve=>release=resolve);
  await page.getByRole('button',{name:/Save changes/}).click();
  await expect.poll(()=>state.writes.length).toBe(1);
  await expect(page.getByRole('button',{name:'Apply status',exact:true})).toBeDisabled();
  await expect(page.getByRole('combobox',{name:'Tip family'})).toBeDisabled();
  release();
  await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Tip 2, dirty',exact:true})).toBeVisible();
  expect(state.writes[0]).toEqual({family:'tips300',updates:[{labware_id:'Rack A',position_id:2,status:'dirty'}]});
  await info.attach('rack-keyboard-save',{body:await page.screenshot(),contentType:'image/png'});
});

test('phone rack list keeps drafts across section changes and failed saves',async({page},info)=>{
  const state=await fixtures(page);state.failSave=true;
  await page.setViewportSize({width:320,height:740});
  await page.goto('/labware');
  await page.getByRole('button',{name:'Open rack Rack A'}).click();
  await page.getByRole('button',{name:'List',exact:true}).click();
  await page.getByRole('button',{name:'Tip 1, clean',exact:true}).click();
  await page.getByRole('combobox',{name:'New status'}).click();
  await page.getByRole('option',{name:'dirty',exact:true}).click();
  await page.getByRole('button',{name:'Apply status',exact:true}).click();
  await page.getByRole('button',{name:/Save changes/}).click();
  await expect(page.getByRole('alert').filter({hasText:'Save failed'})).toBeVisible();
  await page.evaluate(()=>{history.pushState(null,'','/labware?section=cytomat');dispatchEvent(new PopStateEvent('popstate'));});
  await page.evaluate(()=>{history.pushState(null,'','/labware');dispatchEvent(new PopStateEvent('popstate'));});
  await expect(page.getByRole('button',{name:'Tip 1, dirty',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/Save changes/})).toBeEnabled();
  const leaving=page.waitForEvent('dialog');
  await page.evaluate(()=>{setTimeout(()=>location.reload(),0);});
  const warning=await leaving;expect(warning.type()).toBe('beforeunload');await warning.dismiss();
  await expect(page.getByRole('button',{name:'Tip 1, dirty',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await info.attach('rack-phone-draft',{body:await page.screenshot(),contentType:'image/png'});
});

test('initial Labware errors are recoverable and read-only sessions have no editor',async({page},info)=>{
  const state=await fixtures(page,false);state.failRead=true;
  await page.goto('/labware?section=cytomat');
  await expect(page.getByRole('alert')).toContainText('Cytomat service unavailable');
  await expect(page.getByText('No positions found.',{exact:true})).toHaveCount(0);
  state.failRead=false;await page.getByRole('button',{name:'Retry',exact:true}).click();
  await page.getByRole('button',{name:'Position A1, P100',exact:true}).click();
  await expect(page.getByText('Read only',{exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Plate at A1'})).toHaveCount(0);
  expect(state.writes).toEqual([]);
  await info.attach('cytomat-read-only',{body:await page.screenshot(),contentType:'image/png'});
});

test('Cytomat contextual editor retains failed empty assignment and protects save',async({page},info)=>{
  const state=await fixtures(page);state.failSave=true;
  await page.goto('/labware?section=cytomat');
  await page.getByRole('button',{name:'Position A1, P100',exact:true}).click();
  await page.getByRole('combobox',{name:'Plate at A1'}).click();
  await page.getByRole('option',{name:'Empty',exact:true}).click();
  await page.getByRole('button',{name:/Save changes/}).click();
  await expect(page.getByRole('alert').filter({hasText:'Save failed'})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Plate at A1'})).toHaveText('Empty');
  state.failSave=false;let release!:()=>void;state.saveGate=new Promise<void>(resolve=>release=resolve);
  await page.getByRole('button',{name:/Save changes/}).click();
  await expect.poll(()=>state.writes.length).toBe(2);
  await expect(page.getByRole('combobox',{name:'Plate at A1'})).toBeDisabled();
  release();await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  expect(state.writes[1]).toEqual({updates:[{cytomat_pos:'A1',plate_id:''}]});
  await info.attach('cytomat-context-editor',{body:await page.screenshot(),contentType:'image/png'});
});

test('malformed Labware snapshots show an error without crashing the page',async({page},info)=>{
  await fixtures(page);
  await page.route('**/api/labware/cytomat',route=>route.fulfill({json:{data:{active:false}}}));
  await page.goto('/labware?section=cytomat');
  await expect(page.getByRole('alert')).toContainText('Labware data unavailable');
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible();
  await page.route('**/api/labware/tip-tracking',route=>route.fulfill({json:{data:{families:[]}}}));
  await page.goto('/labware');
  await expect(page.getByRole('alert')).toContainText('Labware data unavailable');
  await expect(page.getByRole('heading',{name:'Labware',exact:true})).toBeVisible();
  await info.attach('malformed-labware-recovery',{body:await page.screenshot(),contentType:'image/png'});
});
