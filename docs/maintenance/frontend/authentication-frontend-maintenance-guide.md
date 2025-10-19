# Frontend Authentication Maintenance Guide

Read this before you touch anything related to login, registration, or password changes. It explains exactly which React files are involved, how tokens flow, and what breaks if you skip a step. Assume nothing—follow the checklist literally.

---

## 1. High-Level Architecture

- `frontend/src/context/AuthContext.tsx`  
  Wraps the entire app. Stores the currently signed-in user, access token, and exposes helpers (`login`, `register`, `logout`, `changePassword`). Also listens for token refresh events.

- `frontend/src/services/api.ts`  
  Axios instance with interceptors. Adds the `Authorization` header, blocks calls during maintenance mode, and automatically attempts `/api/auth/refresh` when a request returns `401`.

- `frontend/src/pages/LoginPage.tsx`  
  UI for login, registration, and password-reset requests. Calls `AuthContext` helpers and `authAPI.requestPasswordReset`. Displays success/error messages.

- `frontend/src/components/ChangePasswordDialog.tsx`  
  Modal that forces password changes when the backend sets `must_reset = true`. Uses `AuthContext.changePassword`.

- `frontend/src/App.tsx`  
  Redirects unauthenticated users to `LoginPage`. When signed in, shows the navigation shell and gives quick access to `Change Password` / `Logout`.

**Rule of thumb:** Do not talk to the REST API directly from random components. Always go through `AuthContext` or the helper methods in `services/api.ts` so token storage and refresh stay in sync.

---

## 2. Day-in-the-Life of a Login

1. **User submits the form** on `LoginPage`. The page calls `useAuth().login(username, password)`.
2. **`AuthContext.login`** calls `authAPI.login`. If the backend responds with `{ data: { access_token, refresh_token, user } }`, it stores both tokens in `localStorage`.
3. **Context updates state** (`setToken`, `setUser`). Because the provider wraps `<App />`, the UI rerenders and routes move from the login screen into the main shell.
4. **All Axios requests** go through `api.interceptors.request`, which reads `access_token` from `localStorage` and adds the `Authorization` header.
5. **If a request returns 401**, the response interceptor runs `attemptTokenRefresh()` exactly once. On success it saves the new access token and retries the original request; on failure it nukes both tokens and kicks the user back to `/login`.
6. **Password change requirement:** If the backend marks the user `must_reset = true`, `App.tsx` immediately opens `ChangePasswordDialog` once the user logs in.
7. **Logout** just clears both tokens in `AuthContext.logout()` and sets `user` to `null`, so the router falls back to the login screen.

---

## 3. Key State & Configuration

- **React state stored in `AuthContext`:**
  - `user`: Normalised shape with `user_id`, `username`, `role`, `must_reset`, login metadata.
  - `token`: Current access token string (mirrors `localStorage`).
  - `loading`: Tracks whether the provider is checking `/api/auth/me` on initial mount.

- **LocalStorage keys:**  
  `access_token`, `refresh_token`. Anything that mutates them should fire the `ACCESS_TOKEN_UPDATED_EVENT` so other tabs pick up the new token.

- **Axios interceptors:**  
  - Request interceptor sets the auth header and blocks calls during maintenance mode (using `MaintenanceManager`).  
  - Response interceptor handles refresh, 401 redirects, 503 maintenance activation, and timeouts.

- **Forms:** `LoginPage` uses `mode` state (`login` / `register` / `forgot`). All transitions reset form errors automatically—keep that behaviour if you refactor.

---

## 4. Working With Auth UI

1. **Wrap new routes with `AuthProvider`.** Every component that calls `useAuth()` must be inside the provider. `main.tsx` already ensures this.
2. **Always normalise backend responses.** When you wire new endpoints, stick to the `response.data.data || response.data` pattern used everywhere so we survive both standardised and legacy payloads.
3. **Handle errors loudly.** Use `ErrorAlert` for visible failures. Do not swallow `AxiosError`—`LoginPage` and `ChangePasswordDialog` expect a human-readable message.
4. **Password reset requests** intentionally have no automatic email. The UI just shows “An administrator will follow up.” If you add automation, update both the message and the backend docs.

