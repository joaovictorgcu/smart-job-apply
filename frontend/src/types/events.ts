/**
 * Mirror of backend/app/observability/events.py.
 *
 * The backend serializes `Event` with `model_dump(mode="json")`, so `timestamp`
 * arrives as an ISO 8601 string.
 */

export type EventName =
  | "automation.started"
  | "automation.progress"
  | "automation.stopped"
  | "automation.error"
  | "automation.blocked"
  | "job.found"
  | "job.analyzed"
  | "application.started"
  | "application.awaiting_review"
  | "application.completed"
  | "session.status"
  | "log";

export type EventLevel = "info" | "warning" | "error" | "success";

export interface AppEvent {
  name: EventName;
  timestamp: string;
  run_id: number | null;
  job_id: number | null;
  application_id: number | null;
  message: string | null;
  level: EventLevel;
  data: Record<string, unknown>;
}

export const EVENT_NAMES: readonly EventName[] = [
  "automation.started",
  "automation.progress",
  "automation.stopped",
  "automation.error",
  "automation.blocked",
  "job.found",
  "job.analyzed",
  "application.started",
  "application.awaiting_review",
  "application.completed",
  "session.status",
  "log",
];

/** Events that mean the run halted on a security checkpoint and needs a human. */
export const BLOCKING_EVENTS: readonly EventName[] = ["automation.blocked"];

export function isEventName(value: unknown): value is EventName {
  return typeof value === "string" && (EVENT_NAMES as readonly string[]).includes(value);
}

/** Normalizes an untrusted WebSocket frame into an AppEvent, or null if unusable. */
export function parseAppEvent(raw: unknown): AppEvent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const candidate = raw as Record<string, unknown>;
  if (!isEventName(candidate.name)) return null;

  const level = candidate.level;
  return {
    name: candidate.name,
    timestamp:
      typeof candidate.timestamp === "string"
        ? candidate.timestamp
        : new Date().toISOString(),
    run_id: typeof candidate.run_id === "number" ? candidate.run_id : null,
    job_id: typeof candidate.job_id === "number" ? candidate.job_id : null,
    application_id:
      typeof candidate.application_id === "number" ? candidate.application_id : null,
    message: typeof candidate.message === "string" ? candidate.message : null,
    level:
      level === "warning" || level === "error" || level === "success" ? level : "info",
    data:
      typeof candidate.data === "object" && candidate.data !== null
        ? (candidate.data as Record<string, unknown>)
        : {},
  };
}
