import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { authAPI } from '../services/api';

interface User {
  user_id: string;
  username: string;
  email?: string;
  role: 'admin' | 'user';
  is_active?: boolean;
  must_reset?: boolean;
  last_login_ip?: string | null;
  last_login_ip_type?: string | null;
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

  const normalizeUser = useCallback((rawUser: any): User => ({
    user_id: String(rawUser?.user_id ?? rawUser?.id ?? ''),
    username: rawUser?.username ?? '',
    email: rawUser?.email ?? rawUser?.user_email,
    role: rawUser?.role ?? 'user',
    is_active: rawUser?.is_active,
    must_reset: rawUser?.must_reset,
    last_login_ip: rawUser?.last_login_ip ?? null,
    last_login_ip_type: rawUser?.last_login_ip_type ?? null,
  }), []);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const accessToken = localStorage.getItem('access_token');
        if (accessToken) {
          setToken(accessToken);
          const response = await authAPI.me();
          // Handle standardized response format: { success, data: {...}, metadata }
          const userData = response.data.data || response.data;
          setUser(normalizeUser(userData));
        }
      } catch (error) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, [normalizeUser]); // Empty dependency - run once

  const login = useCallback(async (username: string, password: string) => {
    try {
      const response = await authAPI.login(username, password);
      // Handle standardized response format: { success, data: {...}, metadata }
      const responseData = response.data.data || response.data;
      const { access_token, refresh_token, user: userData } = responseData;
      
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      setToken(access_token);
      setUser(normalizeUser(userData));
    } catch (error) {
      throw new Error('Login failed');
    }
  }, [normalizeUser]);

  const register = useCallback(async (username: string, email: string, password: string) => {
    try {
      const response = await authAPI.register(username, email, password);
      const responseData = response.data.data || response.data;
      const { access_token, refresh_token, user: userData } = responseData;

      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      setToken(access_token);
      setUser(normalizeUser(userData));
    } catch (error) {
      throw new Error('Registration failed');
    }
  }, [normalizeUser]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await authAPI.changePassword(currentPassword, newPassword);
    // Refresh user profile to clear must_reset flag
    try {
      const response = await authAPI.me();
      const userData = response.data.data || response.data;
      setUser(normalizeUser(userData));
    } catch (error) {
      // If fetching profile fails, log the user out to avoid inconsistent state
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setToken(null);
      setUser(null);
    }
  }, [normalizeUser]);

  const logout = useCallback(() => {
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
