import axios, { AxiosHeaders } from 'axios';
import { getApiBase } from '@/utils/apiBase';
import { isMaintenanceActive, getMaintenanceRemainingMs } from '@/utils/MaintenanceManager';

// Derive API base dynamically so phone/tablet clients proxy to the correct backend
const API_BASE_URL = getApiBase();

export const ACCESS_TOKEN_UPDATED_EVENT = 'robotcontrol:access-token-updated';

export const api = axios.create({
  baseURL: API_BASE_URL || undefined,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 second timeout for API calls
});

const refreshClient = axios.create({
  baseURL: API_BASE_URL || undefined,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

let refreshPromise: Promise<string | null> | null = null;

const dispatchTokenUpdate = (accessToken: string, refreshToken?: string | null) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(ACCESS_TOKEN_UPDATED_EVENT, {
      detail: {
        accessToken,
        refreshToken: refreshToken ?? null,
      },
    }),
  );
};

const attemptTokenRefresh = async (): Promise<string | null> => {
  if (typeof window === 'undefined') {
    return null;
  }
  const storedRefreshToken = localStorage.getItem('refresh_token');
  if (!storedRefreshToken) {
    return null;
  }
  if (!refreshPromise) {
    refreshPromise = refreshClient
      .post('/api/auth/refresh', { refresh_token: storedRefreshToken })
      .then((response) => {
        if (localStorage.getItem('refresh_token') !== storedRefreshToken) {
          throw new axios.CanceledError('Sign-in changed while refreshing');
        }
        const newToken =
          response.data?.data?.access_token ??
          response.data?.access_token ??
          null;
        if (newToken) {
          localStorage.setItem('access_token', newToken);
          dispatchTokenUpdate(newToken, storedRefreshToken);
        }
        return newToken;
      })
      .catch((err) => {
        if (localStorage.getItem('refresh_token') !== storedRefreshToken) throw err;
        if (err.response?.status === 401 || err.response?.status === 403) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          return null;
        }
        // Propagate the outage, not the original 401: a retry may still refresh.
        throw err;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
};

// Add auth token to requests and respect maintenance windows
api.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers || {});
  config.headers = headers;

  const maintenanceBypassHeader =
    headers.get('X-Allow-Maintenance') ?? headers.get('x-allow-maintenance');
  const bypassMaintenance = maintenanceBypassHeader === 'true';

  if (!bypassMaintenance && isMaintenanceActive()) {
    const maintenanceError: any = new Error('Database maintenance in progress. Please wait a moment.');
    maintenanceError.name = 'MaintenanceError';
    maintenanceError.isMaintenance = true;
    maintenanceError.remainingMs = getMaintenanceRemainingMs();
    return Promise.reject(maintenanceError);
  }

  const token = localStorage.getItem('access_token');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  return config;
});

// Handle auth errors and timeouts
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    const originalRequest = error.config as Record<string, any> | undefined;
    const requestUrl = originalRequest?.url ?? '';

    const isAuthEndpoint = (url?: string) =>
      !!url &&
      (/\/api\/auth\/login/i.test(url) ||
        /\/api\/auth\/register/i.test(url) ||
        /\/api\/auth\/refresh/i.test(url));

    if (status === 401 && originalRequest && !originalRequest._retry && !isAuthEndpoint(requestUrl)) {
      originalRequest._retry = true;
      const refreshedToken = await attemptTokenRefresh();
      if (refreshedToken) {
        const headers = AxiosHeaders.from(originalRequest.headers || {});
        headers.set('Authorization', `Bearer ${refreshedToken}`);
        originalRequest.headers = headers;
        return api(originalRequest);
      }
    }

    if (status === 401) {
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem('access_token');
        window.localStorage.removeItem('refresh_token');
        if (!isAuthEndpoint(requestUrl)) {
          window.location.href = '/login';
        }
      }
    }

    // A 503 is not a database restart: scheduler and storage use it for their own outages.
    // Maintenance starts only from a successful restore (DatabaseRestore.tsx).

    // Handle timeout errors specifically
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      console.warn('API request timed out:', error.config?.url);
      // Create a proper error response structure that components can handle
      const timeoutError = new Error('Request timed out - database may be unavailable');
      timeoutError.name = 'TimeoutError';
      return Promise.reject(timeoutError);
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

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
};

export const databaseAPI = {
  getTables: (importantOnly = false, sourceId?: string) =>
    api.get('/api/database/tables', { params: { important_only: importantOnly, source_id: sourceId } }),

  getTableData: (tableName: string, page = 1, limit = 50, additionalParams = {}, signal?: AbortSignal) =>
    api.get(`/api/database/tables/${encodeURIComponent(tableName)}`,
      {
        params: { page, limit, ...additionalParams }, signal,
      }),

  getStoredProcedures: (useCache = true, sourceId?: string) =>
    api.get('/api/database/stored-procedures', { params: { use_cache: useCache, source_id: sourceId } }),
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
  deleteUser: (username: string) => api.delete(`/api/admin/users/${username}`),
};
