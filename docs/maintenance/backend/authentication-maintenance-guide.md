# Authentication Maintenance Guide

## SQLite relationship enforcement (2026-09-14)

Each authentication connection enables foreign keys and uses a two-second lock timeout. Deleting a user removes refresh tokens and clears the user link in retained password-reset history. Existing dangling links require local administrator preview and repair with a verified backup. See the [SQLite safety guide](sqlite-safety-maintenance-guide.md); never log password hashes or refresh-token contents in diagnostics.

## uv setup and verification

Python dependencies now come from the root uv project. Keep bcrypt pinned at 4.3.0 to preserve existing hashes and password handling, including passwords over 72 UTF-8 bytes. Run `uv run --locked python -m pytest backend/tests/test_auth.py` to check login, password changes, refresh tokens, and reopening an existing password database. Test fixtures reset both service and database singletons and use temporary SQLite files.

This guide walks through the authentication stack so you always know **which file to touch and why**. Follow the steps exactly—even if they feel obvious—so we don't break logins for the lab.

---

## 1. High-Level Architecture

- `backend/services/auth.py`  
  Central `AuthService`. Handles user creation, password hashing, JWT issuance, refresh-token storage, and password reset workflow.

- `backend/services/auth_database.py`  
  SQLite layer (`AuthDatabase`). Creates the tables, wraps CRUD operations, and enforces constraints like unique usernames/emails.

- `backend/api/auth.py`  
  FastAPI routes (`/api/auth/*`). Validates payloads, formats responses, and plugs into the `AuthService`.

- `backend/api/admin.py` (`password_reset_*`, `users` routes)  
  Admin-only endpoints for resolving reset requests, toggling users, and updating emails.

- Frontend helpers  
  - `frontend/src/services/api.ts` (`authAPI.*`) – wraps REST calls.  
  - `frontend/src/context/AuthContext.tsx` – holds the signed-in user (never a token), exposes `login`, `register`, `logout`, etc. All UI logins go through here.

**Rule of thumb:** Never query the SQLite file directly. Always go through `AuthService` and `AuthDatabase` helpers so password hashing, refresh-token cleanup, and logging stay consistent.

---

## 2. Authentication Lifecycle Cheat Sheet

