import { test, expect } from '@playwright/test';

/** Failure cases: temporary /me or refresh failures sign the person out or grant access
 * without verification; reconnect never retries; a rejected refresh leaves the app signed in;
 * expired access cannot refresh after an outage; a reload loses the destination; the page keeps
 * a token where scripts can read it (localStorage or a reply body) or leaves the old stored
 * tokens behind; a refresh or other change is sent without X-Requested-With: RobotControl or
 * with a token in its body; Sign out never reaches the server, or reaches it while a refresh is
 * still in flight (the late refresh would sign the browser in again) or is held by the restore pause; a 503 from /me starts the
 * maintenance window and blocks the recovered page; a tunnel's HTML 403 challenge page signs the
 * user out; sign-in reports an unreachable server or tunnel error page as a wrong password; the
 * sign-in page prints the default admin credentials; a refused remote default-password sign-in
 * (403) is shown as a connection problem or wrong password instead of RobotControl's message; a
 * local default-password sign-in (must_reset) does not open the required password change; the
 * page's delayed Username focus takes focus from Password chosen right after the page opens
 * (typing lands in Username; seen as a flaky run).
 * Backend side (cookies, the header rule, logout, must_reset on /me): backend/e2e/auth_storage_check.py.
 * Synthetic HTTP fixtures exercise the real app and Axios interceptors; the faked routes stand
 * for the server, so the cookies themselves are checked there.
 */
for (const failure of ['network', 'server', 'timeout', 'refresh', 'proxy'] as const) {
  test(`saved sign-in recovers after ${failure} failure`, async ({ page }, testInfo) => {
    // Tokens an older build stored: the app removes them at start.
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'old-access');
      localStorage.setItem('refresh_token', 'old-refresh');
    });
    let available = false;
    let failed = false;
    let renewed = false;
    const signOuts: string[] = [];
    const refreshes: { body: string | null; header: string | undefined }[] = [];
    page.on('request', request => { if (request.url().includes('/api/auth/logout')) signOuts.push(request.url()); });
    await page.route('**/api/auth/me', async route => {
      if (failure === 'refresh' && !renewed) {
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
      refreshes.push({ body: route.request().postData(), header: route.request().headers()['x-requested-with'] });
      if (!available) {
        failed = true;
        return route.fulfill({ status: 503, json: { detail: 'Restarting' } });
      }
      renewed = true;
      return route.fulfill({ json: { success: true, data: {} } });
    });
    await page.goto('/database?section=restore');
    await expect.poll(() => failed, { timeout: 15_000 }).toBe(true);
    await expect(page.getByText('Connecting to the server.', { exact: false })).toBeVisible();
    await expect(page.getByRole('main')).toHaveCount(0);
    available = true;
    await expect(page.getByRole('button', { name: 'Account menu' })).toContainText('Recovered user', { timeout: 10_000 });
    expect(page.url()).toContain('/database?section=restore');
    await expect(page.getByRole('dialog', { name: 'Database Maintenance In Progress' })).toHaveCount(0);
    expect(signOuts).toEqual([]);
    expect(await page.evaluate(() => [localStorage.getItem('access_token'), localStorage.getItem('refresh_token')])).toEqual([null, null]);
    if (failure === 'refresh') expect(refreshes.at(-1)).toEqual({ body: null, header: 'RobotControl' });
    await page.screenshot({ path: testInfo.outputPath(`recovered-${failure}.png`) });
  });
}

