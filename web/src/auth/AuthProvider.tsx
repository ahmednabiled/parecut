import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { apiFetch } from "../api/client";
import type { SessionUser } from "../api/types";

interface AuthState {
  me: SessionUser | null;
  isLoading: boolean;
}

const AuthContext = createContext<AuthState>({ me: null, isLoading: true });

export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery<SessionUser>({
    queryKey: ["me"],
    queryFn: () => apiFetch<SessionUser>("/api/auth/me"),
    retry: false,
    staleTime: 30_000,
  });

  return (
    <AuthContext.Provider value={{ me: query.data ?? null, isLoading: query.isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
