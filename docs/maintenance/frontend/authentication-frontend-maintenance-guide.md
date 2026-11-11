# Frontend authentication

Login, registration, password-reset requests, password changes and how the sign-in reaches
every API call. Backend rules are in `docs/maintenance/backend/authentication-maintenance-guide.md`.

## Files

- `context/AuthContext.tsx`: the signed-in `user` and `login`, `register`, `logout`,
  `changePassword`. Page code holds no token. `normalizeUser` keeps the server's session
  metadata (`session_is_local`, `session_ip_classification`, `session_client_ip`); use
  those for local-only UI such as Database Restore instead of guessing from login history.
- `services/api.ts`: the Axios client. Every request carries `X-Requested-With: RobotControl`
  (the server refuses a cookie-signed change without it). It blocks calls during a
  maintenance window (`MaintenanceManager`) and renews the sign-in once on a 401.
  A 503 is left to the page that made the request; only a successful restore starts
  maintenance. A timeout keeps the Axios error (`config`, `code`) with the message
  "Request timed out".
- `pages/LoginPage.tsx`: `login` / `register` / `forgot` modes; switching mode clears
  form errors.
- `components/ChangePasswordDialog.tsx`: opened by App when `user.must_reset`; with
  `requireChange` it cannot be dismissed.

Components call `useAuth()` or the helpers in `services/api.ts`; never call the auth
REST endpoints directly, or the request header and refresh fall out of step.

## Sign-in flow

1. `LoginPage` calls `useAuth().login`. The server sets two HttpOnly cookies, `rc_access`
   and `rc_refresh`, which page scripts cannot read; the reply carries only the user and
   session, and `login` sets `user`. App then renders the signed-in shell. `register` uses
   the same step.
2. On a 401 the response interceptor posts `/api/auth/refresh` (no body) once for all
   callers (`attemptTokenRefresh`: true, false, or an outage that rejects) and retries the
   request. A refresh rejected by RobotControl (401/403 with its JSON body,
   `isSignInRejected` in `services/requestError.ts`) returns to login; the server clears the
   cookies. Network errors, timeouts, server errors and proxy pages (a Cloudflare HTML 403
   challenge or 52x) keep the sign-in. A 401 from `/api/auth/me` does not redirect:
   AuthContext shows the sign-in page itself.
3. The recording download (`hooks/useRecordingDownload.ts`) uses `fetch`; the cookie goes
   with it, and a 401 calls `attemptTokenRefresh` once.
4. `logout` clears `user` at once. After any refresh in flight has settled it posts
   `/api/auth/logout`, which revokes the refresh token and clears both cookies, so a late
   refresh reply cannot sign the browser in again. A sign-in right after waits for that post.
   Sign out in one tab signs out the others on their next request.

`signInChanged` / `currentSignIn` (`services/api.ts`) change on every sign-in and sign-out;
cached reads key on them so one person's read is never served to the next. At start the app
removes the `access_token` and `refresh_token` that older builds kept in localStorage.

On page load, `/api/auth/me` verifies the sign-in before App renders protected
content. While the server is unavailable, App shows a connection message and retries
after five seconds; each request still has a ten-second timeout. This request bypasses
maintenance suppression so recovery can complete, and its 503 does not start the
maintenance window, which would block the recovered page. A RobotControl 401/403 rejects
the sign-in; temporary failures and proxy pages do not sign anyone out. `/me` also returns the
stored `must_reset`, so a reload keeps the required password change. `LoginPage` shows the
server's message, else a connection message ("Can't reach RobotControl…", "The connection to
RobotControl was interrupted (502)…") titled "Connection problem"; "Invalid username or
password" only comes from RobotControl's 401. Remote sign-ins are throttled (429 with the
wait, see `docs/maintenance/backend/remote-access-guide.md`). Effect cleanup ignores late responses and
cancels the retry timer. Browser checks: `frontend/e2e/auth-recovery.spec.ts`.

Show failures with the shared `StatusDialog` (see the main application guide), using
the server's message; do not swallow `AxiosError`. Password-reset requests send no
email: the page says an administrator will follow up. Change that text if the backend
process changes.

Login uses the same appearance control as the shell, and the choice survives logout.
User and reset-request rows in Administration wrap their actions under long names on
phones. Local administrators find storage previews and repairs at `/admin?section=storage`.
A user with `review_reason` cannot sign in: its row shows the Needs review chip (Role column, or
beside the actions on narrow cards) and the reason under the user name (`ReviewReason`). Reset & Resolve on that user's reset request, Edit email or Delete clears it.

## Troubleshooting

- **Login spins forever:** `/api/auth/me` failed or never returned; check the network tab.
- **Signed out right after login, or after every reload:** the browser did not keep the
  cookies. Check the login reply's `Set-Cookie` in the network tab: over plain http it must not
  carry `Secure`, and through the tunnel the page and API must share one hostname. Private
  browsing or blocked cookies also lose the sign-in on reload.
- **403 "Missing request header":** a change was sent without `X-Requested-With: RobotControl`;
  send it through `api` in `services/api.ts`.
- **Password dialog will not close:** it is required until the backend clears `must_reset`.
- **Missing role or username:** a backend response changed shape; update `normalizeUser`.
