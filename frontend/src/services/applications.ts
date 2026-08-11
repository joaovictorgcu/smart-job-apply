import { api } from "@/services/client";
import { buildQuery } from "@/lib/utils";
import type {
  Application,
  ApplicationDetail,
  ApplicationEvent,
  ApplicationListQuery,
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
