# Frontend authentication

Login, registration, password-reset requests, password changes and how tokens reach
every API call. Backend rules are in `docs/maintenance/backend/authentication-maintenance-guide.md`.

## Files

- `context/AuthContext.tsx`: the signed-in `user`, the access token and `login`,
  `register`, `logout`, `changePassword`. `normalizeUser` keeps the server's session
  metadata (`session_is_local`, `session_ip_classification`, `session_client_ip`); use
  those for local-only UI such as Database Restore instead of guessing from login history.
- `services/api.ts`: the Axios client. It adds the `Authorization` header, blocks calls
  during a maintenance window (`MaintenanceManager`), refreshes the token once on a 401,
  and turns a 503 into maintenance mode.
- `pages/LoginPage.tsx`: `login` / `register` / `forgot` modes; switching mode clears
  form errors.
- `components/ChangePasswordDialog.tsx`: opened by App when `user.must_reset`; with
  `requireChange` it cannot be dismissed.

Components call `useAuth()` or the helpers in `services/api.ts`; never call the auth
REST endpoints directly, or token storage and refresh fall out of step.

## Sign-in flow

1. `LoginPage` calls `useAuth().login`, which stores `access_token` and `refresh_token`
   in localStorage and sets `user`; App then renders the signed-in shell.
2. On a 401 the response interceptor calls `/api/auth/refresh` once, stores the new
   token and retries. If refresh fails it removes both tokens and returns to login.
3. Anything that changes the tokens dispatches `ACCESS_TOKEN_UPDATED_EVENT` so other
   tabs pick them up.
4. `logout` clears both tokens and `user`.

Show failures with the shared `StatusDialog` (see the main application guide), using
the server's message; do not swallow `AxiosError`. Password-reset requests send no
email: the page says an administrator will follow up. Change that text if the backend
process changes.

Login uses the same appearance control as the shell, and the choice survives logout.
User and reset-request rows in Administration wrap their actions under long names on
phones. Local administrators find storage previews and repairs at `/admin?section=storage`.

## Troubleshooting

- **Login spins forever:** `/api/auth/me` failed or never returned; check the network tab.
- **Signed out right after login:** the refresh token is missing or rejected, so the
  interceptor removed both tokens; check `/api/auth/refresh` returns `{ data: { access_token } }`.
- **Password dialog will not close:** it is required until the backend clears `must_reset`.
- **Missing role or username:** a backend response changed shape; update `normalizeUser`.
