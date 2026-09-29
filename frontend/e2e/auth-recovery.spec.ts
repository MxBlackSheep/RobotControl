import { test, expect } from '@playwright/test';

/** Failure cases: temporary /me or refresh failures discard saved credentials or
 * grant access without verification; reconnect never retries; rejected credentials
 * remain saved; expired access cannot refresh after an outage; a reload loses the
 * destination; a late refresh reinstates credentials after logout. Synthetic HTTP fixtures exercise the real app and Axios interceptors.
 */
for (const failure of ['network', 'server', 'timeout', 'refresh'] as const) {
  test(`saved sign-in recovers after ${failure} failure`, async ({ page }, testInfo) => {
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'saved-access');
      localStorage.setItem('refresh_token', 'saved-refresh');
    });
    let available = false;
    let failed = false;
    await page.route('**/api/auth/me', async route => {
      if (failure === 'refresh' && route.request().headers().authorization !== 'Bearer renewed-access') {
        return route.fulfill({ status: 401, json: { detail: 'Expired' } });
      }
      if (!available) {
        if (failure === 'network') { failed = true; return route.abort('connectionrefused'); }
        if (failure === 'timeout') {
          await new Promise(resolve => setTimeout(resolve, 10_500));
          failed = true;
          return route.abort();
        }
        failed = true;
        return route.fulfill({ status: 503, json: { detail: 'Restarting' } });
      }
      return route.fulfill({ json: { success: true, data: { user_id: 'fixture', username: 'Recovered user', role: 'admin' } } });
    });
    await page.route('**/api/auth/refresh', route => {
      if (!available) {
        failed = true;
        return route.fulfill({ status: 503, json: { detail: 'Restarting' } });
      }
      return route.fulfill({ json: { success: true, data: { access_token: 'renewed-access' } } });
    });
    await page.goto('/database?section=restore');
    await expect.poll(() => failed, { timeout: 15_000 }).toBe(true);
    await expect(page.getByText('Connecting to the server.', { exact: false })).toBeVisible();
    expect(await page.evaluate(() => [localStorage.getItem('access_token'), localStorage.getItem('refresh_token')]))
      .toEqual(['saved-access', 'saved-refresh']);
    await expect(page.getByRole('main')).toHaveCount(0);
    available = true;
    await expect(page.getByRole('button', { name: 'Account menu' })).toContainText('Recovered user', { timeout: 10_000 });
    expect(page.url()).toContain('/database?section=restore');
    expect(await page.evaluate(() => localStorage.getItem('refresh_token'))).toBe('saved-refresh');
    await page.screenshot({ path: testInfo.outputPath(`recovered-${failure}.png`) });
  });
}

for (const rejection of [401, 403]) {
  test(`rejected refresh (${rejection}) removes credentials`, async ({ page }, testInfo) => {
    await page.addInitScript(() => {
      // Do not re-seed credentials on the redirect to /login.
      if (!sessionStorage.getItem('seeded')) {
        localStorage.setItem('access_token', 'expired');
        localStorage.setItem('refresh_token', 'rejected');
        sessionStorage.setItem('seeded', 'yes');
      }
    });
    await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Expired' } }));
    await page.route('**/api/auth/refresh', route => route.fulfill({ status: rejection, json: { detail: 'Rejected' } }));
    await page.goto('/database?section=restore');
    await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => [localStorage.getItem('access_token'), localStorage.getItem('refresh_token')])).toEqual([null, null]);
    await expect(page.getByRole('button', { name: 'Account menu' })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`rejected-${rejection}.png`) });
  });
}


test('a late refresh cannot restore credentials after logout', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'saved-access');
    localStorage.setItem('refresh_token', 'saved-refresh');
  });
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'fixture', username: 'Fixture', role: 'admin' } } }));
  await page.route('**/api/admin/backup/list', route => route.fulfill({ status: 401, json: { detail: 'Expired' } }));
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let refreshing = false;
  await page.route('**/api/auth/refresh', async route => {
    refreshing = true;
    await pending;
    await route.fulfill({ json: { success: true, data: { access_token: 'late-token' } } });
  });
  await page.goto('/database?section=restore');
  await expect.poll(() => refreshing).toBe(true);
  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  release();
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => [localStorage.getItem('access_token'), localStorage.getItem('refresh_token')])).toEqual([null, null]);
  await page.screenshot({ path: testInfo.outputPath('logout-during-refresh.png') });
});
