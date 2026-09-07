"use client";

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  AuthUser,
  fetchMe,
  loadAuthToken,
  login as apiLogin,
  setAuthToken,
} from "@/lib/api";

type Auth = {
  user: AuthUser | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<Auth>({
  user: null,
  ready: false,
  login: async () => {},
  logout: () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      const token = loadAuthToken();
      if (token) {
        try {
          setUser(await fetchMe());
        } catch {
          setAuthToken(null); // stale/expired token
        }
      }
      setReady(true);
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password);
    setUser(await fetchMe());
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    if (loadAuthToken()) {
      try {
        setUser(await fetchMe());
      } catch {
        /* ignore */
      }
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = (): Auth => useContext(AuthContext);
