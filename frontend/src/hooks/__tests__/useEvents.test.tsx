/**
 * The live feed across a reconnect.
 *
 * The backend replays its recent history to every new connection, so whatever
 * the client does with those frames decides whether the activity list is stable
 * or doubles on each drop. These tests pin the behaviour that ships today.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventsProvider, useEvents } from "@/hooks/useEvents";
import type * as ApiClient from "@/services/client";
import { buildAppEvent } from "@/test/factories";
import { createTestQueryClient } from "@/test/utils";
import type { AppEvent } from "@/types/events";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: 1, email: "tester@example.invalid" },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("@/services/client", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClient>()),
  getToken: () => "test-token",
  buildWebSocketUrl: () => "ws://localhost/api/ws?token=test-token",
}));

/** Enough of the WebSocket surface for the provider, fully driven by the test. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.onclose?.();
  }

  /** Server -> client frame. */
  sendEvent(event: AppEvent): void {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  /** The connection dropping on its own, which is what triggers a reconnect. */
  drop(): void {
    this.onclose?.();
  }
}

const HISTORY: AppEvent[] = [
  buildAppEvent({ name: "job.found", job_id: 1, timestamp: "2026-08-01T10:00:00Z" }),
  buildAppEvent({ name: "job.analyzed", job_id: 1, timestamp: "2026-08-01T10:00:05Z" }),
];

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      <EventsProvider>{children}</EventsProvider>
    </QueryClientProvider>
  );
}

function replay(socket: FakeWebSocket, events: AppEvent[]): void {
  act(() => {
    socket.onopen?.();
    for (const event of events) socket.sendEvent(event);
  });
}

describe("useEvents reconnect", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("collects the history the server replays on connect", () => {
    const { result } = renderHook(() => useEvents(), { wrapper });

    expect(FakeWebSocket.instances).toHaveLength(1);
    replay(FakeWebSocket.instances[0], HISTORY);

    expect(result.current.events).toHaveLength(2);
    expect(result.current.connected).toBe(true);
  });

  /*
   * FINDING — current behaviour, deliberately pinned rather than fixed here.
   *
   * `EventsProvider` appends every frame unconditionally, so the history the
   * server replays on reconnect lands in the feed a second time: the activity
   * list doubles on each drop and each tab reload. Deduping is not a one-liner,
   * because `AppEvent` carries no server-assigned id (see types/events.ts) —
   * only a name plus a timestamp, and two genuine events can share both. A
   * correct fix most likely needs an event id from the backend, which is why
   * this is reported instead of patched.
   */
  it("re-appends the replayed history after a reconnect (known duplication)", () => {
    const { result } = renderHook(() => useEvents(), { wrapper });
    replay(FakeWebSocket.instances[0], HISTORY);
    expect(result.current.events).toHaveLength(2);

    act(() => {
      FakeWebSocket.instances[0].drop();
    });
    // Backoff for the first attempt is 1s plus jitter, capped well under 2s.
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(FakeWebSocket.instances).toHaveLength(2);
    replay(FakeWebSocket.instances[1], HISTORY);

    expect(result.current.events).toHaveLength(4);
  });

  it.skip("INTENDED: a reconnect does not duplicate events already in the feed", () => {
    const { result } = renderHook(() => useEvents(), { wrapper });
    replay(FakeWebSocket.instances[0], HISTORY);

    act(() => {
      FakeWebSocket.instances[0].drop();
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    replay(FakeWebSocket.instances[1], HISTORY);

    expect(result.current.events).toHaveLength(2);
  });
});
