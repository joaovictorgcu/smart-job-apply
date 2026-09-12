/**
 * Administrative endpoints.
 *
 * Every call here 403s for a session without the admin role — the frontend's
 * route guard is convenience, and this is the layer that reflects the real
 * protection. Nothing in these payloads carries a resume, a cover letter or a
 * credential; see backend/app/schemas/admin.py.
 */

import { buildQuery } from "@/lib/utils";
import { api } from "@/services/client";
import type {
  AdminActivityEntry,
  AdminErrorEntry,
  AdminJobInsights,
  AdminOverview,
  AdminPeriodQuery,
  AdminUserQuery,
  AdminUserRow,
  Page,
  SystemHealth,
} from "@/types/api";

/** The period triple every endpoint below accepts, in one place. */
function periodParams(
  query: AdminPeriodQuery,
): Record<string, string | number | boolean | null | undefined> {
  return { period: query.period, start: query.start, end: query.end };
}

/** GET /api/admin/overview — the whole dashboard in one request. */
export function fetchOverview(
  query: AdminPeriodQuery & { refresh?: boolean } = {},
  signal?: AbortSignal,
): Promise<AdminOverview> {
  const search = buildQuery({
    ...periodParams(query),
    // Only sent when true: the backend serves a short-lived cache otherwise, and
    // "Atualizar dados" is the one action that should skip it.
    refresh: query.refresh ? true : undefined,
  });
  return api.get<AdminOverview>(`/admin/overview${search}`, { signal });
}

/** GET /api/admin/users */
export function listUsers(
  query: AdminUserQuery = {},
  signal?: AbortSignal,
): Promise<Page<AdminUserRow>> {
  const search = buildQuery({
    ...periodParams(query),
    search: query.search || undefined,
    filter: query.filter && query.filter !== "all" ? query.filter : undefined,
    limit: query.limit,
    offset: query.offset,
  });
  return api.get<Page<AdminUserRow>>(`/admin/users${search}`, { signal });
}

/** GET /api/admin/jobs */
export function fetchJobInsights(
  query: AdminPeriodQuery = {},
  signal?: AbortSignal,
): Promise<AdminJobInsights> {
  return api.get<AdminJobInsights>(`/admin/jobs${buildQuery(periodParams(query))}`, { signal });
}

/** GET /api/admin/errors */
export function listErrors(
  query: AdminPeriodQuery & { limit?: number } = {},
  signal?: AbortSignal,
): Promise<AdminErrorEntry[]> {
  const search = buildQuery({ ...periodParams(query), limit: query.limit });
  return api.get<AdminErrorEntry[]>(`/admin/errors${search}`, { signal });
}

/** GET /api/admin/activity */
export function listActivity(
  query: AdminPeriodQuery & { limit?: number } = {},
  signal?: AbortSignal,
): Promise<AdminActivityEntry[]> {
  const search = buildQuery({ ...periodParams(query), limit: query.limit });
  return api.get<AdminActivityEntry[]>(`/admin/activity${search}`, { signal });
}

/** GET /api/admin/health — the operator's view, not the public liveness probe. */
export function fetchSystemHealth(signal?: AbortSignal): Promise<SystemHealth> {
  return api.get<SystemHealth>("/admin/health", { signal });
}
