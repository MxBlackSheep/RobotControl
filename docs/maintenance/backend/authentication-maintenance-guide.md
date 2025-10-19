# Authentication Maintenance Guide

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

- `backend/security/security_manager.py`  
  Optional “extra guard” (rate limits, IP blocking). Currently used selectively; keep it in mind if you add high-risk routes.

- Frontend helpers  
  - `frontend/src/services/api.ts` (`authAPI.*`) – wraps REST calls.  
  - `frontend/src/context/AuthContext.tsx` – stores tokens, exposes `login`, `register`, `logout`, etc. All UI logins go through here.

**Rule of thumb:** Never query the SQLite file directly. Always go through `AuthService` and `AuthDatabase` helpers so password hashing, refresh-token cleanup, and logging stay consistent.

---

## 2. Authentication Lifecycle Cheat Sheet

1. **User submits credentials** (`POST /api/auth/login`).  
   `AuthService.login` verifies the password (bcrypt via `pwd_context`), logs IP/user agent, and returns access + refresh tokens.

2. **Tokens hit the browser.**  
   `AuthContext.login` stores `access_token` and `refresh_token` in `localStorage` so other requests can attach them.

3. **Every API call** runs through `api.interceptors.request` (Axios).  
   It injects `Authorization: Bearer <access_token>` unless maintenance mode blocks the request.

4. **Access token expires?**  
   `api.interceptors.response` detects a 401, calls `/api/auth/refresh`, and—if valid—replays the original request with the new access token.

5. **Refresh token expires or is revoked?**  
   Refresh fails, the interceptor clears both tokens, and the browser redirects to `/login`.

6. **Password reset request** (`POST /api/auth/password-reset/request`).  
   `AuthService.request_password_reset` logs the request in `password_reset_requests` (no email delivered automatically; admins review via `/api/admin/password-reset/*`).

7. **Admin resolves reset** (`POST /api/admin/password-reset/requests/{id}/resolve`).  
   Admin sets a new password (bcrypt hash), optionally requires `must_reset`, and previous refresh tokens are revoked so old sessions die.

---

## 3. Storage, Secrets, and Configuration

- **SQLite schema** (`AuthDatabase._ensure_database`):
  - `users` – stores username, email, bcrypt hash, role (`admin`/`user`), activation flags, last-login metadata.
  - `refresh_tokens` – hashed refresh tokens (`sha256`), issue/expiry timestamps, revocation markers.
  - `password_reset_requests` – audit log for manual reset tickets (status, resolver notes, IP, user agent).

- **Environment variables** (read at import time in `AuthService`):
  - `ROBOTCONTROL_ADMIN_USERNAME`, `ROBOTCONTROL_ADMIN_PASSWORD`, `ROBOTCONTROL_ADMIN_EMAIL` – one-time bootstrap admin.
  - `ROBOTCONTROL_ACCESS_TOKEN_MINUTES` (default 240) & `ROBOTCONTROL_REFRESH_TOKEN_HOURS` (default 168) – expiry windows.
  - `ROBOTCONTROL_ACCESS_TOKEN_SECRET`, `ROBOTCONTROL_REFRESH_TOKEN_SECRET` – must be long random strings; update in tandem.
  - `ROBOTCONTROL_AUTH_DB_FILENAME` – override database filename/location (useful for testing).

- **Hashing + token safety:**  
  Never store raw refresh tokens. `AuthService` hashes them (`sha256`) before persisting. When you add new storage, reuse `_hash_token`.

---

## 4. API & Frontend Touchpoints

- **Login / Register UI**  
  - `frontend/src/pages/LoginPage.tsx` uses `AuthContext.login`.  
  - Registration UI (if enabled) calls `authAPI.register`.

- **Session awareness**  
  - `AuthContext` listens for `ACCESS_TOKEN_UPDATED_EVENT` so any tab stays synced when a token refresh succeeds.
  - `useAuth()` gatekeeps protected pages (e.g., `MonitoringPage` needs `token` before it opens WebSockets).

