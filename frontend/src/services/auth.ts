import { api, clearToken, notifyUnauthorized, setToken } from "@/services/client";
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

/**
 * DELETE /api/users/me — erases the account. Irreversible.
 *
 * The password goes in the body because a valid token is not enough proof for
 * a request that cannot be undone.
 *
 * Ending the session is signalled the same way a 401 is, rather than by calling
 * `logout` through the auth context: the listener that clears the cached user
 * and empties the query cache is already there, and routing this through it
 * keeps the deletion button from needing the session it is about to destroy.
 */
export async function deleteAccount(password: string): Promise<void> {
  await api.delete<void>("/users/me", { password });
  notifyUnauthorized();
}
