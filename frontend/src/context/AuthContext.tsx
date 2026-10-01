import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react';
import { authAPI, ACCESS_TOKEN_UPDATED_EVENT } from '../services/api';
import { isSignInRejected } from '../services/requestError';

interface User {
  user_id: string;
  username: string;
  email?: string;
  role: 'admin' | 'user';
  is_active?: boolean;
  must_reset?: boolean;
  last_login_ip?: string | null;
  last_login_ip_type?: string | null;
  session_is_local?: boolean;
  session_ip_classification?: string | null;
  session_client_ip?: string | null;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

// Alias for compatibility
export const useAuthContext = useAuth;

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const authRevision = useRef(0);

  const normalizeUser = useCallback((rawUser: any, sessionOverride?: any): User => {
    const session = sessionOverride ?? rawUser?.session ?? {};
    return {
      user_id: String(rawUser?.user_id ?? rawUser?.id ?? ''),
      username: rawUser?.username ?? '',
      email: rawUser?.email ?? rawUser?.user_email,
      role: rawUser?.role ?? 'user',
      is_active: rawUser?.is_active,
      must_reset: rawUser?.must_reset,
      last_login_ip: rawUser?.last_login_ip ?? null,
      last_login_ip_type: rawUser?.last_login_ip_type ?? null,
      session_is_local: typeof session?.is_local === 'boolean' ? session.is_local : undefined,
      session_ip_classification: session?.ip_classification ?? null,
      session_client_ip: session?.client_ip ?? null,
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const revision = authRevision.current;
    const isCurrent = () => !cancelled && revision === authRevision.current;
    const checkAuth = async () => {
      if (!isCurrent()) return;
      const accessToken = localStorage.getItem('access_token');
      if (!accessToken) {
        setLoading(false);
        return;
      }
      setToken(accessToken);
      try {
        const response = await authAPI.me();
        if (!isCurrent()) return;
        const userData = response.data.data || response.data;
        setUser(normalizeUser(userData, userData?.session));
        setLoading(false);
      } catch (error: any) {
        if (!isCurrent()) return;
        if (isSignInRejected(error)) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          setToken(null);
          setUser(null);
          setLoading(false);
        } else {
          // Keep credentials, but do not grant access until /me verifies them.
          retry = setTimeout(checkAuth, 5000);
        }
      }
    };
    void checkAuth();
    return () => {
      cancelled = true;
      clearTimeout(retry);
    };
  }, [normalizeUser]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ accessToken?: string }>).detail;
      if (detail?.accessToken) {
        setToken(detail.accessToken);
      }
    };
    window.addEventListener(ACCESS_TOKEN_UPDATED_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(ACCESS_TOKEN_UPDATED_EVENT, handler as EventListener);
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    authRevision.current += 1;
    // Errors propagate unchanged: the page must tell a wrong password from an unreachable server.
    const response = await authAPI.login(username, password);
    // Handle standardized response format: { success, data: {...}, metadata }
    const responseData = response.data.data || response.data;
    const { access_token, refresh_token, user: userData, session } = responseData;

    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    setToken(access_token);
    setUser(normalizeUser(userData, session));
    setLoading(false);
  }, [normalizeUser]);

  const register = useCallback(async (username: string, email: string, password: string) => {
    authRevision.current += 1;
    const response = await authAPI.register(username, email, password);
    const responseData = response.data.data || response.data;
    const { access_token, refresh_token, user: userData, session } = responseData;

    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    setToken(access_token);
    setUser(normalizeUser(userData, session));
    setLoading(false);
  }, [normalizeUser]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await authAPI.changePassword(currentPassword, newPassword);
    // Refresh user profile to clear must_reset flag
    try {
      const response = await authAPI.me();
      const userData = response.data.data || response.data;
      setUser(normalizeUser(userData, userData?.session));
    } catch (error) {
      if (isSignInRejected(error)) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setToken(null);
        setUser(null);
      } else {
        // The change succeeded; a dropped profile read must not sign the user out.
        setUser((current) => (current ? { ...current, must_reset: false } : current));
      }
    }
  }, [normalizeUser]);

  const logout = useCallback(() => {
    authRevision.current += 1;
    setLoading(false);
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({
    user,
    token,
    login,
    register,
    changePassword,
    logout,
    isAuthenticated: !!user,
    loading,
  }), [user, token, login, register, changePassword, logout, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
