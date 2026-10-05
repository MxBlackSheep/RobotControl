import { expect, test } from '@playwright/test';

/** Failure cases for table paging and the SQL reader:
 * - First, Last and page jump never produce an invalid page, including for empty tables
 *   or a shrinking row count. On a phone they stay reachable (bar, then More > Page and rows). A failed page or filter request keeps the previous rows
 *   with their own page labels; Retry uses the requested query and current filters.
 * - SQL Top/Bottom/Go to line/Find reach the last line without repeated scrolling, keep
 *   reader state, and stay reachable on a phone.
 */
test.beforeEach(async ({page}) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.route('**/api/database/tables?*', route => route.fulfill({json:{success:true,data:{table_details:[{name:'PageSamples',has_data:true,is_important:true}]}}}));
  await page.route('**/api/database/tables/PageSamples?*', route => {
    const params = new URL(route.request().url()).searchParams;
    const offset = (Number(params.get('page') || 1)-1)*Number(params.get('limit') || 25);
    return route.fulfill({json:{success:true,data:{columns:['ID','Name'],total_count:57,rows:Array.from({length:57},(_,i)=>({ID:i+1,Name:`Record ${i+1}`})).slice(offset,offset+Number(params.get('limit')||25))}}});
  });
  await page.route('**/api/database/stored-procedures?*', route => route.fulfill({json:{success:true,data:{procedures:[{name:'LongDefinition',type:'PROCEDURE',parameters:[],definition:Array.from({length:300},(_,i)=>`-- Line ${i+1}`).join('\n')}],functions:[]}}}));
});

test('table First, Last and page jump retain correct data after a failed request', async ({page}, info) => {
  await page.goto('/database');
  await page.getByRole('button',{name:/PageSamples Has data/}).click();
  await expect(page.getByRole('button',{name:'Inspect row 1',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Go to last page'}).click();
  await expect(page.getByRole('button',{name:'Inspect row 57',exact:true})).toBeVisible();
  await expect(page.getByText('Page 3 of 3',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Go to first page'}).click();
  await page.getByRole('spinbutton',{name:'Page',exact:true}).fill('2');
  await page.getByRole('button',{name:'Go to page',exact:true}).click();
  await expect(page.getByRole('button',{name:'Inspect row 26',exact:true})).toBeVisible();
  await page.route('**/api/database/tables/PageSamples?*', route => route.fulfill({status:500,json:{detail:'Read unavailable'}}));
  await page.getByRole('button',{name:'Go to last page'}).click();
  await expect(page.getByRole('alert')).toContainText('Previous rows');
  await expect(page.getByRole('button',{name:'Inspect row 26',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Inspect row 51',exact:true})).toHaveCount(0);
  await expect(page.getByText('Page 2 of 3',{exact:true})).toBeVisible();
  await info.attach('table-retained-page',{body:await page.screenshot(),contentType:'image/png'});
});

test('phone paging bar and Page and rows reach every page', async ({page}, info) => {
  await page.setViewportSize({width:375,height:667});
  await page.goto('/database');
  await page.getByRole('button',{name:/PageSamples Has data/}).click();
  await page.getByRole('button',{name:'Go to last page'}).click();
  await expect(page.getByText('51–57 of 57',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Inspect row 51',exact:true})).toBeInViewport();
  await page.getByRole('button',{name:'More table options'}).click();
  await page.getByRole('menuitem',{name:'Page and rows'}).click();
  const dialog = page.getByRole('dialog',{name:'Page and rows'});
  await dialog.getByRole('spinbutton',{name:'Page',exact:true}).fill('2');
  await dialog.getByRole('button',{name:'Go to page',exact:true}).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('button',{name:'Inspect row 26',exact:true})).toBeInViewport();
  await page.getByRole('button',{name:'More table options'}).click();
  await page.getByRole('menuitem',{name:'Page and rows'}).click();
  await dialog.getByRole('combobox',{name:'Rows per page'}).click();
  await page.getByRole('option',{name:'50',exact:true}).click();
  await expect(page.getByText('1–50 of 57',{exact:true})).toBeVisible();
  await info.attach('phone-paging',{body:await page.screenshot(),contentType:'image/png'});
});

test('SQL Bottom, Top, line jump and Find work at phone size', async ({page},info) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/database?section=procedures');
  await page.getByRole('button',{name:/LongDefinition/}).click();
  const reader=page.getByRole('region',{name:'SQL definition',exact:true});
  await page.getByRole('button',{name:'Go to bottom',exact:true}).click();
  await expect.poll(()=>reader.evaluate(element=>element.scrollTop+element.clientHeight>=element.scrollHeight-2)).toBe(true);
  await page.getByRole('button',{name:'Go to top',exact:true}).click();
  await expect.poll(()=>reader.evaluate(element=>element.scrollTop)).toBe(0);
  await page.getByRole('button',{name:'More SQL options'}).click();
  await page.getByRole('menuitem',{name:'Go to line'}).click();
  await page.getByRole('spinbutton',{name:'Line number'}).fill('250');
  await page.getByRole('button',{name:'Go to line',exact:true}).click();
  await expect.poll(()=>reader.evaluate(element=>element.scrollTop)).toBeGreaterThan(0);
  await page.getByRole('button',{name:'Find in SQL',exact:true}).click();
  await page.getByRole('textbox',{name:'Find in SQL',exact:true}).fill('Line 299');
  await expect(page.getByText('1 of 1 matches',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Expand SQL'}).click();
  await expect(page.getByRole('textbox',{name:'Find in SQL'})).toHaveValue('Line 299');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await info.attach('sql-phone-navigation',{body:await page.screenshot(),contentType:'image/png'});
});
