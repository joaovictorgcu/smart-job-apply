import { api } from "@/services/client";
import { buildQuery } from "@/lib/utils";
import type { Job, JobDetail, JobListQuery, Page } from "@/types/api";

/** GET /api/jobs?status=&min_score=&search_id=&limit=&offset= */
export function listJobs(
  query: JobListQuery = {},
  signal?: AbortSignal,
): Promise<Page<Job>> {
  const search = buildQuery({
    status: query.status,
    min_score: query.min_score,
    search_id: query.search_id,
    limit: query.limit,
    offset: query.offset,
  });
  return api.get<Page<Job>>(`/jobs${search}`, { signal });
}

/** GET /api/jobs/{id} */
export function fetchJob(id: number, signal?: AbortSignal): Promise<JobDetail> {
  return api.get<JobDetail>(`/jobs/${id}`, { signal });
}

/** POST /api/jobs/{id}/skip */
export function skipJob(id: number): Promise<Job> {
  return api.post<Job>(`/jobs/${id}/skip`);
}

/** POST /api/jobs/{id}/analyze — AI scoring only; never submits anything. */
export function analyzeJob(id: number): Promise<Job> {
  return api.post<Job>(`/jobs/${id}/analyze`);
}
