import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { configureAuth, loginRequest } from "./client";

/**
 * In-memory auth context (demo-grade — the bearer token lives in React
 * state, never localStorage). The axios interceptor in client.ts reads the
 * current token via a getter we register here, and calls onUnauthorized to
 * bounce back to the login screen on any 401.
 */
interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  /** Set when the server rejected an existing token (expired/invalid) and the
   * app bounced to login — lets the login screen say WHY instead of looking
   * like an unexplained logout. Cleared on the next successful login only. */
  sessionExpired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const logout = useCallback(() => {
    setToken(null);
    setUsername(null);
    setRole(null);
  }, []);

  // Called by the axios 401 handler: the server rejected a token we held.
  const onUnauthorized = useCallback(() => {
    setSessionExpired(true);
    setToken(null);
    setUsername(null);
    setRole(null);
  }, []);

  // Wire the interceptor to this context exactly once (and on token change).
  useEffect(() => {
    configureAuth(() => token, onUnauthorized);
  }, [token, onUnauthorized]);

  const login = useCallback(async (user: string, pass: string) => {
    const res = await loginRequest(user, pass);
    setToken(res.access_token);
    setUsername(res.username);
    setRole(res.role);
    setSessionExpired(false); // only on success — a wrong password keeps the reason visible
  }, []);

  const value = useMemo<AuthState>(
    () => ({ token, username, role, sessionExpired, login, logout }),
    [token, username, role, sessionExpired, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