---

## 5. Common Maintenance Tasks

| Task | Where | How to do it without breaking stuff |
|------|-------|--------------------------------------|
| Add a new user field (e.g., phone number) | `AuthContext.normalizeUser`, UI components displaying user info | Update the normaliser, adjust `User` type, and show the field wherever needed (profile chips, admin tables). |
| Change validation rules | `LoginPage` inputs / `ChangePasswordDialog` | Add `helperText` & `required` rules, but always mirror the backend checks so error messages stay aligned. |
| Force logout after password change | `AuthContext.changePassword` | After a successful change, call `logout()` (if required by policy) and show a toast so users know to sign in again. |
| Support SSO / external auth | Build a wrapper in `AuthContext.login` | After receiving tokens from your provider, still call `setToken` and `setUser` so the app state stays identical. |
| Run code only when authenticated | Check `useAuth().isAuthenticated` or `user` | Wrap components with a guard or return `null` if not signed in; never assume the user object exists. |

---

## 6. Extending or Modifying Behaviour

### 6.1 Add Multi-Factor Authentication (MFA)
1. Extend `LoginPage` to request the MFA token after the password step succeeds (keep all state local to the page).  
2. Store any new tokens in `localStorage` alongside the access token if they need to persist.  
3. Update `AuthContext.login` to call the new endpoint (`/api/auth/login/mfa` or similar) before calling `setUser`.

### 6.2 Show the logged-in user everywhere
1. Update `App.tsx` header (already displays `Welcome, ${user.username}`) to include new badges (e.g., `Chip` for `role`).  
2. For other components, use `const { user } = useAuth()` rather than copying props around.

### 6.3 Customise password-reset note field
1. Modify `LoginPage` “Forgot” form (the `note` textarea).  
2. Update the payload passed to `authAPI.requestPasswordReset`.  
3. Reword the success message if the process changes (e.g., automated email vs manual handling).

---

## 7. Quick Reference

| Function / Component | Purpose | Notes |
|----------------------|---------|-------|
| `useAuth()` | Access current user + auth helpers | Throws if used outside `AuthProvider`. |
| `AuthProvider` | Wraps the entire app | Performs initial `/api/auth/me` check on mount. |
| `authAPI.login(username, password)` | REST call for login | Returns the standard response format `{ data: { access_token, refresh_token, user } }`. |
| `authAPI.requestPasswordReset(...)` | Submits reset ticket | Accepts `{ username?, email?, note? }`; success message is generic on purpose. |
| `ACCESS_TOKEN_UPDATED_EVENT` | Broadcast after refresh | Other tabs listen and update their local access token. |
| `ChangePasswordDialog` | Force password update | Opens automatically when `user.must_reset` is `true`. |

---

## 8. When Something Goes Wrong

1. **Login spins forever**  
   - `AuthProvider` might be stuck at `loading=true`. Check browser dev tools for a failed `/api/auth/me`. Fix the backend or adjust CORS.  
   - Ensure `App.tsx` is reading `isAuthenticated`—if `AuthContext` returns `false`, you’ll stay on the login page.

2. **Refresh loop kicks user out immediately**  
   - Inspect localStorage: if `refresh_token` is missing or mismatched with the backend secret, the interceptor will remove both tokens.  
   - Verify backend `/api/auth/refresh` returns `{ data: { access_token } }`; the interceptor falls back to other shapes but needs a string.

3. **Forgot-password form never clears**  
   - Make sure `setSuccessMessage` runs and you reset all fields. Without the resets, the mode switch keeps stale data and confuses users.

4. **Change password dialog won’t close**  
   - Remember it ignores `onClose` when `requireChange=true`. To allow closing, ensure the backend clears `must_reset` after a successful change.

5. **Garbled usernames / missing roles**  
   - Update `normalizeUser` whenever backend responses change. If you forget, components will display `Unknown` or `undefined`.

Stick to these steps and the auth experience will stay predictable for everyone, including your future self.

