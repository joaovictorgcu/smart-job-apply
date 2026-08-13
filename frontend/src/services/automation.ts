import { api } from "@/services/client";
import { buildQuery } from "@/lib/utils";
import type {
  AutomationRun,
  Message,
  PrepareRequest,
  PreviewResponse,
  SearchRunRequest,
  SessionStatus,
} from "@/types/api";

/** GET /api/automation/session */
export function fetchSessionStatus(signal?: AbortSignal): Promise<SessionStatus> {
  return api.get<SessionStatus>("/automation/session", { signal });
}

/** POST /api/automation/session/start — opens the visible browser for manual login. */
export function startSession(): Promise<SessionStatus> {
  return api.post<SessionStatus>("/automation/session/start");
}

/** POST /api/automation/session/stop */
export function stopSession(): Promise<SessionStatus> {
  return api.post<SessionStatus>("/automation/session/stop");
}

/** POST /api/automation/search — discovery plus optional AI scoring. Never submits. */
export function runSearch(payload: SearchRunRequest): Promise<AutomationRun> {
  return api.post<AutomationRun>("/automation/search", payload);
}

/**
 * POST /api/automation/preview
 *
 * Read-only dry count the user must see before anything is prepared.
 */
export function previewJobs(payload: PrepareRequest): Promise<PreviewResponse> {
  return api.post<PreviewResponse>("/automation/preview", payload);
}

/**
 * POST /api/automation/prepare
 *
 * Fills the Easy Apply form and stops at the review step. `confirmed: true` is
 * required by the backend and only means "the user saw the preview" — it is not
 * a submit approval; submitting is a separate, per-application action.
 */
export function prepareApplications(payload: PrepareRequest): Promise<AutomationRun> {
  return api.post<AutomationRun>("/automation/prepare", {
    ...payload,
    confirmed: true,
  });
}

/** POST /api/automation/stop — kill switch. */
export function stopAutomation(): Promise<Message> {
  return api.post<Message>("/automation/stop");
}

/** GET /api/automation/runs?limit= */
export function listRuns(limit?: number, signal?: AbortSignal): Promise<AutomationRun[]> {
  return api.get<AutomationRun[]>(`/automation/runs${buildQuery({ limit })}`, { signal });
}

/** GET /api/automation/runs/{id} */
export function fetchRun(id: number, signal?: AbortSignal): Promise<AutomationRun> {
  return api.get<AutomationRun>(`/automation/runs/${id}`, { signal });
}

/** POST /api/automation/runs/{id}/resume — pick an interrupted run back up. */
export function resumeRun(id: number): Promise<AutomationRun> {
  return api.post<AutomationRun>(`/automation/runs/${id}/resume`);
}
