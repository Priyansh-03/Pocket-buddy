import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/client";

export type UserMe = {
  id: string;
  email: string;
  salary_day: number | null;
  monthly_rent_inr: string | null;
  estimated_cash_inr: string | null;
  wallet_1_inr?: string | null;
  wallet_2_inr?: string | null;
  wallet_3_inr?: string | null;
  wallet_4_inr?: string | null;
  wallet_5_inr?: string | null;
  daily_budget_inr?: string | null;
  profit_inr?: string | null;
  wallet_1_loan_inr?: string | null;
  wallet_2_loan_inr?: string | null;
  wallet_3_loan_inr?: string | null;
  wallet_4_loan_inr?: string | null;
  wallet_5_loan_inr?: string | null;
  active_wallet_id?: number;
  money_profile_notes?: string | null;
  food_menu_text?: string | null;
  remember_text?: string | null;
  llm_provider: string;
};

type AuthCtx = {
  token: string | null;
  user: UserMe | null;
  bootstrapping: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);
const STORAGE = "survival_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(STORAGE));
  const [user, setUser] = useState<UserMe | null>(null);
  const [bootstrapping, setBootstrapping] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!token) {
      setUser(null);
      return;
    }
    const me = await apiFetch<UserMe>("/auth/me", { token, method: "GET" });
    setUser(me);
  }, [token]);

  useEffect(() => {
    (async () => {
      try {
        if (token) await refreshUser();
        else setUser(null);
      } catch {
        setToken(null);
        localStorage.removeItem(STORAGE);
        setUser(null);
      } finally {
        setBootstrapping(false);
      }
    })();
  }, [token, refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await apiFetch<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem(STORAGE, r.access_token);
    setToken(r.access_token);
    const me = await apiFetch<UserMe>("/auth/me", { token: r.access_token, method: "GET" });
    setUser(me);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const r = await apiFetch<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem(STORAGE, r.access_token);
    setToken(r.access_token);
    const me = await apiFetch<UserMe>("/auth/me", { token: r.access_token, method: "GET" });
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ token, user, bootstrapping, login, register, logout, refreshUser }),
    [token, user, bootstrapping, login, register, logout, refreshUser],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
}
