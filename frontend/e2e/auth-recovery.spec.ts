import { test, expect } from '@playwright/test';

/** Failure cases: temporary /me or refresh failures discard saved credentials or
 * grant access without verification; reconnect never retries; rejected credentials
 * remain saved; expired access cannot refresh after an outage; a reload loses the
 * destination; a late refresh reinstates credentials after logout; a 503 from /me
 * starts the maintenance window and blocks the recovered page; a tunnel's HTML 403
 * challenge page signs the user out; sign-in reports an unreachable server or tunnel
 * error page as a wrong password; the sign-in page prints the default admin credentials;
 * a refused remote default-password sign-in (403) is shown as a connection problem or wrong
 * password instead of RobotControl's message; a local default-password sign-in (must_reset)
 * does not open the required password change. Backend side: backend/e2e/auth_storage_check.py.
 * Synthetic HTTP fixtures exercise the real app and Axios interceptors.
 */
for (const failure of ['network', 'server', 'timeout', 'refresh', 'proxy'] as const) {
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
        if (failure === 'proxy') {
          failed = true;
          return route.fulfill({ status: 403, contentType: 'text/html', body: '<html><title>Just a moment...</title></html>' });
        }
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
    await expect(page.getByRole('dialog', { name: 'Database Maintenance In Progress' })).toHaveCount(0);
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


test('sign-in tells an unreachable server from a wrong password', async ({ page }, testInfo) => {
  let answer: 'tunnel' | 'refused' | 'wrong' | 'default-remote' | 'default-local' = 'tunnel';
  const defaultRemote = 'Change the default password on the robot PC before signing in remotely.';
  await page.route('**/api/auth/login', route => {
    if (answer === 'refused') return route.abort('connectionrefused');
    if (answer === 'tunnel') return route.fulfill({ status: 502, contentType: 'text/html', body: '<html>Bad gateway</html>' });
    if (answer === 'default-remote') {
      return route.fulfill({ status: 403, json: { success: false, message: defaultRemote, data: null, error: { message: defaultRemote, code: 'DEFAULT_PASSWORD_REMOTE' } } });
    }
    if (answer === 'default-local') {
      return route.fulfill({ json: { success: true, data: {
        access_token: 'viewer-admin', refresh_token: 'viewer-refresh', token_type: 'bearer', expires_in: 14400,
        user: { user_id: 'viewer-admin', username: 'admin', role: 'admin', is_active: true, must_reset: true },
        session: { is_local: true, ip_classification: 'local' },
      } } });
    }
    return route.fulfill({ status: 401, json: { success: false, error: { message: 'Invalid username or password', code: 'UNAUTHORIZED' } } });
  });
  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/Default admin|ShouGroupAdmin/);
  await page.getByLabel('Username', { exact: true }).fill('operator');
  await page.getByLabel('Password', { exact: true }).fill('secret');
  const submit = page.getByRole('button', { name: 'Sign in' });
  const dialog = page.getByRole('dialog');
  await submit.click();
  await expect(dialog.getByRole('heading', { name: 'Connection problem' })).toBeVisible();
  await expect(dialog).toContainText('The connection to RobotControl was interrupted (502)');
  await page.screenshot({ path: testInfo.outputPath('sign-in-tunnel-error.png') });
  await dialog.getByRole('button', { name: 'Close' }).click();
  answer = 'refused';
  await submit.click();
  await expect(dialog).toContainText("Can't reach RobotControl");
  await expect(dialog).not.toContainText('Invalid username or password');
  await dialog.getByRole('button', { name: 'Close' }).click();
  answer = 'wrong';
  await submit.click();
  await expect(dialog.getByRole('heading', { name: 'Authentication Required' })).toBeVisible();
  await expect(dialog).toContainText('Invalid username or password');
  await dialog.getByRole('button', { name: 'Close' }).click();
  answer = 'default-remote';
  await submit.click();
  await expect(dialog.getByRole('heading', { name: 'Authentication Required' })).toBeVisible();
  await expect(dialog).toContainText(defaultRemote);
  await expect(dialog).not.toContainText('Invalid username or password');
  await page.screenshot({ path: testInfo.outputPath('sign-in-default-password-remote.png'), animations: 'disabled' });
  expect(await page.evaluate(() => localStorage.getItem('access_token'))).toBeNull();
  await dialog.getByRole('button', { name: 'Close' }).click();
  answer = 'default-local';
  await submit.click();
  const change = page.getByRole('dialog', { name: 'Password Reset Required' });
  await expect(change).toBeVisible();
  await expect(change.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath('sign-in-default-password-local.png') });
});

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
