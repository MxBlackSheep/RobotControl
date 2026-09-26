import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }, info) => {
  if (info.title.startsWith('system appearance')) return;
  await page.addInitScript(() => localStorage.setItem('access_token', 'viewer-admin'));
});

test('maintenance does not enable actions for malformed state', async ({ page }) => {
  await page.route('**/api/maintenance/hxrun*', route => route.fulfill({ json: { success: true, data: { permissions: { can_edit: true } } } }));
  await page.goto('/maintenance');
  await expect(page.getByText('State unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enter maintenance', exact: true })).toBeDisabled();
});

test('appearance persists and log content receives the default reading space', async ({ page }, info) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('/logfile?section=robotcontrol');
  await page.getByRole('button', { name: /robotcontrol_backend.log/ }).click();
  await expect(page.getByLabel('Log content')).toContainText('ACTIVE-END');
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
  const bounds = await page.getByLabel('Log content').boundingBox();
  expect(bounds!.height / 720).toBeGreaterThanOrEqual(.60);
  await info.attach('log-space', { body: JSON.stringify({ viewport: 720, content: bounds!.height }), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath('dark-logs.png'), animations: 'disabled' });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Light', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light');
});

test('maintenance initial failure is unknown and a retry preserves reason edits', async ({ page }) => {
  let broken = true;
  await page.route('**/api/maintenance/hxrun*', route => route.fulfill(broken
    ? { status: 500, json: { detail: 'Unavailable' } }
    : { json: { success: true, data: { enabled: false, reason: '', permissions: { can_edit: true } } } }));
  await page.goto('/maintenance');
  await expect(page.getByText('State unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enter maintenance', exact: true })).toBeDisabled();
  broken = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await page.getByLabel('Reason').fill('Operator draft');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByLabel('Reason')).toHaveValue('Operator draft');
});

for (const width of [320, 1920]) {
  test(`all module shells support dark appearance at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width === 320 ? 740 : 1080 });
    await page.addInitScript(() => localStorage.setItem('robotcontrol-appearance', 'dark'));
    await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'viewer-admin', username: 'operator', role: 'admin', session_is_local: true, session: { is_local: true } } } }));
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const route of ['/', '/database', '/database?section=restore', '/database?section=operations', '/scheduling', '/scheduling?section=calendar', '/scheduling?section=history', '/scheduling?section=notifications', '/camera', '/labware', '/labware?section=cytomat', '/maintenance', '/logfile', '/system-status', '/admin', '/admin?section=storage', '/about']) {
      await page.goto(route);
      await expect(page.locator('main')).toBeVisible();
      await expect(page.locator('main h1')).toBeVisible();
      // A fixture error dialog can temporarily hide the shell from the accessibility tree.
      // This assertion measures the underlying layout, not modal interaction.
      const location = page.locator('nav[aria-label="navigation breadcrumbs"]');
      expect((await location.locator('.MuiTypography-root').last().boundingBox())!.width, `${route} location label`).toBeGreaterThan(30);
      await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), route).toBeTruthy();
      await page.screenshot({ path: info.outputPath(`${route.replace(/[^a-z0-9]/gi, '-') || 'dashboard'}.png`), fullPage: true });
    }
    expect(errors).toEqual([]);
  });
}

test('system appearance follows OS changes and login exposes the same preference', async ({ page }) => {
  await page.addInitScript(() => { localStorage.removeItem('access_token'); });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/login');
  await expect(page.getByRole('form', { name: 'Login form' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light');
  await page.getByRole('button', { name: 'Appearance', exact: true }).click();
  await page.getByRole('menuitemradio', { name: 'Dark', exact: true }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark');
});
