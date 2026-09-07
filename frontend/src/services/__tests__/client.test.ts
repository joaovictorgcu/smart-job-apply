/**
 * The 401 path.
 *
 * Every request funnels through `request()`, so this is the single place where a
 * dead session is detected. It has to clear the token and broadcast exactly one
 * UNAUTHORIZED_EVENT: a second one would tear down an already-restarted session.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  TOKEN_STORAGE_KEY,
  UNAUTHORIZED_EVENT,
  api,
  getToken,
} from "@/services/client";

function respondWith(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client on 401", () => {
  let dispatched: string[];

  beforeEach(() => {
    dispatched = [];
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "stale-token");
    window.addEventListener(UNAUTHORIZED_EVENT, collect);
  });

  afterEach(() => {
    window.removeEventListener(UNAUTHORIZED_EVENT, collect);
  });

  function collect(event: Event) {
    dispatched.push(event.type);
  }

  it("clears the stored token and broadcasts once", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respondWith(401, { detail: "Not authenticated" }))),
    );

    await expect(api.get("/applications")).rejects.toBeInstanceOf(ApiError);

    expect(getToken()).toBeNull();
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(dispatched).toEqual([UNAUTHORIZED_EVENT]);
  });

  it("surfaces the backend detail on the thrown error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respondWith(401, { detail: "Token expirado" }))),
    );

    await expect(api.get("/applications")).rejects.toMatchObject({
      status: 401,
      detail: "Token expirado",
      isUnauthorized: true,
    });
  });

  it("leaves the session alone on any other failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respondWith(500, { detail: "Boom" }))),
    );

    await expect(api.get("/applications")).rejects.toBeInstanceOf(ApiError);

    expect(getToken()).toBe("stale-token");
    expect(dispatched).toEqual([]);
  });

  it("broadcasts once per failed request, not once per listener", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(respondWith(401, { detail: "Not authenticated" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const second: string[] = [];
    const secondListener = (event: Event) => second.push(event.type);
    window.addEventListener(UNAUTHORIZED_EVENT, secondListener);

    try {
      await expect(api.get("/applications")).rejects.toBeInstanceOf(ApiError);
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, secondListener);
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(dispatched).toHaveLength(1);
    expect(second).toHaveLength(1);
  });
});
