import type { Page } from '@playwright/test';

/**
 * Signs the browser in the way the app is signed in: an HttpOnly rc_access cookie. The fixture
 * server (backend/e2e/viewer_server.py) answers as the user the cookie names; specs that fake
 * /api/auth/me themselves only need the cookie for the fixture server's own routes.
 */
export const signIn = (page: Page, user = 'viewer-admin') =>
  page.context().addCookies([{ name: 'rc_access', value: user, domain: '127.0.0.1', path: '/api', httpOnly: true, sameSite: 'Strict' }]);
