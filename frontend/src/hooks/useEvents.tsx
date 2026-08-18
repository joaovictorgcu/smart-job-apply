/**
 * Single WebSocket to /api/ws, shared by the whole app.
 *
 * Besides exposing the live feed, this provider is what makes the UI
 * self-updating: each incoming event invalidates the matching TanStack Query
 * keys, so pages never poll.
 */

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
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { backoffDelay } from "@/lib/utils";
import { buildWebSocketUrl, getToken } from "@/services/client";
import { parseAppEvent, type AppEvent, type EventName } from "@/types/events";

/** Newest last; the activity feed renders the tail. */
const MAX_EVENTS = 300;
const MAX_RECONNECT_ATTEMPTS = 12;

type EventHandler = (event: AppEvent) => void;

interface EventsContextValue {
  events: AppEvent[];
  connected: boolean;
  lastEvent: AppEvent | null;
  /** Most recent automation.blocked event, cleared on the next start/stop. */
  blockedEvent: AppEvent | null;
  clearBlocked: () => void;
  clearEvents: () => void;
  /** Returns an unsubscribe function. Pass "*" to receive every event. */
  subscribe: (name: EventName | "*", handler: EventHandler) => () => void;
}

const EventsContext = createContext<EventsContextValue | null>(null);

/**
 * Identity of an event, for the reconnect dedupe.
 *
 * The backend replays its last 200 events to every new connection (see
 * `ConnectionManager` in backend/app/websocket/manager.py), so after every drop
 * — and every tab reload — the client is handed frames it already has. `Event`
 * carries no server-assigned id (backend/app/observability/events.py), so
 * identity has to be reconstructed from the envelope: a replayed frame is
 * `model_dump(mode="json")` of the very same object the live frame came from,
 * hence byte-identical field by field. Taking the whole envelope, `data`
 * included, keeps the dedupe as narrow as possible — nothing is collapsed that
 * differs in any observable way.
 *
 * What would make this wrong: two genuinely distinct events agreeing on every
 * field, which today means being created inside the same microsecond (the
 * resolution of `datetime.now(UTC)`) with the same ids, message and payload. A
 * backend that truncated the timestamp to whole seconds, or re-serialized `data`
 * with a different key order between the live send and the replay, would break
 * the assumption in either direction — at which point the real fix is an event
 * id on the wire rather than a wider tuple here.
 */
function eventKey(event: AppEvent): string {
  // JSON rather than a joined string: a message containing the separator must
  // not be able to impersonate a different field split.
  return JSON.stringify([
    event.name,
    event.timestamp,
    event.level,
    event.run_id,
    event.job_id,
    event.application_id,
    event.message,
    event.data,
  ]);
}

function invalidateForEvent(client: QueryClient, event: AppEvent): void {
  const invalidate = (queryKey: readonly unknown[]) => {
    void client.invalidateQueries({ queryKey });
  };

  switch (event.name) {
    case "automation.started":
    case "automation.stopped":
    case "automation.error":
    case "automation.blocked":
      invalidate(queryKeys.automation());
      invalidate(queryKeys.stats());
      break;

    case "automation.progress":
      invalidate(queryKeys.runsAll());
      if (event.run_id !== null) invalidate(queryKeys.run(event.run_id));
      break;

    case "job.found":
      invalidate(queryKeys.jobs());
      invalidate(queryKeys.stats());
      break;

    case "job.analyzed":
      invalidate(queryKeys.jobs());
      if (event.job_id !== null) invalidate(queryKeys.job(event.job_id));
      invalidate(queryKeys.stats());
      break;

    case "application.started":
    case "application.awaiting_review":
    case "application.completed":
      invalidate(queryKeys.applications());
      if (event.application_id !== null) {
        invalidate(queryKeys.application(event.application_id));
        invalidate(queryKeys.applicationEvents(event.application_id));
      }
      if (event.job_id !== null) invalidate(queryKeys.job(event.job_id));
      invalidate(queryKeys.jobs());
      invalidate(queryKeys.session());
      invalidate(queryKeys.stats());
      break;

    case "session.status":
      invalidate(queryKeys.session());
      break;

    case "log":
      break;
  }
}

