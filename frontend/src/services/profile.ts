import { api } from "@/services/client";
import type {
  AIStatus,
  CoverLetterResponse,
  HealthResponse,
  IntakeApplied,
  IntakeApply,
  Profile,
  ProfileUpdate,
  ResumeIntake,
  UserSettings,
  UserSettingsUpdate,
} from "@/types/api";

/** GET /api/profile */
export function fetchProfile(signal?: AbortSignal): Promise<Profile> {
  return api.get<Profile>("/profile", { signal });
}

/** PUT /api/profile */
export function updateProfile(payload: ProfileUpdate): Promise<Profile> {
  return api.put<Profile>("/profile", payload);
}

/** POST /api/profile/resume — multipart, field name `file`, PDF only. */
export function uploadResume(file: File, signal?: AbortSignal): Promise<Profile> {
  return api.upload<Profile>("/profile/resume", file, { field: "file", signal });
}

/**
 * POST /api/profile/intake — read a CV and return what it says.
 *
 * Nothing about the profile is written. With a file, it is stored (that PDF is
 * what the application form attaches) and read; with none, the resume text
 * already on the profile is read instead.
 */
export function readResumeIntake(file: File, signal?: AbortSignal): Promise<ResumeIntake> {
  return api.upload<ResumeIntake>("/profile/intake", file, { field: "file", signal });
}

/** POST /api/profile/intake with no file — reads the stored resume text. */
export function readStoredResumeIntake(signal?: AbortSignal): Promise<ResumeIntake> {
  return api.post<ResumeIntake>("/profile/intake", undefined, { signal });
}

/** POST /api/profile/intake/apply — save the proposal the user confirmed. */
export function applyResumeIntake(payload: IntakeApply): Promise<IntakeApplied> {
  return api.post<IntakeApplied>("/profile/intake/apply", payload);
}

/** GET /api/settings */
export function fetchSettings(signal?: AbortSignal): Promise<UserSettings> {
  return api.get<UserSettings>("/settings", { signal });
}

/** PUT /api/settings */
export function updateSettings(payload: UserSettingsUpdate): Promise<UserSettings> {
  return api.put<UserSettings>("/settings", payload);
}

/** GET /api/ai/status */
export function fetchAIStatus(signal?: AbortSignal): Promise<AIStatus> {
  return api.get<AIStatus>("/ai/status", { signal });
}

/** POST /api/ai/cover-letter/{job_id} */
export function generateCoverLetter(jobId: number): Promise<CoverLetterResponse> {
  return api.post<CoverLetterResponse>(`/ai/cover-letter/${jobId}`);
}

/** GET /api/health */
export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return api.get<HealthResponse>("/health", { signal });
}
