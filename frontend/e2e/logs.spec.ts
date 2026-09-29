import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';

/** Failure cases for log readers (real log HTTP routes, disposable files):
 * - Development and packaged log roots agree. Remote administrators can read history;
 *   remote non-administrators and other readers' owners cannot.
 * - Folder, ZIP entry and relative paths cannot escape the configured root.
 * - Every section of a large archived log is reachable, not only its start and end, with
 *   no lost or duplicated UTF-8/UTF-16/CRLF/very long lines at section boundaries.
 * - Appending, replacing or truncating the source never produces a mixed snapshot.
 * - Corrupt gzip/ZIP, binary, missing or locked files, capacity limits and expiry fail
 *   clearly without hanging or blanking text that was already shown.
 * - Cancel or file switch stops the worker and its temporary copy; late responses never
 *   replace a newer selection. Follow is opt-in and hidden readers stop polling.
 * - Phones show the reader instead of the catalogue stacked above it, with no horizontal
 *   scroll. Back, resize and expansion keep selection, section, scroll and focus.
 */
test.beforeEach(async ({ page }) => { await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin')); });
const headers = { Authorization: 'Bearer viewer-admin' };
test('real log HTTP routes reconstruct every archived section and enforce reader ownership', async ({ request }) => {
  const manifest = await (await request.get('/__e2e/manifest')).json();
  for (const file of manifest.files) {
    const opened = await request.post('/api/logfiles/readers', { headers, data: {source_id:'robotcontrol_logs', relative_path:file.path, entry_path:file.entry} });
    expect(opened.ok()).toBeTruthy(); const reader = (await opened.json()).data;
    let state: any;
    await expect.poll(async () => { state = (await (await request.get(`/api/logfiles/readers/${reader.id}`,{headers})).json()).data; return state.state; }).toBe('ready');
    let cursor = 'first'; const chunks: string[] = []; const cursors: string[] = [];
    while (cursor) {
      const response = await request.get(`/api/logfiles/readers/${reader.id}/sections`, {headers, params:{cursor}});
      expect(response.ok()).toBeTruthy(); const chunk = (await response.json()).data;
      chunks.push(chunk.content); cursors.push(chunk.cursor); cursor = chunk.next_cursor;
    }
    expect(createHash('sha256').update(chunks.join('')).digest('hex')).toBe(file.sha256);
    let reverse = 'last'; const reversed: string[] = [];
    while (reverse) { const chunk = (await (await request.get(`/api/logfiles/readers/${reader.id}/sections`,{headers,params:{cursor:reverse}})).json()).data; reversed.unshift(chunk.content); reverse=chunk.previous_cursor; }
    expect(reversed.join('')).toBe(chunks.join(''));
    expect((await request.get(`/api/logfiles/readers/${reader.id}`,{headers:{Authorization:'Bearer other-admin'}})).status()).toBe(404);
    await request.delete(`/api/logfiles/readers/${reader.id}`, {headers});
    expect((await request.get(`/api/logfiles/readers/${reader.id}`,{headers})).status()).toBe(404);
  }
});
test('remote log policy, root, corrupt files and traversal are explicit', async ({ request }) => {
  const sources=(await (await request.get('/api/logfiles/sources',{headers})).json()).data;
  expect(sources.find((s:any)=>s.id==='robotcontrol_logs').path).toContain('viewer-e2e-');
  expect((await request.get('/api/logfiles/browse?source_id=robotcontrol_logs',{headers:{Authorization:'Bearer viewer-user','X-Forwarded-For':'203.0.113.20'}})).status()).toBe(403);
  expect((await request.post('/api/logfiles/readers',{headers,data:{source_id:'robotcontrol_logs',relative_path:'../outside.log'}})).status()).toBe(400);
  const bad=(await (await request.post('/api/logfiles/readers',{headers,data:{source_id:'robotcontrol_logs',relative_path:'history/corrupt.gz'}})).json()).data;
  await expect.poll(async()=> (await (await request.get(`/api/logfiles/readers/${bad.id}`,{headers})).json()).data.state).toBe('error');
  await request.delete(`/api/logfiles/readers/${bad.id}`,{headers});
});
test('phone history reader, section search and expansion retain selected file', async ({ page }) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/logfile?section=robotcontrol');
  await page.getByRole('button',{name:'History',exact:true}).click();
  await page.getByRole('button',{name:/unicode.log.gz/}).click();
  await expect(page.getByRole('checkbox',{name:'Follow latest'})).toHaveCount(0);
  await expect(page.getByLabel('Log content')).toContainText('END-MARKER');
  await page.getByRole('button',{name:'Beginning',exact:true}).click();
  await expect(page.getByLabel('Log content')).toContainText('START-MARKER');
  await page.getByRole('button', { name: 'Find', exact: true }).click();
  await page.getByLabel('Find in this section').fill('START-MARKER');
  await expect(page.getByText(/1 match/).first()).toBeVisible();
  await page.getByRole('button',{name:'Expand',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('START-MARKER');
  await page.keyboard.press('Escape');
  await expect(page.getByLabel('Find in this section')).toHaveValue('START-MARKER');
  await page.getByRole('button',{name:'Back to files',exact:true}).click();
  await page.getByRole('button',{name:/unicode.log.gz/}).click();
  await expect(page.getByLabel('Log content')).toContainText('START-MARKER');
  await page.evaluate(()=>{history.pushState(null,'','/logfile?section=python');dispatchEvent(new PopStateEvent('popstate'));});
  await page.evaluate(()=>{history.pushState(null,'','/logfile?section=robotcontrol');dispatchEvent(new PopStateEvent('popstate'));});
  await expect(page.getByLabel('Log content')).toContainText('START-MARKER');
  await page.getByRole('button',{name:'Newer section',exact:true}).click();
  await expect(page.getByText(/Section 2 of/)).toBeVisible();
  await page.setViewportSize({width:320,height:390});
  await page.getByRole('button',{name:'Latest',exact:true}).click();
  await expect(page.getByLabel('Log content')).toContainText('END-MARKER');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await page.screenshot({path:'../test-output/viewer-verification/log-phone.png',fullPage:true});
});

test('follow is opt-in and section navigation stops polling without Latest restarting it', async ({ page }) => {
  let previews = 0;
  page.on('request', req => { if (req.url().includes('/api/logfiles/preview?')) previews++; });
  await page.goto('/logfile?section=robotcontrol');
  await page.getByRole('button', { name: /robotcontrol_backend.log/ }).click();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-END');
  expect(previews).toBe(0);
  await page.getByRole('checkbox', { name: 'Follow latest' }).check();
  await expect.poll(() => previews).toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Beginning', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'Follow latest' })).not.toBeChecked();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-START');
  const stopped = previews;
  await page.getByRole('button', { name: 'Latest', exact: true }).click();
  await page.waitForTimeout(5500);
  expect(previews).toBe(stopped);
  await expect(page.getByRole('checkbox', { name: 'Follow latest' })).not.toBeChecked();
});

// Failure scenario: phone Back preserves the selected reader but sets detailOpen
// false. A desktop resize must report that the retained reader is visible again,
// or Follow immediately cancels and its captured reading copy cannot renew.
test('phone Back then desktop resize keeps the retained log reader usable', async ({ page }) => {
  let previews = 0;
  page.on('request', req => { if (req.url().includes('/api/logfiles/preview?')) previews++; });
  await page.setViewportSize({width:390,height:844});
  await page.goto('/logfile?section=robotcontrol');
  await page.getByRole('button', { name: /robotcontrol_backend.log/ }).click();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-END');
  await page.getByRole('button', { name: 'Back to files', exact: true }).click();
  await expect(page.getByLabel('Log content')).toBeHidden();
  await page.setViewportSize({width:1280,height:800});
  await expect(page.getByLabel('Log content')).toBeVisible();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-END');
  await page.getByRole('checkbox', { name: 'Follow latest' }).check();
  await expect.poll(() => previews).toBeGreaterThan(0);
  await expect(page.getByRole('checkbox', { name: 'Follow latest' })).toBeChecked();
  await expect(page.getByText('Reading stopped. Displayed text is retained.')).toHaveCount(0);
  await page.getByRole('button', { name: 'Beginning', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'Follow latest' })).not.toBeChecked();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-START');
  await page.screenshot({path:'../test-output/viewer-verification/log-phone-back-desktop.png',fullPage:true});
});

test('cancel, capacity, expiry and source growth preserve bounded reader behavior', async ({ request }) => {
  await request.post('/__e2e/readers',{data:{reset:true}});
  const create=async(path:string)=> (await (await request.post('/api/logfiles/readers',{headers,data:{source_id:'robotcontrol_logs',relative_path:path}})).json()).data;
  const state=async(id:string)=> (await (await request.get(`/api/logfiles/readers/${id}`,{headers})).json()).data;
  try {
    const cancelled=await create('history/unicode.log.gz');
    await request.delete(`/api/logfiles/readers/${cancelled.id}`,{headers});
    await expect.poll(async()=> (await (await request.post('/__e2e/readers',{data:{}})).json()).cache_bytes).toBe(0);
    await request.post('/__e2e/readers',{data:{max_reader_bytes:1024}});
    const large=await create('history/unicode.log.gz');
    await expect.poll(async()=> (await state(large.id)).state).toBe('error');
    expect((await state(large.id)).error).toContain('limit');
    await request.post('/__e2e/readers',{data:{reset:true,max_total_bytes:1024}});
    const full=await create('history/unicode.log.gz');
    await expect.poll(async()=> (await state(full.id)).state).toBe('error');
    expect((await state(full.id)).error).toContain('storage');
    await request.post('/__e2e/readers',{data:{reset:true}});
    const snapshot=await create('robotcontrol_backend.log');
    await expect.poll(async()=> (await state(snapshot.id)).state).toBe('ready');
    const before=(await (await request.get(`/api/logfiles/readers/${snapshot.id}/sections`,{headers})).json()).data.content;
    await request.post('/__e2e/readers',{data:{append:true}});
    expect((await state(snapshot.id)).source_changed).toBeTruthy();
    expect((await (await request.get(`/api/logfiles/readers/${snapshot.id}/sections`,{headers})).json()).data.content).toBe(before);
    await request.post('/__e2e/readers',{data:{expire:snapshot.id}});
    expect((await request.get(`/api/logfiles/readers/${snapshot.id}`,{headers})).status()).toBe(404);
    const denied=await request.get('/api/logfiles/browse?source_id=robotcontrol_logs',{headers:{Authorization:'Bearer viewer-user','X-E2E-Peer':'203.0.113.8','X-Forwarded-For':'127.0.0.1'}});
    expect(denied.status()).toBe(403);
  } finally { await request.post('/__e2e/readers',{data:{reset:true}}); }
});