export function EventsProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { isAuthenticated } = useAuth();

  const [events, setEvents] = useState<AppEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<AppEvent | null>(null);
  const [blockedEvent, setBlockedEvent] = useState<AppEvent | null>(null);

  // Keys of the events currently in the feed, so a replayed history is dropped
  // instead of appended twice. Insertion-ordered like the feed itself and capped
  // at the same MAX_EVENTS, so the two are trimmed in lockstep.
  const seenRef = useRef<Set<string>>(new Set());
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const attemptsRef = useRef(0);
  const closedByUsRef = useRef(false);
  const subscribersRef = useRef<Map<EventName | "*", Set<EventHandler>>>(new Map());

  const subscribe = useCallback((name: EventName | "*", handler: EventHandler) => {
    const map = subscribersRef.current;
    let handlers = map.get(name);
    if (!handlers) {
      handlers = new Set();
      map.set(name, handlers);
    }
    handlers.add(handler);
    return () => {
      handlers?.delete(handler);
      if (handlers && handlers.size === 0) map.delete(name);
    };
  }, []);

  const dispatch = useCallback((event: AppEvent) => {
    for (const handler of subscribersRef.current.get(event.name) ?? []) {
      try {
        handler(event);
      } catch {
        // A broken subscriber must not stop the stream.
      }
    }
    for (const handler of subscribersRef.current.get("*") ?? []) {
      try {
        handler(event);
      } catch {
        // Same.
      }
    }
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLastEvent(null);
    // Emptying the feed also forgets what was in it: if the server replays those
    // events on the next connect, the user asked for a clean slate, not a
    // permanently blank list.
    seenRef.current = new Set();
  }, []);

  const clearBlocked = useCallback(() => setBlockedEvent(null), []);

  useEffect(() => {
    if (!isAuthenticated) {
      // Tear down on logout so a new user never sees the previous feed.
      closedByUsRef.current = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      socketRef.current?.close();
      socketRef.current = null;
      setConnected(false);
      setEvents([]);
      setLastEvent(null);
      setBlockedEvent(null);
      seenRef.current = new Set();
      return;
    }

    closedByUsRef.current = false;
    attemptsRef.current = 0;
    let disposed = false;

    const connect = () => {
      if (disposed || closedByUsRef.current) return;

      const token = getToken();
      if (!token) return;

      let socket: WebSocket;
      try {
        socket = new WebSocket(buildWebSocketUrl(token));
      } catch {
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        if (disposed) return;
        attemptsRef.current = 0;
        setConnected(true);
      };

      socket.onmessage = (message) => {
        if (disposed) return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(String(message.data));
        } catch {
          return;
        }
        const event = parseAppEvent(parsed);
        if (!event) return;

        // A frame we already hold is the server replaying its history, not
        // something that just happened: it must not append to the feed, nor
        // re-run the invalidations and subscribers it already ran once.
        const key = eventKey(event);
        const seen = seenRef.current;
        if (seen.has(key)) return;
        seen.add(key);
        if (seen.size > MAX_EVENTS) {
          // Sets iterate in insertion order, so the oldest key belongs to the
          // event the feed drops in the very same update below.
          const oldest = seen.values().next().value;
          if (oldest !== undefined) seen.delete(oldest);
        }

        setEvents((previous) => {
          const next = [...previous, event];
          return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next;
        });
        setLastEvent(event);

        if (event.name === "automation.blocked") {
          setBlockedEvent(event);
        } else if (event.name === "automation.started") {
          setBlockedEvent(null);
        }

        invalidateForEvent(queryClient, event);
        dispatch(event);
      };

      socket.onerror = () => {
        if (disposed) return;
        setConnected(false);
      };

      socket.onclose = () => {
        if (disposed) return;
        setConnected(false);
        socketRef.current = null;
        if (!closedByUsRef.current) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (disposed || closedByUsRef.current) return;
      if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) return;
      const delay = backoffDelay(attemptsRef.current, 1000, 30_000);
      attemptsRef.current += 1;
      reconnectTimerRef.current = window.setTimeout(connect, delay);
    };

    // A tab that comes back from sleep should not wait out the backoff.
    const handleVisibility = () => {
      if (document.visibilityState !== "visible") return;
      if (socketRef.current || closedByUsRef.current) return;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      attemptsRef.current = 0;
      connect();
    };

    connect();
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      disposed = true;
      closedByUsRef.current = true;
      document.removeEventListener("visibilitychange", handleVisibility);
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        socket.onopen = null;
        socket.close();
      }
      setConnected(false);
    };
  }, [isAuthenticated, queryClient, dispatch]);

  const value = useMemo<EventsContextValue>(
    () => ({
      events,
      connected,
      lastEvent,
      blockedEvent,
      clearBlocked,
      clearEvents,
      subscribe,
    }),
    [events, connected, lastEvent, blockedEvent, clearBlocked, clearEvents, subscribe],
  );

  return <EventsContext.Provider value={value}>{children}</EventsContext.Provider>;
}

export function useEvents(): EventsContextValue {
  const context = useContext(EventsContext);
  if (!context) {
    throw new Error("useEvents must be used inside an EventsProvider.");
  }
  return context;
}

/** Runs `handler` for every matching event; re-subscribes when `handler` changes. */
export function useEventSubscription(
  name: EventName | "*",
  handler: EventHandler,
): void {
  const { subscribe } = useEvents();
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(
    () => subscribe(name, (event) => handlerRef.current(event)),
    [name, subscribe],
  );
}

/** Newest-first slice of the feed, for compact activity widgets. */
export function useRecentEvents(limit = 20): AppEvent[] {
  const { events } = useEvents();
  return useMemo(() => events.slice(-limit).reverse(), [events, limit]);
}
