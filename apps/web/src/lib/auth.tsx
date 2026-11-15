import { createContext, useContext, useEffect, useState } from "react";
import { api, Me } from "./api/client";

type Ctx = { me: Me | null; loading: boolean; refresh: () => Promise<void> };
const AuthCtx = createContext<Ctx>({ me: null, loading: true, refresh: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = async () => {
    const { data } = await api.GET("/api/auth/me");
    setMe(data ?? null);
    setLoading(false);
  };
  useEffect(() => { refresh(); }, []);
  return <AuthCtx.Provider value={{ me, loading, refresh }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
