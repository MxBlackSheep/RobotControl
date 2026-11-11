import axios from 'axios';
import { getApiBase } from '@/utils/apiBase';
import { isMaintenanceActive } from '@/utils/MaintenanceManager';
import { isAppResponse, isSignInRejected, recordRequestFailure, recordRequestSuccess } from './requestError';

/** The `data` of a RobotControl reply `{ success, message, data }`, or the body itself. */
export const unwrapData = <T>(response: any): T => (response?.data?.data ?? response?.data) as T;

// The sign-in travels in HttpOnly cookies the page cannot read. The header marks requests as
// the page's own: the server refuses a cookie-signed change without it (another site cannot send it).
const clientOptions = {
  // Derive API base dynamically so phone/tablet clients proxy to the correct backend
  baseURL: getApiBase() || undefined,
  headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'RobotControl' },
  timeout: 10000, // 10 second timeout for API calls
};

export const api = axios.create(clientOptions);
const refreshClient = axios.create(clientOptions);

let refreshPromise: Promise<boolean> | null = null;

/** Renews the access cookie once for all callers: true when renewed, false when RobotControl
 * rejected the sign-in; an outage rejects, so nobody is signed out by it. Exported for streamed
 * downloads that must use fetch; everything else uses `api`. */
export const attemptTokenRefresh = (): Promise<boolean> => {
  refreshPromise ??= refreshClient
    .post('/api/auth/refresh')
    .then(() => true, (err) => {
      // Only RobotControl can reject a sign-in; a tunnel's 403 challenge page cannot.
      if (isSignInRejected(err)) return false;
      // Propagate the outage, not the original 401: a retry may still refresh.
      throw err;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
};

/** Settles once no refresh is in flight, so a late refresh cannot set the cookie after Sign out. */
export const refreshSettled = (): Promise<unknown> => (refreshPromise ?? Promise.resolve()).catch(() => undefined);

let signInRevision = 0;
/** Changes on every sign-in and sign-out, so a read cached for one person is never served to the next. */
export const currentSignIn = () => signInRevision;
export const signInChanged = () => { signInRevision += 1; };

// Respect maintenance windows
api.interceptors.request.use((config) => {
  const bypassMaintenance = config.headers.get('X-Allow-Maintenance') === 'true';
  if (!bypassMaintenance && isMaintenanceActive()) {
    return Promise.reject(new Error('Database maintenance in progress. Please wait a moment.'));
  }
  return config;
});

// Handle auth errors and timeouts
api.interceptors.response.use(
  (response) => {
    recordRequestSuccess();
    return response;
  },
  async (error) => {
    if (isAppResponse(error)) recordRequestSuccess();
    else recordRequestFailure(error);
    // A 401 page from a proxy says nothing about the RobotControl sign-in.
    const status = error.response?.status === 401 && !isAppResponse(error) ? undefined : error.response?.status;
    const originalRequest = error.config as Record<string, any> | undefined;
    const requestUrl: string = originalRequest?.url ?? '';
    const isAuthEndpoint = /\/api\/auth\/(login|register|refresh)/i.test(requestUrl);

    if (status === 401 && originalRequest && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      if (await attemptTokenRefresh()) return api(originalRequest);
    }

    // The signed-in check (/me) shows the sign-in page itself; redirecting it would reload forever.
    if (status === 401 && !isAuthEndpoint && !/\/api\/auth\/me/i.test(requestUrl)) {
      window.location.href = '/login';
    }

    // A 503 is not a database restart: scheduler and storage use it for their own outages.
    // Maintenance starts only from a successful restore (DatabaseRestore.tsx).

    // Keep the Axios error (config, code) so callers can tell which request timed out;
    // a timeout says nothing about the database, so the message does not guess a cause.
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      console.warn('API request timed out:', error.config?.url);
      error.message = 'Request timed out';
    }

    return Promise.reject(error);
  }
);

export const authAPI = {
  login: (username: string, password: string) =>
    api.post('/api/auth/login', { username, password }),

  register: (username: string, email: string, password: string) =>
    api.post('/api/auth/register', { username, email, password }),

  requestPasswordReset: (payload: { username?: string; email?: string; note?: string }) =>
    api.post('/api/auth/password-reset/request', payload),

  me: () => api.get('/api/auth/me', { headers: { 'X-Allow-Maintenance': 'true' } }),

  // Sign out must reach the server during the restore pause too, or both cookies stay.
  logout: () => api.post('/api/auth/logout', undefined, { headers: { 'X-Allow-Maintenance': 'true' } }),

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
};

export const databaseAPI = {
  getTables: (sourceId?: string) =>
    api.get('/api/database/tables', { params: { source_id: sourceId } }),

  getTableData: (tableName: string, page = 1, limit = 50, additionalParams = {}, signal?: AbortSignal) =>
    api.get(`/api/database/tables/${encodeURIComponent(tableName)}`,
      {
        params: { page, limit, ...additionalParams }, signal,
      }),

  getStoredProcedures: (sourceId?: string) =>
    api.get('/api/database/stored-procedures', { params: { source_id: sourceId } }),
};

export const experimentsAPI = {
  getLatest: () => api.get('/api/experiments/latest'),
};

export const adminAPI = {
  getUsers: () => api.get('/api/admin/users'),
  getPasswordResetRequests: () => api.get('/api/admin/password-reset/requests'),
  resolvePasswordResetRequest: (requestId: number, resolutionNote?: string) =>
    api.post(`/api/admin/password-reset/requests/${requestId}/resolve`, {
      resolution_note: resolutionNote,
    }),
  resetUserPassword: (username: string, newPassword: string, mustReset = true) =>
    api.post(`/api/admin/users/${username}/reset-password`, {
      new_password: newPassword,
      must_reset: mustReset,
    }),
  updateUserEmail: (username: string, email: string) =>
    api.put(`/api/admin/users/${username}/email`, { email }),
  setUserRole: (username: string, role: 'user' | 'admin') =>
    api.put(`/api/admin/users/${username}/role`, { role }),
  deleteUser: (username: string) => api.delete(`/api/admin/users/${username}`),
};
