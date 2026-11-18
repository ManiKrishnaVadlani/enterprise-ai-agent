import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { clearStoredToken, getStoredToken, SESSION_EXPIRED_EVENT, setStoredToken } from "../services/api";

interface SessionContextValue {
  authenticated: boolean;
  saveToken: (token: string) => void;
  logout: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(() => Boolean(getStoredToken()));

  useEffect(() => {
    const expire = () => setAuthenticated(false);
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, []);

  const value = useMemo<SessionContextValue>(() => ({
    authenticated,
    saveToken(token) {
      setStoredToken(token);
      setAuthenticated(true);
    },
    logout() {
      clearStoredToken();
      setAuthenticated(false);
    },
  }), [authenticated]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider.");
  return context;
}
