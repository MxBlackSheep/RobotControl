// Called by backend/e2e/packaged_walkthrough.py while its relocated EXE is running.
// Visits every navigation page and section as a local admin and records what the
// page asked the real backend for. Failure cases (written before this script):
//   1. a page calls an API route that no longer exists (HTTP 404/405);
//   2. a page throws (pageerror / console error) or shows the lazy-load failure text;
//   3. a lazy page chunk or static asset is missing from the package;
//   4. a route used by a page returns 5xx for a reason other than the deliberately
//      unreachable SQL Server;
//   5. a navigation entry renders a blank page.
// PACKAGED_E2E_PORT comes from the launcher, which has proven its own app listens there.
const { chromium } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const output = process.env.WALKTHROUGH_EVIDENCE;
if (!process.env.PACKAGED_E2E_PORT) throw new Error('Run through backend/e2e/packaged_walkthrough.py, which sets PACKAGED_E2E_PORT');
const base = `http://127.0.0.1:${process.env.PACKAGED_E2E_PORT}`;
const pages = [
  ['/', []], ['/database', ['tables', 'procedures', 'restore', 'operations', 'retrieval', 'packages', 'settings']],
  ['/scheduling', ['schedules', 'methods', 'calendar', 'history', 'archived', 'recovery', 'notifications']],
  ['/camera', ['archive', 'live']], ['/labware', ['tips', 'cytomat']], ['/maintenance', []],
  ['/logfile', ['python', 'hamilton', 'robotcontrol']], ['/system-status', []],
  ['/admin', ['users', 'password-resets', 'storage']], ['/about', []],
];

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await context.addInitScript(token => localStorage.setItem('access_token', token), process.env.WALKTHROUGH_TOKEN);
  const page = await context.newPage();
  const visits = [];
  let current = null;
  page.on('response', response => {
    const url = new URL(response.url());
    if (current && (url.pathname.startsWith('/api/') || url.pathname.startsWith('/assets/')))
      current.requests.push({ method: response.request().method(), path: url.pathname, status: response.status() });
  });
  page.on('requestfailed', request => { if (current) current.requests.push({ method: request.method(), path: new URL(request.url()).pathname, status: 'failed', error: request.failure()?.errorText }); });
  page.on('pageerror', error => { if (current) current.errors.push('pageerror: ' + error.message); });
  page.on('console', message => { if (current && message.type() === 'error') current.errors.push('console: ' + message.text()); });
  for (const [route, sections] of pages) {
    for (const section of sections.length ? sections : [null]) {
      const url = section ? `${route}?section=${section}` : route;
      current = { url, requests: [], errors: [] };
      await page.goto(base + url);
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(1500);
      const text = await page.locator('#root').innerText();
      current.visibleCharacters = text.trim().length;
      current.loadFailure = /Failed to load component|Something went wrong/i.test(text);
      const file = url.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'dashboard';
      current.screenshot = `${file}.png`;
      await page.screenshot({ path: path.join(output, current.screenshot), fullPage: true, animations: 'disabled' });
      visits.push(current);
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(output, 'visits.json'), JSON.stringify(visits, null, 2));
})().catch(error => { console.error(error); process.exit(1); });
