import { test, expect, type Page } from '@playwright/test';

// Phone navigation (below 900px): the paged page bar, Account and the section header.
// - A user sees pages their role does not permit (Scheduling, Labware, Admin), or Account is missing.
// - Pills of an off-screen group can be reached by Tab or a screen reader.
// - A swipe on the bar opens the pill under the finger, or a short drag snaps to another group.
// - A held run is invisible because the Scheduling pill's group is off-screen.
// - The bar opens on a group that does not hold the current page.
// - Section dots or the title menu lose the section on reload, or offer a section the user may not open.
// - The bar covers the end of the page.

const phone = { width: 390, height: 844 };
const pills = (page: Page) => page.getByRole('navigation', { name: 'Pages' });
const visiblePills = async (page: Page) => (await pills(page).getByRole('link').evaluateAll(links =>
  links.filter(link => !link.closest('[inert]')).map(link => link.textContent?.trim()))).filter(Boolean);
const signInAs = (page: Page, role: string) => page.route('**/api/auth/me', route => route.fulfill({ json: {
  success: true, data: { user_id: 'viewer-admin', username: 'operator', role, session_is_local: false, session: { is_local: false } } } }));

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
  await page.setViewportSize(phone);
});

test('the bar lists only permitted pages, four at a time, with Account last', async ({ page }) => {
  await signInAs(page, 'viewer');
  await page.goto('/');
  await expect(pills(page)).toBeVisible();
  expect(await visiblePills(page)).toEqual(['Overview', 'Camera', 'Database', 'Maintenance']);
  await page.getByRole('button', { name: 'Pages 5 to 7' }).click();
  expect(await visiblePills(page)).toEqual(['Logs', 'System status', 'Account']);
  await expect(pills(page).getByRole('link', { name: /Scheduling|Labware|Admin/ })).toHaveCount(0);
  await pills(page).getByRole('link', { name: 'Account', exact: true }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
  // Reopened on Account, the bar shows Account's group.
  await page.reload();
  expect(await visiblePills(page)).toContain('Account');
});

test('off-screen pills take no focus, and a swipe changes group without opening a page', async ({ page }) => {
  await page.goto('/');
  // Admin, phone order: Overview Scheduling Camera Labware | Database Maintenance Logs System status | Admin Account.
  await expect(pills(page).getByRole('link', { name: 'Overview', exact: true })).toHaveAttribute('aria-current', 'page');
  // Every pill except the current group's must refuse focus (aria-hidden alone would still let Tab reach it).
  const focusable = await page.locator('nav[aria-label="Pages"] a').evaluateAll(links => links.map(link => {
    (link as HTMLElement).focus();
    return document.activeElement === link ? link.textContent?.trim() : null;
  }).filter(Boolean));
  expect(focusable).toEqual(['Overview', 'Scheduling', 'Camera', 'Labware']);
  const row = pills(page).getByRole('link', { name: 'Camera', exact: true });
  const box = (await row.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x - 120, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => visiblePills(page)).toEqual(['Database', 'Maintenance', 'Logs', 'System status']);
  await expect(page).toHaveURL(/\/$/);
  // A short drag snaps back.
  const database = (await pills(page).getByRole('link', { name: 'Database', exact: true }).boundingBox())!;
  await page.mouse.move(database.x + 10, database.y + 10);
  await page.mouse.down();
  await page.mouse.move(database.x + 30, database.y + 10, { steps: 4 });
  await page.mouse.up();
  await expect.poll(() => visiblePills(page)).toEqual(['Database', 'Maintenance', 'Logs', 'System status']);
  await expect(page).toHaveURL(/\/$/);
});

test('a held run shows on the Scheduling pill, and on its group dot while that group is away', async ({ page }) => {
  await page.route('**/api/scheduling/status/queue', route => route.fulfill({ json: { success: true, data: {
    queue: { queued_jobs: 0, running_job_details: [] }, hamilton: { is_running: false },
    manual_recovery: { active: true, storage_healthy: true, safety_revision: 4,
      pending_recoveries: [{ schedule_id: 'feed2', experiment_name: 'Cell feeding · stack 2', note: 'No log activity for 3 min.' }] } } } }));
  await page.goto('/logfile');
  // Logs is in the middle group, so the bar opens there and the first group (with Scheduling) is away.
  expect(await visiblePills(page)).toEqual(['Database', 'Maintenance', 'Logs', 'System status']);
  const dotColour = (name: string) => page.getByRole('button', { name }).locator('span').evaluate(dot => getComputedStyle(dot).backgroundColor);
  await expect.poll(() => dotColour('Pages 1 to 4')).not.toBe(await dotColour('Pages 9 to 10'));
  await page.getByRole('button', { name: 'Pages 1 to 4' }).click();
  await expect(pills(page).getByRole('link', { name: 'Scheduling, recovery requires attention' })).toBeVisible();
});

test('section dots and the title menu keep the section in the address', async ({ page }) => {
  await page.goto('/scheduling');
  const heading = page.locator('main h1');
  await expect(heading).toHaveText('Schedules');
  await page.getByRole('navigation', { name: 'Scheduling sections' }).getByRole('link', { name: 'History', exact: true }).click();
  await expect(page).toHaveURL(/section=history/);
  await expect(heading).toHaveText('History');
  await page.reload();
  await expect(heading).toHaveText('History');
  await heading.getByRole('button').click();
  await page.getByRole('menuitem', { name: 'Calendar' }).click();
  await expect(page).toHaveURL(/section=calendar/);
  // Remote session: local-only sections are neither dots nor menu items.
  await expect(page.getByRole('navigation', { name: 'Scheduling sections' }).getByRole('link', { name: 'Methods' })).toHaveCount(0);
});

test('the end of a page stays above the bar', async ({ page }) => {
  await page.goto('/system-status');
  await page.locator('main').evaluate(main => main.scrollTo(0, main.scrollHeight));
  const barTop = await pills(page).evaluate(nav => nav.getBoundingClientRect().top);
  const contentBottom = await page.locator('main').evaluate(main => {
    const last = main.lastElementChild?.lastElementChild ?? main;
    return last.getBoundingClientRect().bottom;
  });
  expect(contentBottom).toBeLessThanOrEqual(barTop);
});
