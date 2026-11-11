import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react';
import { authAPI, refreshSettled, signInChanged } from '../services/api';
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

interface AuthProviderProps {
  children: ReactNode;
}

/** The user from a sign-in reply (`user` plus `session`) or from /me (one object holding `session`). */
const normalizeUser = (rawUser: any, session: any = rawUser.session ?? {}): User => ({
  user_id: String(rawUser.user_id),
  username: rawUser.username,
  email: rawUser.email,
  role: rawUser.role,
  is_active: rawUser.is_active,
  must_reset: rawUser.must_reset,
  last_login_ip: rawUser.last_login_ip ?? null,
  last_login_ip_type: rawUser.last_login_ip_type ?? null,
  session_is_local: typeof session.is_local === 'boolean' ? session.is_local : undefined,
  session_ip_classification: session.ip_classification ?? null,
  session_client_ip: session.client_ip ?? null,
});

/**
 * The signed-in user. The sign-in itself lives in HttpOnly cookies that this code never sees,
 * so a page load asks /api/auth/me: 401 means signed out, an outage retries every 5 s.
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const authRevision = useRef(0);
  const signingOut = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    // Tokens an older build kept where page scripts can read them.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const revision = authRevision.current;
    const isCurrent = () => !cancelled && revision === authRevision.current;
    const checkAuth = async () => {
      if (!isCurrent()) return;
      try {
        const response = await authAPI.me();
        if (!isCurrent()) return;
        setUser(normalizeUser(response.data.data));
        setLoading(false);
      } catch (error: any) {
        if (!isCurrent()) return;
        if (isSignInRejected(error)) {
          setUser(null);
          setLoading(false);
        } else {
          // Do not grant access until /me verifies the sign-in.
          retry = setTimeout(checkAuth, 5000);
        }
      }
    };
    void checkAuth();
    return () => {
      cancelled = true;
      clearTimeout(retry);
    };
  }, []);

  /** Login and register: the server sets the cookies; the reply carries the user and session. */
  const signIn = useCallback(async (request: () => Promise<any>) => {
    authRevision.current += 1;
    // A sign-out still being sent must not clear the cookies this sign-in sets.
    await signingOut.current;
    // Errors propagate unchanged: the page must tell a wrong password from an unreachable server.
    const { user: userData, session } = (await request()).data.data;
    signInChanged();
    setUser(normalizeUser(userData, session));
    setLoading(false);
  }, []);

  const login = useCallback((username: string, password: string) =>
    signIn(() => authAPI.login(username, password)), [signIn]);

  const register = useCallback((username: string, email: string, password: string) =>
    signIn(() => authAPI.register(username, email, password)), [signIn]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await authAPI.changePassword(currentPassword, newPassword);
    // Refresh user profile to clear must_reset flag
    try {
      const response = await authAPI.me();
      setUser(normalizeUser(response.data.data));
    } catch (error) {
      if (isSignInRejected(error)) {
        setUser(null);
      } else {
        // The change succeeded; a dropped profile read must not sign the user out.
        setUser((current) => (current ? { ...current, must_reset: false } : current));
      }
    }
  }, []);

  const logout = useCallback(() => {
    authRevision.current += 1;
    // The server ends the sign-in after any refresh in flight, so a late refresh reply cannot
    // set the cookie again. The page signs out at once and does not wait for the reply.
    signingOut.current = refreshSettled().then(() => authAPI.logout()).catch(() => undefined);
    signInChanged();
    setLoading(false);
    setUser(null);
  }, []);

  const value = useMemo(() => ({
    user,
    login,
    register,
    changePassword,
    logout,
    isAuthenticated: !!user,
    loading,
  }), [user, login, register, changePassword, logout, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
