import { api } from "@/services/client";
import type { TailoredResume } from "@/types/api";

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