- **Admin console**  
  - `frontend/src/pages/AdminPage.tsx` hits `adminAPI.getUsers` and password-reset endpoints. They expect `AuthService.get_user_list()` shape.

- **Standardised responses**  
  - Every backend endpoint wraps data using `ResponseFormatter`. If you add new fields, return them inside `data` so the frontend’s `response.data.data || response.data` fallback still works.

---

## 5. Common Maintenance Tasks

| Task | Where | Step-by-step |
|------|-------|--------------|
| Reset bootstrap admin password | `backend/services/auth.py` / ENV vars | Update `ROBOTCONTROL_ADMIN_PASSWORD`, delete `data/robotcontrol_auth.db`, restart backend so `ensure_admin` seeds the new hash. |
| Force-refresh all sessions | `AuthService` | Call `AuthService.db.revoke_tokens_for_user(user_id)` for each user (or wipe `refresh_tokens` table) so everyone signs in again. |
| Add a new admin user | `AuthService.register_user` | Call `register_user`, then `toggle_user_active` or direct SQL to flip role to `admin`. Remember to hash the password through `get_password_hash`. |
| Review password reset tickets | `backend/api/admin.py`, `adminAPI.getPasswordResetRequests` | Use admin UI to see pending requests → resolve with a new password → confirm `must_reset` handshake. |
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

### 6.4 Hook into the security manager
If you wire routes through `SecurityManager`, call `security_manager.validate_request(request, "auth")` at the start of the endpoint. This enforces IP block lists and rate limits from a single place.

---

## 7. Quick Reference

| Function / Method | Purpose | Notes |
|-------------------|---------|-------|
| `AuthService.register_user(username, email, password)` | Create new user | Enforces unique username/email, hashes password before storage. |
| `AuthService.login(username, password, client_info)` | Issue tokens | Returns dict with access/refresh tokens and `user` payload. |
| `AuthService.refresh_access_token(refresh_token)` | Rotate access token | Validates hashed refresh token, returns new access token string. |
| `AuthService.change_password(user, current_password, new_password)` | User-driven password change | Revokes old refresh tokens to kick other sessions. |
| `AuthService.request_password_reset(...)` | Queue manual reset | Logs request for admin follow-up; returns ticket if user exists. |
| `AuthService.get_auth_stats()` | Dashboard numbers | Used by `/api/auth/status` and admin UI. |
| `AuthDatabase.list_users()` | Raw rows | Prefer `AuthService.get_user_list()` which formats data for responses. |

---

## 8. When Something Goes Wrong

1. **“Invalid username or password” even for admin**  
   - Check `data/robotcontrol_auth.db` exists and contains the bootstrap user (`sqlite3 ... "SELECT username FROM users"`).  
   - Confirm env secrets match the ones used when the tokens were issued—changing `ROBOTCONTROL_ACCESS_TOKEN_SECRET` immediately invalidates existing cookies.

2. **Refresh loop / user kicked out repeatedly**  
   - Inspect logs for “Refresh attempt with revoked token.” This usually means duplicate browser tabs fought over tokens. Clearing `refresh_tokens` table fixes the loop.

3. **`sqlalchemy.InterfaceError` or DB file locked**  
   - Windows: make sure no other process has the SQLite file open. The service uses `check_same_thread=False`, so if you see locks it’s almost always external (Explorer preview, antivirus).  
   - As a last resort, stop the backend, remove the DB file, and let it recreate.

4. **Password reset tickets never generate emails**  
   - Intentional: there is no automatic emailer. Admins must poll `/api/admin/password-reset/requests`.  
   - To auto-email, integrate `EmailNotificationService` from `backend/services/notifications.py` and call it inside `request_password_reset`.

5. **JWT verification fails after deployment**  
   - Double-check system clocks (access tokens include `exp`/`iat`).  
   - Ensure new environment sets both `ROBOTCONTROL_ACCESS_TOKEN_SECRET` and `ROBOTCONTROL_REFRESH_TOKEN_SECRET`; mismatched secrets break verification.

Stay methodical: keep changes inside the service layer, respect hashing/token helpers, and always update both backend and frontend when you add or rename fields.

