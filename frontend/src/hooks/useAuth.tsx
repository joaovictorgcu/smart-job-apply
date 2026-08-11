import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import * as authService from "@/services/auth";
import { UNAUTHORIZED_EVENT, getToken } from "@/services/client";
import type { LoginRequest, RegisterRequest, User } from "@/types/api";

interface AuthContextValue {
  user: User | null;
  /** True while the initial /auth/me bootstrap is in flight. */
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (payload: LoginRequest) => Promise<User>;
  register: (payload: RegisterRequest) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(() => Boolean(getToken()));
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const logout = useCallback(() => {
    authService.logout();
    setUser(null);
    setIsLoading(false);
    // Another account must never inherit the previous user's cached data.
    queryClient.clear();
  }, [queryClient]);

  // Bootstrap: a stored token is only trusted once /auth/me confirms it.
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);

    authService
      .fetchCurrentUser(controller.signal)
      .then((fetched) => {
        if (!mounted.current || controller.signal.aborted) return;
        setUser(fetched);
      })
      .catch(() => {
        // A 401 already cleared the token via the client; anything else means we
        // cannot vouch for the session either.
        if (!mounted.current || controller.signal.aborted) return;
        setUser(null);
      })
      .finally(() => {
        if (!mounted.current || controller.signal.aborted) return;
        setIsLoading(false);
      });

    return () => controller.abort();
  }, []);

  // Any 401 anywhere in the app tears the session down exactly once.
  useEffect(() => {
    const handleUnauthorized = () => logout();
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [logout]);

  const login = useCallback(
    async (payload: LoginRequest) => {
      const response = await authService.login(payload);
      queryClient.clear();
      setUser(response.user);
      setIsLoading(false);
      return response.user;
    },
    [queryClient],
  );

  const register = useCallback(
    async (payload: RegisterRequest) => {
      const response = await authService.register(payload);
      queryClient.clear();
      setUser(response.user);
      setIsLoading(false);
      return response.user;
    },
    [queryClient],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isAuthenticated: Boolean(user),
      login,
      register,
      logout,
    }),
    [user, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an AuthProvider.");
  }
  return context;
}
