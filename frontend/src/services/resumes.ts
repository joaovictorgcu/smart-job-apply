/**
 * The master resume, and the copy each application carries.
 *
 * None of these calls reaches a model: the derivation is deterministic on the
 * backend (`app/domain/resume.py`), so adapting works with no API key configured.
 */

import { api } from "@/services/client";
import type {
  ApplicationResume,
  ApplicationResumeUpdate,
  Experience,
  ExperienceCreate,
  ExperienceUpdate,
  MasterResume,
  ResumeVersionSummary,
} from "@/types/api";

/** GET /api/resumes/master — the profile's text and skills plus the positions. */
export function fetchMasterResume(signal?: AbortSignal): Promise<MasterResume> {
  return api.get<MasterResume>("/resumes/master", { signal });
}

/** GET /api/resumes/versions — every application-specific version, newest first. */
export function listResumeVersions(signal?: AbortSignal): Promise<ResumeVersionSummary[]> {
  return api.get<ResumeVersionSummary[]>("/resumes/versions", { signal });
}

/** GET /api/resumes/applications/{id} — 404 when nothing was derived yet. */
export function fetchApplicationResume(
  applicationId: number,
  signal?: AbortSignal,
): Promise<ApplicationResume> {
  return api.get<ApplicationResume>(`/resumes/applications/${applicationId}`, { signal });
}

/**
 * POST /api/resumes/applications/{id} — derive this application's copy again.
 *
 * Replaces only this application's document and bumps its version. The master
 * resume and every sibling application are untouched.
 */
export function adaptApplicationResume(applicationId: number): Promise<ApplicationResume> {
  return api.post<ApplicationResume>(`/resumes/applications/${applicationId}`);
}

/** PATCH /api/resumes/applications/{id} — save edits to this copy, and only this one. */
export function updateApplicationResume(
  applicationId: number,
  payload: ApplicationResumeUpdate,
): Promise<ApplicationResume> {
  return api.patch<ApplicationResume>(`/resumes/applications/${applicationId}`, payload);
}

/* ------------------------------------------------------- master experiences */

export function listExperiences(signal?: AbortSignal): Promise<Experience[]> {
  return api.get<Experience[]>("/profile/experiences", { signal });
}

export function createExperience(payload: ExperienceCreate): Promise<Experience> {
  return api.post<Experience>("/profile/experiences", payload);
}

export function updateExperience(id: number, payload: ExperienceUpdate): Promise<Experience> {
  return api.patch<Experience>(`/profile/experiences/${id}`, payload);
}

export function deleteExperience(id: number): Promise<void> {
  return api.delete<void>(`/profile/experiences/${id}`);
}
