import { api, clearToken, setToken } from "@/services/client";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "@/types/api";

/** POST /api/auth/register — stores the returned token. */
export async function register(payload: RegisterRequest): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>("/auth/register", payload, {
    anonymous: true,
  });
  setToken(response.access_token);
  return response;
}

/** POST /api/auth/login — stores the returned token. */
export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>("/auth/login", payload, {
    anonymous: true,
  });
  setToken(response.access_token);
  return response;
}

/** GET /api/auth/me */
export function fetchCurrentUser(signal?: AbortSignal): Promise<User> {
  return api.get<User>("/auth/me", { signal });
}

/** Local-only: the JWT is stateless, so there is nothing to revoke server-side. */
export function logout(): void {
  clearToken();
}
