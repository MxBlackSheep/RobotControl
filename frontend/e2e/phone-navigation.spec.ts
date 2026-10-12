import { test, expect, type Page } from '@playwright/test';

// Phone navigation (below 900px): four fixed tabs, More, and the page heading.
// - A role sees a tab or More entry it may not open (Runs, Tip racks, Cytomat for a viewer).
// - The tab of the current place is not marked; a page opened from More marks no tab or the wrong one.
// - A held run is invisible from the tabs.
// - A page opened from More has no way back, or is titled differently from the entry that was tapped.
// - Runs shows a section menu over its own Agenda/History switch (phone-runs.spec.ts covers the switch).
// - The tabs cover the end of a page.

const phone = { width: 390, height: 844 };
const tabs = (page: Page) => page.getByRole('navigation', { name: 'Pages' });
const signInAs = (page: Page, role: string) => page.route('**/api/auth/me', route => route.fulfill({ json: {
  success: true, data: { user_id: 'viewer-admin', username: 'operator', role, session_is_local: false, session: { is_local: false } } } }));

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.setViewportSize(phone);
});

test('tabs and More list only what the role may open, and More pages lead back', async ({ page }) => {
  await signInAs(page, 'viewer');
  await page.goto('/');
  await expect(tabs(page).getByRole('link')).toHaveText(['Now', 'Camera', 'More']);
  await expect(tabs(page).getByRole('link', { name: 'Now', exact: true })).toHaveAttribute('aria-current', 'page');
  await tabs(page).getByRole('link', { name: 'More', exact: true }).click();
  const more = page.getByRole('list', { name: 'More pages' });
  await expect(more.getByRole('link')).toHaveText(['Run logs', 'Database tables', 'Reports', 'System status', 'Account']);
  await more.getByRole('link', { name: 'Account' }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.locator('main h1')).toHaveText('Account');
  // Pages opened from More belong to the More tab.
  await expect(tabs(page).getByRole('link', { name: 'More', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
  await page.getByRole('link', { name: 'More', exact: true }).first().click();
  await expect(page).toHaveURL(/\/more$/);
});

test('a More entry opens its section, titled with the name that was tapped', async ({ page }) => {
  await page.goto('/more');
  const more = page.getByRole('list', { name: 'More pages' });
  await expect(more.getByRole('link')).toHaveText(['Tip racks', 'Cytomat', 'Run logs', 'Database tables', 'Reports', 'System status', 'Account']);
  await more.getByRole('link', { name: 'Reports' }).click();
  await expect(page).toHaveURL(/\/database\?section=retrieval$/);
  await expect(page.locator('main h1')).toHaveText('Reports');
  // No section menu: other database sections are workstation work.
  await expect(page.locator('main h1').getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('main').getByRole('link', { name: 'More', exact: true })).toBeVisible();
});

test('a held run marks the Now tab', async ({ page }) => {
  await page.route('**/api/scheduling/status/queue', route => route.fulfill({ json: { success: true, data: {
    queue: { queued_jobs: 0, running_job_details: [] }, hamilton: { is_running: false },
    manual_recovery: { active: true, storage_healthy: true, safety_revision: 4,
      pending_recoveries: [{ schedule_id: 'feed2', experiment_name: 'Cell feeding · stack 2', note: 'No log activity for 3 min.' }] } } } }));
  await page.goto('/logfile');
  await expect(tabs(page).getByRole('link', { name: 'Now, 1 run needs recovery' })).toBeVisible();
});

test('Runs is a plain title over its own Agenda and History switch', async ({ page }) => {
  await page.goto('/scheduling');
  await expect(page.locator('main h1')).toHaveText('Runs');
  await expect(page.locator('main h1').getByRole('button')).toHaveCount(0);
  await expect(tabs(page).getByRole('link', { name: 'Runs', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('group', { name: 'Runs view' })).toBeVisible();
});

test('the end of a page stays above the tabs', async ({ page }) => {
  await page.goto('/system-status');
  await page.locator('main').evaluate(main => main.scrollTo(0, main.scrollHeight));
  const barTop = await tabs(page).evaluate(nav => nav.getBoundingClientRect().top);
  const contentBottom = await page.locator('main').evaluate(main => {
    const last = main.lastElementChild?.lastElementChild ?? main;
    return last.getBoundingClientRect().bottom;
  });
  expect(contentBottom).toBeLessThanOrEqual(barTop);
});
