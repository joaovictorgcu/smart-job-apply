import { api } from "@/services/client";
import type { ApplicationResume, ResumeStrategy, TailoredResume } from "@/types/api";

/** GET /api/ai/tailor-cv/{job_id} — 404 when no draft exists yet. */
export function fetchTailoredResume(
  jobId: number,
  signal?: AbortSignal,
): Promise<TailoredResume> {
  return api.get<TailoredResume>(`/ai/tailor-cv/${jobId}`, { signal });
}

/** POST /api/ai/tailor-cv/{job_id} — generate or regenerate. Never submits anything. */
export function createTailoredResume(jobId: number): Promise<TailoredResume> {
  return api.post<TailoredResume>(`/ai/tailor-cv/${jobId}`);
}

/** PATCH /api/ai/tailor-cv/{job_id} — save the user's edits. */
export function updateTailoredResume(
  jobId: number,
  content: string,
): Promise<TailoredResume> {
  return api.patch<TailoredResume>(`/ai/tailor-cv/${jobId}`, { content });
}

/*
 * One application's own version of the resume. Addressed by application id
 * rather than job id, because that is the thing the user is looking at — and
 * because a request can then only ever name one application's version, which is
 * what keeps editing one from touching any other.
 */

/** GET /api/applications/{id}/resume — 404 when this application has none yet. */
export function fetchApplicationResume(
  applicationId: number,
  signal?: AbortSignal,
): Promise<ApplicationResume> {
  return api.get<ApplicationResume>(`/applications/${applicationId}/resume`, {
    signal,
  });
}

/**
 * POST /api/applications/{id}/resume — derive (or re-derive) this version.
 *
 * Always builds from the master resume as it stands now, and freezes that
 * snapshot onto the version, so re-deriving is how a stale version is refreshed.
 */
export function createApplicationResume(
  applicationId: number,
  strategy: ResumeStrategy = "deterministic",
): Promise<ApplicationResume> {
  return api.post<ApplicationResume>(`/applications/${applicationId}/resume`, {
    strategy,
  });
}

/** PATCH /api/applications/{id}/resume — save edits to this version alone. */
export function updateApplicationResume(
  applicationId: number,
  content: string,
): Promise<ApplicationResume> {
  return api.patch<ApplicationResume>(`/applications/${applicationId}/resume`, {
    content,
  });
}
