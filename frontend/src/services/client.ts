/**
 * Typed fetch wrapper for the backend API.
 *
 * Every request goes through here so token handling and the 401 -> logout
 * broadcast live in exactly one place.
 */

export const API_BASE = "/api";
export const TOKEN_STORAGE_KEY = "laa.token";
export const UNAUTHORIZED_EVENT = "laa:unauthorized";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly payload: unknown;

  constructor(status: number, detail: string, payload?: unknown) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.payload = payload;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** 422 from FastAPI request validation. */
  get isValidation(): boolean {
    return this.status === 422;
  }
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Storage may be unavailable; the session then lasts only for this page.
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Nothing to do.
  }
}

function notifyUnauthorized(): void {
  clearToken();
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

/** Pulls a human-readable message out of FastAPI's error shapes. */
function extractDetail(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (typeof payload !== "object" || payload === null) return fallback;

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;

  // 422: [{loc: [...], msg: "...", type: "..."}]
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (typeof item !== "object" || item === null) return null;
        const entry = item as { msg?: unknown; loc?: unknown };
        const msg = typeof entry.msg === "string" ? entry.msg : null;
        if (!msg) return null;
        const loc = Array.isArray(entry.loc)
          ? entry.loc.filter((part) => part !== "body").join(".")
          : "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter((item): item is string => Boolean(item));
    if (messages.length) return messages.join("; ");
  }

  const message = (payload as { message?: unknown }).message;
  if (typeof message === "string" && message.trim()) return message;

  return fallback;
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) return null;
  const contentType = response.headers.get("content-type") ?? "";
  try {
    if (contentType.includes("application/json")) return await response.json();
    const text = await response.text();
    return text || null;
  } catch {
    return null;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-encoded automatically. */
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** Skip the Authorization header (login/register). */
  anonymous?: boolean;
}

async function handle<T>(response: Response): Promise<T> {
  const payload = await readBody(response);

  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(
      response.status,
      extractDetail(payload, response.statusText || `Request failed (${response.status})`),
      payload,
    );
  }

  return payload as T;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, headers = {}, anonymous = false } = options;

  const finalHeaders: Record<string, string> = { Accept: "application/json", ...headers };
  if (body !== undefined) finalHeaders["Content-Type"] = "application/json";

  if (!anonymous) {
    const token = getToken();
    if (token) finalHeaders.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Cannot reach the server. Is the backend running?", error);
  }

  return handle<T>(response);
}

/** Multipart upload; the browser sets the boundary, so no Content-Type here. */
export async function upload<T>(
  path: string,
  file: File,
  options: { field?: string; method?: "POST" | "PUT"; signal?: AbortSignal } = {},
): Promise<T> {
  const { field = "file", method = "POST", signal } = options;

  const form = new FormData();
  form.append(field, file, file.name);

  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method, headers, body: form, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Upload failed: cannot reach the server.", error);
  }

  return handle<T>(response);
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
  upload,
};

/**
 * Absolute ws:// or wss:// URL for the live event stream.
 *
 * Derived from window.location so it works behind the Vite dev proxy and when
 * the built bundle is served by the backend itself.
 */
export function buildWebSocketUrl(token: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${API_BASE}/ws?token=${encodeURIComponent(token)}`;
}

/** Human-readable message for any thrown value. */
export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
