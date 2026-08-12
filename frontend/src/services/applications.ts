import { api, API_BASE, ApiError, getToken } from "@/services/client";
import { buildQuery } from "@/lib/utils";
import type {
  Application,
  ApplicationCard,
  ApplicationDetail,
  ApplicationEvent,
  ApplicationListQuery,
  ApplicationOutcome,
  ApplicationUpdate,
  Page,
} from "@/types/api";

/** GET /api/applications?status=&limit=&offset= */
export function listApplications(
  query: ApplicationListQuery = {},
  signal?: AbortSignal,
): Promise<Page<Application>> {
  const search = buildQuery({
    status: query.status,
    limit: query.limit,
    offset: query.offset,
  });
  return api.get<Page<Application>>(`/applications${search}`, { signal });
}

/** GET /api/applications/{id} */
export function fetchApplication(
  id: number,
  signal?: AbortSignal,
): Promise<ApplicationDetail> {
  return api.get<ApplicationDetail>(`/applications/${id}`, { signal });
}

/** PATCH /api/applications/{id} — user edits during review. */
export function updateApplication(
  id: number,
  payload: ApplicationUpdate,
): Promise<ApplicationDetail> {
  return api.patch<ApplicationDetail>(`/applications/${id}`, payload);
}

/**
 * POST /api/applications/{id}/submit
 *
 * The only call in the whole app that can send a real LinkedIn application.
 * `confirm` is hard-coded to true here precisely so a caller cannot reach this
 * endpoint by accident: the UI must decide to invoke this specific function.
 */
export function submitApplication(id: number): Promise<ApplicationDetail> {
  return api.post<ApplicationDetail>(`/applications/${id}/submit`, { confirm: true });
}

/** POST /api/applications/{id}/discard */
export function discardApplication(id: number): Promise<ApplicationDetail> {
  return api.post<ApplicationDetail>(`/applications/${id}/discard`);
}

/** GET /api/applications/{id}/events */
export function fetchApplicationEvents(
  id: number,
  signal?: AbortSignal,
): Promise<ApplicationEvent[]> {
  return api.get<ApplicationEvent[]>(`/applications/${id}/events`, { signal });
}

/**
 * GET /api/applications/export — the full history as a CSV file download.
 *
 * Bypasses the JSON wrapper on purpose: the response is a blob handed straight
 * to the browser's download machinery.
 */
export async function downloadApplicationsCsv(): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}/applications/export`, { headers });
  if (!response.ok) {
    throw new ApiError(response.status, "Não foi possível exportar o CSV.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "candidaturas.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** GET /api/applications/board — submitted applications for the pipeline board. */
export function fetchBoard(signal?: AbortSignal): Promise<ApplicationCard[]> {
  return api.get<ApplicationCard[]>("/applications/board", { signal });
}

/** PATCH /api/applications/{id}/outcome — record what happened after applying. */
export function updateOutcome(
  id: number,
  outcome: ApplicationOutcome,
  note?: string | null,
): Promise<ApplicationDetail> {
  return api.patch<ApplicationDetail>(`/applications/${id}/outcome`, { outcome, note });
}