for (const rejection of [401, 403]) {
  test(`rejected refresh (${rejection}) shows the sign-in page`, async ({ page }, testInfo) => {
    let refreshes = 0;
    await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Expired' } }));
    await page.route('**/api/auth/refresh', route => { refreshes++; return route.fulfill({ status: rejection, json: { detail: 'Rejected' } }); });
    await page.goto('/database?section=restore');
    await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Account menu' })).toHaveCount(0);
    // One try, and no reload loop on the sign-in page.
    await page.waitForTimeout(500);
    expect(refreshes).toBe(1);
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
        expires_in: 14400,
        user: { user_id: 'viewer-admin', username: 'admin', role: 'admin', is_active: true, must_reset: true },
        session: { is_local: true, ip_classification: 'local' },
      } } });
    }
    return route.fulfill({ status: 401, json: { success: false, error: { message: 'Invalid username or password', code: 'UNAUTHORIZED' } } });
  });
  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/Default admin|ShouGroupAdmin/);
  // Choosing Password straight away (a quick tap, or password autofill) must keep focus there:
  // the page's delayed Username focus used to move the typing into Username.
  await page.getByLabel('Password', { exact: true }).focus();
  await page.waitForTimeout(300);
  await expect(page.getByLabel('Password', { exact: true })).toBeFocused();
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
  expect(await page.evaluate(() => [localStorage.getItem('access_token'), localStorage.getItem('refresh_token')])).toEqual([null, null]);
});

test('Sign out waits for a refresh in flight, then ends the sign-in on the server', async ({ page }, testInfo) => {
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'fixture', username: 'Fixture', role: 'admin' } } }));
  let expired = true;
  await page.route('**/api/admin/backup/list', route => {
    if (!expired) return route.fulfill({ json: { success: true, data: [] } });
    expired = false;
    return route.fulfill({ status: 401, json: { detail: 'Expired' } });
  });
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let refreshing = false;
  const events: string[] = [];
  await page.route('**/api/auth/refresh', async route => {
    refreshing = true;
    await pending;
    events.push('refresh answered');
    await route.fulfill({ json: { success: true, data: {} } });
  });
  await page.route('**/api/auth/logout', route => {
    events.push(`logout ${route.request().method()} ${route.request().headers()['x-requested-with']}`);
    return route.fulfill({ json: { success: true, data: {} } });
  });
  await page.goto('/database?section=restore');
  await expect.poll(() => refreshing).toBe(true);
  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  await page.waitForTimeout(300);
  expect(events).toEqual([]);
  release();
  await expect.poll(() => events).toEqual(['refresh answered', 'logout POST RobotControl']);
  await page.screenshot({ path: testInfo.outputPath('logout-during-refresh.png') });
});

test('Sign out during the restore pause still ends the sign-in on the server', async ({ page }) => {
  const backup = { filename: 'EvoYeast_20260101_120000.bak', file_size: 2048, file_size_formatted: '2 KB', created_date: '2026-01-01T12:00:00', is_valid: true };
  await page.route('**/api/auth/me', route => route.fulfill({ json: { success: true, data: { user_id: 'fixture', username: 'Fixture', role: 'admin', session: { is_local: true } } } }));
  await page.route('**/api/admin/backup/list', route => route.fulfill({ json: { success: true, data: [backup] } }));
  await page.route('**/api/admin/backup/restore', route => route.fulfill({ json: { success: true, message: 'Database restored successfully', data: { warnings: [] } } }));
  // The server is still restarting, so the pause holds.
  await page.route('**/health', route => route.fulfill({ status: 503, json: {} }));
  const signOuts: string[] = [];
  await page.route('**/api/auth/logout', route => { signOuts.push(route.request().method()); return route.fulfill({ json: { success: true, data: {} } }); });
  await page.goto('/database?section=restore');
  await page.getByRole('main').getByRole('combobox').click();
  await page.getByRole('option', { name: backup.filename, exact: false }).click();
  await page.getByRole('button', { name: 'Restore Database', exact: true }).click();
  const confirm = page.getByRole('dialog').filter({ hasText: 'Confirmation Required' });
  await confirm.getByRole('checkbox').nth(0).check();
  await confirm.getByRole('checkbox').nth(1).check();
  await confirm.getByRole('button', { name: 'Restore Database', exact: true }).click();
  await page.getByRole('dialog', { name: 'Restore Completed' }).getByRole('button', { name: 'Close' }).click();
  await page.getByRole('button', { name: 'Got it' }).click();
  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  await expect.poll(() => signOuts).toEqual(['POST']);
});