1. **User submits credentials** (`POST /api/auth/login`).  
   `AuthService.login` verifies the password through `verify_password` using `bcrypt.checkpw`, logs IP/user agent, and returns access + refresh tokens. The route puts them into cookies (`signed_in_reply` in `backend/api/auth.py`) and removes them from the body; register does the same.
   **Built-in default password.** `BUILT_IN_ADMIN_PASSWORD` (`backend/services/auth.py`) is public in the repository. A sign-in with it that is not local (tunnel, LAN; rule in `get_connection_context`, see the [remote access guide](remote-access-guide.md)) answers 403 "Change the default password on the workstation before signing in remotely." and issues no tokens. The route checks this at sign-in (`AuthService.has_built_in_password`: the submitted password equals the built-in one *and* verifies against the account's hash), so nothing is stored and the rule ends as soon as the password changes. It applies to any account carrying that password, is checked only after the throttle, is not counted as a failed attempt, and never runs for a wrong password, which keeps the generic 401 (no hint whether the default is in use). A local sign-in with it succeeds with `user.must_reset: true` in the response, so the app opens the required change-password dialog. A deployment that set its own `ROBOTCONTROL_ADMIN_PASSWORD` is not affected. Check: `backend/e2e/auth_storage_check.py`.

2. **Tokens hit the browser as cookies.**  
   `set_sign_in_cookies` (`backend/services/auth.py`) sets `rc_access` (Path `/api`, Max-Age = access lifetime) and `rc_refresh` (Path `/api/auth`, Max-Age = refresh lifetime), both `HttpOnly; SameSite=Strict`, no Domain. `Secure` is added only when the request came over HTTPS (`x-forwarded-proto: https` from the tunnel); the lab PC opens plain `http://localhost:8005`, where a Secure cookie would not be kept. Page scripts never see a token.

3. **Every API call** carries the sign-in.
   `request_token` (`backend/services/auth.py`, the one owner) takes a `Authorization: Bearer` header when present (programs such as the checks in `backend/e2e`), else the `rc_access` cookie, else 401. Programs sign in like the page: they post login with `X-Requested-With: RobotControl` and take the token from the `rc_access` Set-Cookie (`packaged_app.sign_in`). **Request-header rule** (`require_request_header` in `backend/main.py`): a POST, PUT, PATCH or DELETE to `/api/` without a Bearer header must carry `X-Requested-With: RobotControl`, else 403 `{"detail": "Missing request header"}`. Another site cannot add that header without CORS approval, and CORS allows only `http://localhost:8005`, `http://127.0.0.1:8005` and the Vite ports `3005`.

4. **Access token expires?**  
   The frontend gets a 401 and posts `/api/auth/refresh` with no body. The route reads `rc_refresh` and sets a new `rc_access`; the reply is `{success, data: {}}`. A rejection (401) clears both cookies; a storage outage (503) keeps them.

5. **Refresh token expires or is revoked?**  
   Refresh fails, the cookies are cleared, and the browser returns to `/login`.

5a. **Sign out** (`POST /api/auth/logout`, no sign-in needed).
   Revokes the refresh token from the cookie if present, clears both cookies and always answers 200. Other tabs of that browser are signed out on their next request. The refresh token ends at once; an access token already copied stays valid until it expires (access lifetime, 4 hours by default), because access tokens are not stored.

6. **Password reset request** (`POST /api/auth/password-reset/request`).  
   `AuthService.request_password_reset` logs the request in `password_reset_requests` (no email delivered automatically; admins review via `/api/admin/password-reset/*`).

7. **Admin resolves reset** (`POST /api/admin/password-reset/requests/{id}/resolve`).  
   Admin sets a new password (bcrypt hash), optionally requires `must_reset`, and previous refresh tokens are revoked so old sessions die.

8. **User under review.** `check_user` (`backend/services/auth.py`) checks two stored fields, each fixed by an existing action: a bcrypt hash (reset password) and an email containing "@" (Edit email) (only that: the built-in `admin@localhost` must pass; the register and email forms keep their stricter rule). Register and the email change call it, and so does the bootstrap admin, but only when that row is about to be written (a later bad `ROBOTCONTROL_ADMIN_EMAIL` never stops an existing installation; a fresh one refuses with "ROBOTCONTROL_ADMIN_EMAIL has no "@""). User name and role are owned by the routes and the SQL constraint; `_row_to_user` derives `review_reason` from it on every read, so nothing is stored. `authenticate_user`, `verify_token` and `refresh_access_token` refuse a user under review with the usual 401; `request_password_reset` accepts one. The Admin user list returns `review_reason`. The way out is the admin's reset password, Edit email or Delete. Check: `backend/e2e/stored_data_check.py`, which also proves every user of a copy of an installed sign-in database passes.

---

## 3. Storage, Secrets, and Configuration

- **SQLite schema** (`AuthDatabase._ensure_database`):
  - `users` – stores username, email, bcrypt hash, role (`admin`/`user`), activation flags, last-login metadata.
  - `refresh_tokens` – hashed refresh tokens (`sha256`), issue/expiry timestamps, revocation markers.
  - `password_reset_requests` – audit log for manual reset tickets (status, resolver notes, IP, user agent).

- **Environment variables** (read at import time in `AuthService`):
  - `ROBOTCONTROL_ADMIN_USERNAME`, `ROBOTCONTROL_ADMIN_PASSWORD`, `ROBOTCONTROL_ADMIN_EMAIL` – one-time bootstrap admin. Without `ROBOTCONTROL_ADMIN_PASSWORD` the admin gets `BUILT_IN_ADMIN_PASSWORD`, which works only on the RobotControl computer until changed (Admin → User accounts, or the account menu's Change password).
  - `ROBOTCONTROL_ACCESS_TOKEN_MINUTES` (default 240) & `ROBOTCONTROL_REFRESH_TOKEN_HOURS` (default 168) – expiry windows.
  - `ROBOTCONTROL_ACCESS_TOKEN_SECRET`, `ROBOTCONTROL_REFRESH_TOKEN_SECRET` – optional; used only when both are set (long random strings).

- **Signing keys** (`token_secrets()` in `backend/services/auth.py`): without both variables, the keys live in `data/config/token-secrets.json`, created with two random keys at first start and reused after every restart and upgrade. The source holds no key. A key file that cannot be read stops start-up with a log line naming the file; it is never rewritten. Deleting the file signs everyone out and nothing else; never copy it to another PC. Check: `backend/e2e/auth_storage_check.py` (a token signed with the old published key answers 401; a restart keeps sessions).
  - `ROBOTCONTROL_AUTH_DB_FILENAME` – override database filename/location (useful for testing).

- **Hashing + token safety:**  
  Never store raw refresh tokens. `AuthService` hashes them (`sha256`) before persisting. When you add new storage, reuse `_hash_token`.

---

## 4. API & Frontend Touchpoints

- **Login / Register UI**  
  - `frontend/src/pages/LoginPage.tsx` uses `AuthContext.login`.  
  - Registration UI (if enabled) calls `authAPI.register`.

- **Session awareness**  
  - `AuthContext` asks `/api/auth/me` on every page load; the cookies themselves are invisible to page code.
  - `useAuth()` gatekeeps protected pages (e.g., monitoring polls only while `user` is set).

- **Admin console**  
  - `frontend/src/pages/AdminPage.tsx` hits `adminAPI.getUsers` and password-reset endpoints. They expect `AuthService.get_user_list()` shape.

- **Standardised responses**  
  - Every backend endpoint wraps data using `ResponseFormatter`. If you add new fields, return them inside `data`; `AuthContext` reads `response.data.data`.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Reset bootstrap admin password | `backend/services/auth.py` / ENV vars | Update `ROBOTCONTROL_ADMIN_PASSWORD`, delete `data/robotcontrol_auth.db`, restart backend so `ensure_admin` seeds the new hash. |
| Force-refresh all sessions | `AuthService` | Call `AuthService.db.revoke_tokens_for_user(user_id)` for each user (or wipe `refresh_tokens` table) so everyone signs in again. |
| Add a user | `AuthService.register_user` | Call `register_user` with username, email and password; it hashes the password through `get_password_hash` and creates a user with role `user`. |
| Review password reset tickets | `backend/api/admin.py`, `adminAPI.getPasswordResetRequests` | Use admin UI to see pending requests → resolve with a new password → confirm `must_reset` handshake. |
| Role | `PUT /api/admin/users/{username}/role` (`backend/api/admin.py`), `AuthDatabase.set_user_role` | Body `{"role": "user"}` or `{"role": "admin"}`, admin only, local or remote. It applies on the account's next request: `verify_token` and the admin check read the role from the database, so nobody signs in again. Refusals: 403 "You are no longer an admin. Reload the page" for a caller who is not an admin (`get_current_admin_for_account_change`; also on delete, while every other admin route says "Admin access required"), 404 unknown user, 400 "Cannot change your own role". The UPDATE (and the DELETE of `delete_user`) is saved only while the maker is still an active admin, checked in the same statement, so two admins changing each other at once always leave one admin who can sign in. Every change and refusal is logged with `log_action(action="change_user_role")`. Check: `backend/e2e/auth_storage_check.py`. |
| Move auth DB location | `ROBOTCONTROL_AUTH_DB_FILENAME` | Set env var to desired filename (absolute or relative). Ensure containing folder exists; restart backend to create schema. |

---

## 6. Extending or Modifying Behaviour

### 6.1 Add a new user attribute (e.g., phone number)
1. Extend `users` table: add column in `AuthDatabase._ensure_database`. Use `ALTER TABLE` if the column is missing.
2. Update `_row_to_user` and `User.to_dict` so new field flows through API responses.
3. Accept the field in relevant endpoints (`RegisterRequest`, admin update routes).
4. Thread it into `AuthContext.normalizeUser` so the frontend stays in sync.

### 6.2 Enforce stronger passwords
1. Update validation in `RegisterRequest` / `ChangePasswordRequest` schemas (_more min length, regex, etc_).  
2. Add extra checks inside `AuthService.register_user` and `change_password` so the backend rejects weak passwords even if the frontend forgets.

### 6.3 Shorten token lifetime (e.g., production hardening)
1. Change `ROBOTCONTROL_ACCESS_TOKEN_MINUTES` / `ROBOTCONTROL_REFRESH_TOKEN_HOURS`.  
2. Restart backend.  
3. Tell the team: shorter windows mean more frequent refreshes—warn about UI prompts.

---

## 7. Quick Reference

| Function / Method | Purpose | Notes |
|-------------------|---------|-------|
| `AuthService.register_user(username, email, password)` | Create new user | Enforces unique username/email, hashes password before storage. |
| `AuthService.login(username, password, client_info)` | Issue tokens | Returns dict with access/refresh tokens and `user` payload. |
| `AuthService.refresh_access_token(refresh_token)` | Rotate access token | Validates hashed refresh token, returns new access token string. |
| `AuthService.change_password(user, current_password, new_password)` | User-driven password change | Revokes old refresh tokens to kick other sessions. |
| `AuthService.request_password_reset(...)` | Queue manual reset | Logs request for admin follow-up; returns ticket if user exists. |
| `get_auth_service()` | Shared sign-in owner | Authentication and admin routes use the same service. |
| `AuthDatabase.list_users()` | Raw rows | Prefer `AuthService.get_user_list()` which formats data for responses. |

---

## 8. When Something Goes Wrong

1. **“Invalid username or password” even for admin**  
   - Check `data/robotcontrol_auth.db` exists and contains the bootstrap user (`sqlite3 ... "SELECT username FROM users"`).  
   - Changing the signing keys (the key variables or `data/config/token-secrets.json`) signs everyone out; they sign in again.

2. **"Change the default password on the workstation before signing in remotely."**  
   - The account still has the built-in password. Sign in on the RobotControl computer itself (`http://localhost:8005`), set a new password in the dialog that opens, then sign in remotely with it.

3. **Refresh loop / user kicked out repeatedly**  
   - Inspect logs for “Refresh attempt with revoked token.” This usually means duplicate browser tabs fought over tokens. Clearing `refresh_tokens` table fixes the loop.

4. **`sqlalchemy.InterfaceError` or DB file locked**  
   - A storage error while checking a token (`sqlite3.Error`, `StorageUnavailable`; listed in `AUTH_STORAGE_ERRORS`) answers 503, never 401, so browsers keep their sign-in and retry. Only a bad, expired, wrong-type or revoked token answers 401. Check: `.venv/Scripts/python.exe -m backend.e2e.auth_storage_check`.  
   - Windows: make sure no other process has the SQLite file open. The service uses `check_same_thread=False`, so if you see locks it’s almost always external (Explorer preview, antivirus).  
   - As a last resort, stop the backend, remove the DB file, and let it recreate.

5. **Password reset tickets never generate emails**  
   - Intentional: there is no automatic emailer. Admins must poll `/api/admin/password-reset/requests`.  
   - To auto-email, integrate `EmailNotificationService` from `backend/services/notifications.py` and call it inside `request_password_reset`.

6. **JWT verification fails after deployment**  
   - Double-check system clocks (access tokens include `exp`/`iat`).  
   - A new PC creates its own `data/config/token-secrets.json`; earlier sign-ins end there, which is expected.

Stay methodical: keep changes inside the service layer, respect hashing/token helpers, and always update both backend and frontend when you add or rename fields.

