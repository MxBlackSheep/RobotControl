import axios from 'axios';
import { getApiBase } from '@/utils/apiBase';

// Derive API base dynamically so phone/tablet clients proxy to the correct backend
const API_BASE_URL = getApiBase();

export const api = axios.create({
  baseURL: API_BASE_URL || undefined,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 second timeout for API calls
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors and timeouts
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }

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

  refresh: (refreshToken: string) =>
    api.post('/api/auth/refresh', { refresh_token: refreshToken }),

  me: () => api.get('/api/auth/me'),

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
};

export const databaseAPI = {
  getTables: (importantOnly = false) =>
    api.get('/api/database/tables', { params: { important_only: importantOnly } }),

  getStatus: () => api.get('/api/database/status'),

  getTableData: (tableName: string, page = 1, limit = 50, additionalParams = {}) =>
    api.get(`/api/database/tables/${tableName}`,
      {
        params: { page, limit, ...additionalParams },
      }),

  getTableSchema: (tableName: string) =>
    api.get(`/api/database/tables/${tableName}/columns`),

  getStoredProcedures: (useCache = true) =>
    api.get('/api/database/stored-procedures', { params: { use_cache: useCache } }),

  executeProcedure: (procedureName: string, parameters?: Record<string, any>) =>
    api.post('/api/database/execute-procedure', {
      procedure_name: procedureName,
      parameters,
    }),

  getExperiments: (page = 1, limit = 100) =>
    api.get('/api/database/tables/Experiments', { params: { page, limit } }),
};

export const experimentsAPI = {
  getLatest: () => api.get('/api/experiments/latest'),

  getHealth: () => api.get('/api/experiments/health'),
};

export const systemAPI = {
  health: () => api.get('/health'),
  status: () => api.get('/api/database/status'),
};

export const adminAPI = {
  getSystemStatus: () => api.get('/api/admin/system/status'),
  getUsers: () => api.get('/api/admin/users'),
  getDatabasePerformance: () => api.get('/api/admin/database/performance'),
};
