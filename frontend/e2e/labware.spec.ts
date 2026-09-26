import { expect, Page, test } from '@playwright/test';

async function fixtures(page:Page, canUpdate=true, realDeck=false) {
  await page.addInitScript(()=>localStorage.setItem('access_token','viewer-admin'));
  const permissions={role:'admin',is_local_session:canUpdate,can_update:canUpdate};
  const statuses=['clean','empty','dirty','rinsed','washed','reserved','unclear'];
  const tips={grid:{rows:8,cols:12,positions_per_rack:96},auto_refresh_ms:1000,status_order:statuses,status_colors:{clean:'#22c55e',empty:'#d1d5db',dirty:'#ef4444',rinsed:'#3b82f6',washed:'#a855f7',reserved:'#f59e0b',unclear:'#6b7280'},unknown_status:'unclear',refreshed_at:'2026-09-26T12:00:00Z',permissions,families:[
    {family_id:'tips300',display_name:'300 µL tips',left_racks:['Rack A','Rack A5','Rack A2','Rack A8','Rack A9'],right_racks:['Rack B','Rack B4','Rack B7','Rack B3','Rack B10'],reset_map:{},tips:{'Rack A':Object.fromEntries(Array.from({length:96},(_,i)=>[String(i+1),'clean'])),'Rack B':{}}},
    {family_id:'tips1000',display_name:'1000 µL tips',left_racks:['Rack C'],right_racks:[],reset_map:{},tips:{'Rack C':{}}},
  ]};
  if(realDeck){
    const family=tips.families[0];family.left_racks=['VER_ST_0001','VER_ST_0002','VER_ST_0003','VER_ST_0006','VER_ST_0009'];family.right_racks=['VER_ST_0004','VER_ST_0005','VER_ST_0007','VER_ST_0008','VER_ST_0010'];
    family.tips=Object.fromEntries([...family.left_racks,...family.right_racks].map((rack,rackIndex)=>[rack,Object.fromEntries(Array.from({length:96},(_,i)=>[String(i+1),statuses[(Math.floor(i/8)+rackIndex)%statuses.length]]))])) as typeof family.tips;
  }
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

async function chooseStatus(page:Page,status='Dirty'){
  await page.getByRole('combobox',{name:'Set tips to',exact:true}).click();
  await page.getByRole('option',{name:status,exact:true}).click();
}

test('selected rack has keyboard access and saves cannot lose newer edits',async({page},info)=>{
  const state=await fixtures(page);
  await page.goto('/labware');
  await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();
  const first=page.getByRole('button',{name:'Tip 1, clean',exact:true});
  await first.focus();await first.press('ArrowDown');
  await expect(page.getByRole('button',{name:'Tip 2, clean',exact:true})).toBeFocused();
  const bottom=page.getByRole('button',{name:'Tip 8, clean',exact:true});
  await bottom.focus();await bottom.press('ArrowDown');
  await expect(bottom).toBeFocused();
  await chooseStatus(page);
  await page.getByRole('button',{name:'Tip 2, clean',exact:true}).dblclick();
  const reads=state.reads;await page.waitForTimeout(1200);expect(state.reads).toBe(reads);
  let release!:()=>void;state.saveGate=new Promise<void>(resolve=>release=resolve);
  await page.getByRole('button',{name:/Save changes/}).click();
  await expect.poll(()=>state.writes.length).toBe(1);
  await expect(page.getByRole('combobox',{name:'Set tips to',exact:true})).toBeDisabled();
  await expect(page.getByRole('combobox',{name:'Tip family'})).toBeDisabled();
  release();
  await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Tip 2, dirty',exact:true})).toBeVisible();
  expect(state.writes[0]).toEqual({family:'tips300',updates:[{labware_id:'Rack A',position_id:2,status:'dirty'}]});
  await info.attach('rack-keyboard-save',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});

test('phone rack painting keeps drafts across section changes and failed saves',async({page},info)=>{
  const state=await fixtures(page);state.failSave=true;
  await page.setViewportSize({width:320,height:740});
  await page.goto('/labware');
  await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();
  await chooseStatus(page);
  await page.getByRole('button',{name:'Tip 1, clean',exact:true}).dblclick();
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
  await info.attach('rack-phone-draft',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});

for (const width of [1280,320]) test(`deck preserves both carrier columns and all ten racks at ${width}px`,async({page},info)=>{
  await fixtures(page,true,true);await page.setViewportSize({width,height:720});await page.goto('/labware');
  const deck=page.getByRole('region',{name:'Tip deck'});
  const left=deck.getByRole('group',{name:'Col A',exact:true});const right=deck.getByRole('group',{name:'Col B',exact:true});
  await expect(left.getByRole('button')).toHaveCount(5);await expect(right.getByRole('button')).toHaveCount(5);
  expect(await left.getByRole('button').evaluateAll(items=>items.map(item=>item.getAttribute('aria-label')))).toEqual(['VER_ST_0001','VER_ST_0002','VER_ST_0003','VER_ST_0006','VER_ST_0009'].map(rack=>`Open rack ${rack}`));
  const a=await left.boundingBox();const b=await right.boundingBox();expect(b!.x).toBeGreaterThan(a!.x);expect(Math.abs(a!.y-b!.y)).toBeLessThan(2);
  await info.attach(`full-deck-${width}`,{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
  await page.getByRole('button',{name:'Open rack VER_ST_0002',exact:true}).click();
  await expect(page.getByRole('heading',{name:'VER_ST_0002',exact:true})).toBeVisible();
  if(width===320){await page.getByRole('button',{name:'Back to deck',exact:true}).click();await expect(page.getByRole('button',{name:'Open rack VER_ST_0002',exact:true})).toBeFocused();}
  else await expect(deck).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('rectangle paints coordinates once, cancels safely and Undo restores prior drafts',async({page},info)=>{
  const state=await fixtures(page);await page.setViewportSize({width:1440,height:1100});await page.goto('/labware');
  await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();await chooseStatus(page);
  const first=page.getByRole('button',{name:'Tip 1, clean',exact:true});await first.focus();await first.press('ArrowDown');
  await expect(page.getByRole('button',{name:'Tip 2, clean',exact:true})).toBeFocused();await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await page.getByRole('button',{name:'Tip 2, clean',exact:true}).press('Enter');
  await expect(page.getByRole('button',{name:'Tip 2, clean',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Tip 2, clean',exact:true}).press('Enter');
  const start=await first.boundingBox();const end=await page.getByRole('button',{name:'Tip 10, clean',exact:true}).boundingBox();
  await page.mouse.move(start!.x+22,start!.y+22);await page.mouse.down();await page.mouse.move(end!.x+22,end!.y+22,{steps:5});
  await expect(page.getByRole('button',{name:'Tip 1, clean',exact:true})).toBeVisible();
  await page.mouse.up();for(const tip of[1,2,9,10])await expect(page.getByRole('button',{name:`Tip ${tip}, dirty`,exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await expect(page.getByRole('button',{name:'Tip 2, dirty',exact:true})).toBeVisible();for(const tip of[1,9,10])await expect(page.getByRole('button',{name:`Tip ${tip}, clean`,exact:true})).toBeVisible();
  await page.mouse.move(start!.x+22,start!.y+22);await page.mouse.down();await page.mouse.move(end!.x+22,end!.y+22,{steps:4});await page.keyboard.press('Escape');await page.mouse.up();
  await expect(page.getByRole('button',{name:'Tip 1, clean',exact:true})).toBeVisible();
  await first.dispatchEvent('pointerdown',{pointerId:7,pointerType:'pen',button:0,buttons:1,clientX:start!.x+22,clientY:start!.y+22});
  await first.dispatchEvent('pointercancel',{pointerId:7,pointerType:'pen'});
  await expect(page.getByRole('button',{name:'Cancel selection',exact:true})).toHaveCount(0);
  await page.mouse.move(start!.x+22,start!.y+22);await page.mouse.down();await page.mouse.move(end!.x+22,end!.y+22,{steps:4});await page.mouse.move(5,5);await page.mouse.up();
  await expect(page.getByRole('button',{name:'Tip 1, clean',exact:true})).toBeVisible();expect(state.writes).toEqual([]);
  await page.getByRole('button',{name:'Undo',exact:true}).click();await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await info.attach('rectangle-undo-cancel',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});

test.describe('touch editing',()=>{
test.use({hasTouch:true,isMobile:true});
test('phone rectangle uses two corners and Back preserves paint and orientation',async({page},info)=>{
  const state=await fixtures(page);await page.setViewportSize({width:320,height:800});await page.goto('/labware');await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Rack A',exact:true})).toBeVisible();
  await chooseStatus(page);
  const first=page.getByRole('button',{name:'Tip 1, clean',exact:true});await first.scrollIntoViewIfNeeded();const bounds=await first.boundingBox();
  const touch=await page.context().newCDPSession(page);
  await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:bounds!.x+22,y:bounds!.y+22}]});
  await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:bounds!.x+22,y:bounds!.y-90}]});
  await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await first.tap();await first.tap();await expect(page.getByRole('button',{name:'Tip 1, dirty',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Undo',exact:true}).tap();await expect(first).toBeVisible();
  await first.tap();await expect(page.getByRole('button',{name:'Cancel selection',exact:true})).toBeVisible();
  const reads=state.reads;await page.waitForTimeout(1200);expect(state.reads).toBe(reads);
  await page.getByRole('button',{name:'Tip 10, clean',exact:true}).tap();for(const tip of[1,2,9,10])await expect(page.getByRole('button',{name:`Tip ${tip}, dirty`,exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Back to deck',exact:true}).click();await page.getByRole('button',{name:'Open rack Rack B',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Set tips to',exact:true})).toContainText('Dirty');
  await page.getByRole('button',{name:'Back to deck',exact:true}).click();await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();
  await expect(page.getByRole('button',{name:'Tip 10, dirty',exact:true})).toBeVisible();
  await info.attach('phone-two-corner-paint',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});
test('phone selection survives native horizontal scrolling to a distant corner',async({page},info)=>{
  const state=await fixtures(page);await page.setViewportSize({width:320,height:800});await page.goto('/labware');await page.getByRole('button',{name:'Open rack Rack A',exact:true}).tap();await chooseStatus(page);
  const first=page.getByRole('button',{name:'Tip 1, clean',exact:true});await first.tap();
  const grid=page.getByRole('group',{name:'Rack A tips',exact:true});const scrollArea=grid.locator('..');const area=await scrollArea.boundingBox();
  const x=area!.x+area!.width-24,y=area!.y+100;
  const touch=await page.context().newCDPSession(page);
  await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
  for(let step=1;step<=8;step++)await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-step*26,y}]});
  await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await expect.poll(()=>scrollArea.evaluate(element=>element.scrollLeft)).toBeGreaterThan(100);
  await expect(page.getByRole('button',{name:'Cancel selection',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await page.getByRole('button',{name:'Tip 89, clean',exact:true}).tap();
  await expect(grid.getByRole('button',{name:/, dirty$/})).toHaveCount(12);await expect(page.getByRole('button',{name:'Tip 90, clean',exact:true})).toBeVisible();
  expect(state.writes).toEqual([]);
  await info.attach('phone-across-columns',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
  await page.getByRole('button',{name:'Undo',exact:true}).tap();await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
});
});

test('read-only tip deck permits inspection and never exposes painting',async({page},info)=>{
  const state=await fixtures(page,false);await page.goto('/labware');await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();
  await page.getByRole('button',{name:'Tip 1, clean',exact:true}).click();await expect(page.getByRole('combobox',{name:'Set tips to',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:/Save changes/})).toHaveCount(0);expect(state.writes).toEqual([]);
  await info.attach('read-only-tip-deck',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});

for(const viewport of [{width:3840,height:2160},{width:1920,height:1080},{width:1366,height:768},{width:1280,height:720},{width:1024,height:768},{width:1024,height:600},{width:390,height:844},{width:320,height:720}]){
test(`rack sizing and bulk controls at ${viewport.width}x${viewport.height}`,async({page},info)=>{
  await fixtures(page,true,true);if(viewport.width===1920)await page.addInitScript(()=>localStorage.setItem('robotcontrol-appearance','dark'));await page.setViewportSize(viewport);await page.goto('/labware');
  await page.getByRole('button',{name:'Open rack VER_ST_0001',exact:true}).click();await chooseStatus(page);
  const grid=page.getByRole('group',{name:'VER_ST_0001 tips',exact:true});
  const cell=grid.getByRole('button').first();const last=grid.getByRole('button').last();
  await expect(cell).toBeVisible();const dimensions=await cell.boundingBox();expect(dimensions!.width).toBeGreaterThanOrEqual(43.9);expect(Math.abs(dimensions!.width-dimensions!.height)).toBeLessThan(1.1);
  const canvas=await grid.boundingBox();const card=await grid.locator('xpath=ancestor::*[@data-rack-editor]').boundingBox();
  if(viewport.width>=1280){expect(card!.width-canvas!.width).toBeLessThan(40);const bottom=await last.boundingBox();expect(bottom!.y+bottom!.height).toBeLessThanOrEqual(viewport.height-16);}
  if(viewport.width===3840)expect(dimensions!.width).toBeGreaterThan(85);
  await expect(page.getByRole('button',{name:'Set entire rack',exact:true})).toBeEnabled();
  for(const name of['Paint','Rectangle','Inspect','Paint row','Paint column','Paint rack','Paint range'])await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await info.attach(`rack-layout-${viewport.width}x${viewport.height}`,{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});
}

test.describe('high DPI rack',()=>{
test.use({viewport:{width:1920,height:1080},deviceScaleFactor:2});
test('same layout at high DPI and natural whole-rack action',async({page},info)=>{
  const state=await fixtures(page,true,true);await page.goto('/labware');await page.getByRole('button',{name:'Open rack VER_ST_0001',exact:true}).click();await chooseStatus(page);
  const grid=page.getByRole('group',{name:'VER_ST_0001 tips',exact:true});const size=await grid.getByRole('button').first().boundingBox();expect(size!.width).toBeGreaterThanOrEqual(44);
  await page.getByRole('button',{name:'Set entire rack',exact:true}).click();await expect(grid.getByRole('button',{name:/, dirty$/})).toHaveCount(96);expect(state.writes).toEqual([]);
  await page.getByRole('button',{name:'Undo',exact:true}).click();await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await info.attach('rack-1920-css-at-2x',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});
});

test('scrolling keeps rack size stable and resizing cancels an unfinished selection',async({page},info)=>{
  await fixtures(page);await page.setViewportSize({width:1024,height:600});await page.goto('/labware');await page.getByRole('button',{name:'Open rack Rack A',exact:true}).click();await chooseStatus(page);
  const first=page.getByRole('button',{name:'Tip 1, clean',exact:true});const before=await first.boundingBox();
  await page.getByRole('button',{name:'Tip 96, clean',exact:true}).scrollIntoViewIfNeeded();const after=await first.boundingBox();expect(after!.width).toBe(before!.width);expect(after!.height).toBe(before!.height);
  await first.click();await expect(page.getByRole('button',{name:'Cancel selection',exact:true})).toBeVisible();
  await page.setViewportSize({width:1100,height:650});await expect(page.getByRole('button',{name:'Cancel selection',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:/Save changes/})).toBeDisabled();
  await info.attach('rack-scroll-and-resize',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});

test('initial Labware errors are recoverable and read-only sessions have no editor',async({page},info)=>{
  const state=await fixtures(page,false);state.failRead=true;
  await page.goto('/labware?section=cytomat');
  await expect(page.getByRole('alert')).toContainText('Cytomat service unavailable');
  await expect(page.getByText('No positions found.',{exact:true})).toHaveCount(0);
  state.failRead=false;await page.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(page.getByText('P100',{exact:true})).toBeVisible();
  await expect(page.getByText('Read only',{exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Plate at A1'})).toHaveCount(0);
  expect(state.writes).toEqual([]);
  await info.attach('cytomat-read-only',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});

test('Cytomat contextual editor retains failed empty assignment and protects save',async({page},info)=>{
  const state=await fixtures(page);state.failSave=true;
  await page.goto('/labware?section=cytomat');
  await page.getByRole('button',{name:'Edit position A1',exact:true}).click();
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
  await info.attach('cytomat-context-editor',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
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
  await info.attach('malformed-labware-recovery',{body:await page.screenshot({animations:'disabled'}),contentType:'image/png'});
});
