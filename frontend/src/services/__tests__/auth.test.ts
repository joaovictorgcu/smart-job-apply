/**
 * Deleting the account ends the session the same way a 401 does.
 *
 * There is no token to revoke server-side — the row the token points at simply
 * stops existing — so the client has to drop it and tell the app, or the next
 * screen renders against an account that is gone.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { deleteAccount } from "@/services/auth";
import { TOKEN_STORAGE_KEY, UNAUTHORIZED_EVENT } from "@/services/client";

describe("deleteAccount", () => {
  let dispatched: number;

  const collect = () => {
    dispatched += 1;
  };

  beforeEach(() => {
    dispatched = 0;
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "a-live-token");
    window.addEventListener(UNAUTHORIZED_EVENT, collect);
  });

  afterEach(() => {
    window.removeEventListener(UNAUTHORIZED_EVENT, collect);
  });

  it("sends the password as the body of a DELETE", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteAccount("correct-horse-battery");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/users/me");
    expect(init.method).toBe("DELETE");
    expect(JSON.parse(String(init.body))).toEqual({ password: "correct-horse-battery" });
  });

  it("drops the token and announces the end of the session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );

    await deleteAccount("correct-horse-battery");

    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(dispatched).toBe(1);
  });

  it("keeps the session when the server refuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "Incorrect password." }), {
            status: 401,
            headers: { "content-type": "application/json" },
          }),
      ),
    );

    await expect(deleteAccount("wrong")).rejects.toThrow("Incorrect password.");

    // The 401 handler in `request()` owns that path and fires exactly once; what
    // matters here is that `deleteAccount` adds no second teardown of its own.
    expect(dispatched).toBe(1);
  });
});
