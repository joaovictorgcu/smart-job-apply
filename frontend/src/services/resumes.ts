import { api } from "@/services/client";
import type { ApplicationResume, ResumeDocument } from "@/types/api";

/** GET /api/applications/{id}/resume — 404 when the application has no version yet. */
export function fetchApplicationResume(
  applicationId: number,
  signal?: AbortSignal,
): Promise<ApplicationResume> {
  return api.get<ApplicationResume>(`/applications/${applicationId}/resume`, { signal });
}

/**
 * POST /api/applications/{id}/resume — derive this application's version from the
 * master resume as it stands now.
 *
 * Also the way back: re-deriving discards the edits made to *this* version and
 * starts over from the profile. It never touches another application.
 */
export function deriveApplicationResume(
  applicationId: number,
): Promise<ApplicationResume> {
  return api.post<ApplicationResume>(`/applications/${applicationId}/resume`);
}

/**
 * PATCH /api/applications/{id}/resume — save edits to this application's version.
 *
 * The master resume is left untouched. The server refuses an edit that changes
 * an experience's company, role or period.
 */
export function updateApplicationResume(
  applicationId: number,
  document: ResumeDocument,
): Promise<ApplicationResume> {
  return api.patch<ApplicationResume>(`/applications/${applicationId}/resume`, { document });
}
