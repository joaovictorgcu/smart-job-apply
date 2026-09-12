/**
 * Shared TanStack Query layer.
 *
 * `queryKeys` is the single registry of cache keys; the live-event provider
 * invalidates against it, so keys must never be written inline elsewhere.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseMutationResult,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query";

import * as adminService from "@/services/admin";
import * as applicationsService from "@/services/applications";
import * as automationService from "@/services/automation";
import * as jobsService from "@/services/jobs";
import * as preferencesService from "@/services/preferences";
import * as profileService from "@/services/profile";
import * as resumesService from "@/services/resumes";
import * as searchesService from "@/services/searches";
import * as statsService from "@/services/stats";
import * as tailoringService from "@/services/tailoring";
import type { ApiError } from "@/services/client";
import type {
  AdminActivityEntry,
  AdminErrorEntry,
  AdminJobInsights,
  AdminOverview,
  AdminPeriodQuery,
  AdminUserQuery,
  AdminUserRow,
  AICredentialResult,
  AIProviderOption,
  AIStatus,
  Application,
  ApplicationCard,
  ApplicationDetail,
  ApplicationEvent,
  ApplicationListQuery,
  ApplicationOutcome,
  ApplicationResume,
  ApplicationResumeUpdate,
  ApplicationUpdate,
  AutomationRun,
  DashboardStats,
  Experience,
  ExperienceCreate,
  ExperienceUpdate,
  IntakeApplied,
  IntakeApply,
  JobPreferences,
  JobPreferencesUpdate,
  MasterResume,
  OutcomeStats,
  ResumeVersionSummary,
  SegmentStats,
  Job,
  JobDetail,
  JobListQuery,
  Message,
  Page,
  PrepareRequest,
  PreviewResponse,
  Profile,
  ProfileUpdate,
  ResumeIntake,
  Search,
  SearchCreate,
  SearchRunRequest,
  SearchUpdate,
  SessionStatus,
  SystemHealth,
  TailoredResume,
  UserSettings,
  UserSettingsUpdate,
} from "@/types/api";

export const queryKeys = {
  me: () => ["me"] as const,

  profile: () => ["profile"] as const,
  // Prefix of `experiences`, so invalidating the profile also refreshes the
  // structured half of the master resume that lives next to it.
  experiences: () => ["profile", "experiences"] as const,
  settings: () => ["settings"] as const,
  aiProviders: () => ["settings", "ai-providers"] as const,
  preferences: () => ["preferences"] as const,
  aiStatus: () => ["ai", "status"] as const,
  tailoredResume: (jobId: number) => ["ai", "tailored-cv", jobId] as const,
  health: () => ["health"] as const,

  // Prefix over the master resume, the version list and every application's
  // copy: a master edit changes the staleness of all of them at once, so they
  // are invalidated together.
  resumes: () => ["resumes"] as const,
  masterResume: () => ["resumes", "master"] as const,
  resumeVersions: () => ["resumes", "versions"] as const,
  applicationResume: (applicationId: number) =>
    ["resumes", "application", applicationId] as const,

  searches: () => ["searches"] as const,

  jobs: () => ["jobs"] as const,
  jobList: (query: JobListQuery = {}) => ["jobs", "list", query] as const,
  job: (id: number) => ["jobs", "detail", id] as const,

  applications: () => ["applications"] as const,
  applicationList: (query: ApplicationListQuery = {}) =>
    ["applications", "list", query] as const,
  application: (id: number) => ["applications", "detail", id] as const,
  applicationEvents: (id: number) => ["applications", "events", id] as const,
  board: () => ["applications", "board"] as const,
  outcomeStats: () => ["stats", "outcomes"] as const,
  segmentStats: () => ["stats", "segments"] as const,

  automation: () => ["automation"] as const,
  session: () => ["automation", "session"] as const,
  // Prefix over every runs list: `runs(limit)` appends the limit, so invalidating
  // `runs()` alone would miss `runs(8)` and leave the caller's list stale.
  runsAll: () => ["automation", "runs"] as const,
  runs: (limit?: number) => ["automation", "runs", limit ?? null] as const,
  run: (id: number) => ["automation", "run", id] as const,

  stats: () => ["stats"] as const,

  // The admin panel's own subtree. `admin()` is the prefix of every key below,
  // so the panel's refresh button invalidates all of them at once — and
  // `queryClient.clear()` on logout drops platform-wide data with the rest.
  admin: () => ["admin"] as const,
  adminOverview: (query: AdminPeriodQuery = {}) => ["admin", "overview", query] as const,
  adminUsers: (query: AdminUserQuery = {}) => ["admin", "users", query] as const,
  adminJobs: (query: AdminPeriodQuery = {}) => ["admin", "jobs", query] as const,
  adminErrors: (query: AdminPeriodQuery & { limit?: number } = {}) =>
    ["admin", "errors", query] as const,
  adminActivity: (query: AdminPeriodQuery & { limit?: number } = {}) =>
    ["admin", "activity", query] as const,
  adminHealth: () => ["admin", "health"] as const,
} as const;

type QueryOpts<T> = Omit<UseQueryOptions<T, ApiError>, "queryKey" | "queryFn">;
type MutationOpts<TData, TVars> = Omit<
  UseMutationOptions<TData, ApiError, TVars>,
  "mutationFn"
>;

/*
 * Mutation hooks own their cache maintenance. Caller options are spread FIRST
 * and `options?.onSuccess` is invoked from the hook's own handler, so a caller
 * adding a toast can never accidentally replace the setQueryData/invalidate
 * calls — spreading the options after the handler did exactly that.
 */

/* -------------------------------------------------------------------------- */
/* Profile, settings, AI                                                      */
/* -------------------------------------------------------------------------- */

export function useProfile(options?: QueryOpts<Profile>): UseQueryResult<Profile, ApiError> {
  return useQuery<Profile, ApiError>({
    queryKey: queryKeys.profile(),
    queryFn: ({ signal }) => profileService.fetchProfile(signal),
    ...options,
  });
}

export function useUpdateProfile(
  options?: MutationOpts<Profile, ProfileUpdate>,
): UseMutationResult<Profile, ApiError, ProfileUpdate> {
  const client = useQueryClient();
  return useMutation<Profile, ApiError, ProfileUpdate>({
    mutationFn: (payload) => profileService.updateProfile(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.profile(), data);
      // The skills and the summary are part of the master resume, so editing
      // them moves its fingerprint: every derived copy has to re-answer whether
      // it is stale. It never rewrites them — that is the whole point.
      void client.invalidateQueries({ queryKey: queryKeys.resumes() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useUploadResume(
  options?: MutationOpts<Profile, File>,
): UseMutationResult<Profile, ApiError, File> {
  const client = useQueryClient();
  return useMutation<Profile, ApiError, File>({
    mutationFn: (file) => profileService.uploadResume(file),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.profile(), data);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/**
 * Read an uploaded CV (or the stored resume text) into a proposal.
 *
 * A mutation rather than a query on purpose: it is an action the user takes,
 * and re-running it on window focus would re-upload a file. Passing `null`
 * reads the resume text already on the profile.
 */
export function useReadResumeIntake(
  options?: MutationOpts<ResumeIntake, File | null>,
): UseMutationResult<ResumeIntake, ApiError, File | null> {
  const client = useQueryClient();
  return useMutation<ResumeIntake, ApiError, File | null>({
    mutationFn: (file) =>
      file ? profileService.readResumeIntake(file) : profileService.readStoredResumeIntake(),
    ...options,
    onSuccess: (data, vars, context) => {
      // An upload stores the file, so the profile's `resume_filename` moved
      // even though not one profile field the user typed did.
      if (vars) void client.invalidateQueries({ queryKey: queryKeys.profile() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useApplyResumeIntake(
  options?: MutationOpts<IntakeApplied, IntakeApply>,
): UseMutationResult<IntakeApplied, ApiError, IntakeApply> {
  const client = useQueryClient();
  return useMutation<IntakeApplied, ApiError, IntakeApply>({
    mutationFn: (payload) => profileService.applyResumeIntake(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.profile(), data.profile);
      void client.invalidateQueries({ queryKey: queryKeys.experiences() });
      // New positions move the master resume's fingerprint, so every derived
      // copy has to re-answer whether it is stale.
      void client.invalidateQueries({ queryKey: queryKeys.resumes() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function usePreferences(
  options?: QueryOpts<JobPreferences>,
): UseQueryResult<JobPreferences, ApiError> {
  return useQuery<JobPreferences, ApiError>({
    queryKey: queryKeys.preferences(),
    queryFn: ({ signal }) => preferencesService.fetchPreferences(signal),
    ...options,
  });
}

export function useUpdatePreferences(
  options?: MutationOpts<JobPreferences, JobPreferencesUpdate>,
): UseMutationResult<JobPreferences, ApiError, JobPreferencesUpdate> {
  const client = useQueryClient();
  return useMutation<JobPreferences, ApiError, JobPreferencesUpdate>({
    mutationFn: (payload) => preferencesService.updatePreferences(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.preferences(), data);
      // Saving a role also creates or rewrites the managed saved search, so the
      // search list is stale even though nothing here touched it.
      void client.invalidateQueries({ queryKey: queryKeys.searches() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useSettings(
  options?: QueryOpts<UserSettings>,
): UseQueryResult<UserSettings, ApiError> {
  return useQuery<UserSettings, ApiError>({
    queryKey: queryKeys.settings(),
    queryFn: ({ signal }) => profileService.fetchSettings(signal),
    ...options,
  });
}

export function useUpdateSettings(
  options?: MutationOpts<UserSettings, UserSettingsUpdate>,
): UseMutationResult<UserSettings, ApiError, UserSettingsUpdate> {
  const client = useQueryClient();
  return useMutation<UserSettings, ApiError, UserSettingsUpdate>({
    mutationFn: (payload) => profileService.updateSettings(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.settings(), data);
      // Caps and dry-run live in the session banner too.
      void client.invalidateQueries({ queryKey: queryKeys.session() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
      // Whether AI can run is now an answer about this account: storing a key
      // turns it on, clearing one can turn it off.
      void client.invalidateQueries({ queryKey: queryKeys.aiStatus() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useAIProviders(
  options?: QueryOpts<AIProviderOption[]>,
): UseQueryResult<AIProviderOption[], ApiError> {
  return useQuery<AIProviderOption[], ApiError>({
    queryKey: queryKeys.aiProviders(),
    queryFn: ({ signal }) => profileService.fetchAIProviders(signal),
    // The list changes when the server is upgraded, not while a form is open.
    staleTime: Infinity,
    ...options,
  });
}

export function useTestAICredentials(
  options?: MutationOpts<AICredentialResult, { provider?: string; api_key?: string }>,
): UseMutationResult<AICredentialResult, ApiError, { provider?: string; api_key?: string }> {
  return useMutation<AICredentialResult, ApiError, { provider?: string; api_key?: string }>({
    mutationFn: (payload) => profileService.testAICredentials(payload),
    ...options,
  });
}

export function useAIStatus(
  options?: QueryOpts<AIStatus>,
): UseQueryResult<AIStatus, ApiError> {
  return useQuery<AIStatus, ApiError>({
    queryKey: queryKeys.aiStatus(),
    queryFn: ({ signal }) => profileService.fetchAIStatus(signal),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useGenerateCoverLetter(
  options?: MutationOpts<{ content: string; language: string }, number>,
): UseMutationResult<{ content: string; language: string }, ApiError, number> {
  return useMutation<{ content: string; language: string }, ApiError, number>({
    mutationFn: (jobId) => profileService.generateCoverLetter(jobId),
    ...options,
  });
}

/**
 * The tailored resume for one job. A missing draft is a normal state (the user
 * has not generated one yet), so a 404 resolves to `null` rather than an error.
 */
export function useTailoredResume(
  jobId: number,
  options?: QueryOpts<TailoredResume | null>,
): UseQueryResult<TailoredResume | null, ApiError> {
  return useQuery<TailoredResume | null, ApiError>({
    queryKey: queryKeys.tailoredResume(jobId),
    queryFn: async ({ signal }) => {
      try {
        return await tailoringService.fetchTailoredResume(jobId, signal);
      } catch (error) {
        if ((error as { status?: number })?.status === 404) return null;
        throw error;
      }
    },
    ...options,
  });
}

export function useTailorResume(
  jobId: number,
  options?: MutationOpts<TailoredResume, void>,
): UseMutationResult<TailoredResume, ApiError, void> {
  const client = useQueryClient();
  return useMutation<TailoredResume, ApiError, void>({
    mutationFn: () => tailoringService.createTailoredResume(jobId),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.tailoredResume(jobId), data);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useUpdateTailoredResume(
  jobId: number,
  options?: MutationOpts<TailoredResume, string>,
): UseMutationResult<TailoredResume, ApiError, string> {
  const client = useQueryClient();
  return useMutation<TailoredResume, ApiError, string>({
    mutationFn: (content) => tailoringService.updateTailoredResume(jobId, content),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.tailoredResume(jobId), data);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Resumes: the master one, and one adapted copy per application              */
/* -------------------------------------------------------------------------- */

export function useMasterResume(
  options?: QueryOpts<MasterResume>,
): UseQueryResult<MasterResume, ApiError> {
  return useQuery<MasterResume, ApiError>({
    queryKey: queryKeys.masterResume(),
    queryFn: ({ signal }) => resumesService.fetchMasterResume(signal),
    ...options,
  });
}

export function useResumeVersions(
  options?: QueryOpts<ResumeVersionSummary[]>,
): UseQueryResult<ResumeVersionSummary[], ApiError> {
  return useQuery<ResumeVersionSummary[], ApiError>({
    queryKey: queryKeys.resumeVersions(),
    queryFn: ({ signal }) => resumesService.listResumeVersions(signal),
    ...options,
  });
}

/**
 * The resume one application is using.
 *
 * A missing copy is a normal state — an application created before this feature
 * has no honest snapshot — so a 404 resolves to `null` rather than an error, the
 * same way `useTailoredResume` treats an ungenerated draft.
 */
export function useApplicationResume(
  applicationId: number,
  options?: QueryOpts<ApplicationResume | null>,
): UseQueryResult<ApplicationResume | null, ApiError> {
  return useQuery<ApplicationResume | null, ApiError>({
    queryKey: queryKeys.applicationResume(applicationId),
    queryFn: async ({ signal }) => {
      try {
        return await resumesService.fetchApplicationResume(applicationId, signal);
      } catch (error) {
        if ((error as { status?: number })?.status === 404) return null;
        throw error;
      }
    },
    enabled: Number.isFinite(applicationId) && applicationId > 0,
    ...options,
  });
}

/** Derive this application's copy again. Touches no other application. */
export function useAdaptApplicationResume(
  applicationId: number,
  options?: MutationOpts<ApplicationResume, void>,
): UseMutationResult<ApplicationResume, ApiError, void> {
  const client = useQueryClient();
  return useMutation<ApplicationResume, ApiError, void>({
    mutationFn: () => resumesService.adaptApplicationResume(applicationId),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.applicationResume(applicationId), data);
      void client.invalidateQueries({ queryKey: queryKeys.resumeVersions() });
      // Adapting writes an event to the application's own trail.
      void client.invalidateQueries({ queryKey: queryKeys.application(applicationId) });
      void client.invalidateQueries({ queryKey: queryKeys.applicationEvents(applicationId) });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/** Save edits to one application's copy. The master resume is never written. */
export function useUpdateApplicationResume(
  applicationId: number,
  options?: MutationOpts<ApplicationResume, ApplicationResumeUpdate>,
): UseMutationResult<ApplicationResume, ApiError, ApplicationResumeUpdate> {
  const client = useQueryClient();
  return useMutation<ApplicationResume, ApiError, ApplicationResumeUpdate>({
    mutationFn: (payload) => resumesService.updateApplicationResume(applicationId, payload),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.applicationResume(applicationId), data);
      void client.invalidateQueries({ queryKey: queryKeys.resumeVersions() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useExperiences(
  options?: QueryOpts<Experience[]>,
): UseQueryResult<Experience[], ApiError> {
  return useQuery<Experience[], ApiError>({
    queryKey: queryKeys.experiences(),
    queryFn: ({ signal }) => resumesService.listExperiences(signal),
    ...options,
  });
}

/*
 * The three experience mutations share their cache maintenance: writing the
 * master resume changes its fingerprint, so the version list and every open
 * application copy have to re-answer whether they are stale. None of them
 * rewrites a copy's content, which is the isolation rule the backend enforces.
 */
function invalidateMaster(client: ReturnType<typeof useQueryClient>): void {
  void client.invalidateQueries({ queryKey: queryKeys.experiences() });
  void client.invalidateQueries({ queryKey: queryKeys.resumes() });
}

export function useCreateExperience(
  options?: MutationOpts<Experience, ExperienceCreate>,
): UseMutationResult<Experience, ApiError, ExperienceCreate> {
  const client = useQueryClient();
  return useMutation<Experience, ApiError, ExperienceCreate>({
    mutationFn: (payload) => resumesService.createExperience(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      invalidateMaster(client);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useUpdateExperience(
  options?: MutationOpts<Experience, { id: number; payload: ExperienceUpdate }>,
): UseMutationResult<Experience, ApiError, { id: number; payload: ExperienceUpdate }> {
  const client = useQueryClient();
  return useMutation<Experience, ApiError, { id: number; payload: ExperienceUpdate }>({
    mutationFn: ({ id, payload }) => resumesService.updateExperience(id, payload),
    ...options,
    onSuccess: (data, vars, context) => {
      invalidateMaster(client);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useDeleteExperience(
  options?: MutationOpts<void, number>,
): UseMutationResult<void, ApiError, number> {
  const client = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) => resumesService.deleteExperience(id),
    ...options,
    onSuccess: (data, vars, context) => {
      invalidateMaster(client);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Searches                                                                   */
/* -------------------------------------------------------------------------- */

export function useSearches(
  options?: QueryOpts<Search[]>,
): UseQueryResult<Search[], ApiError> {
  return useQuery<Search[], ApiError>({
    queryKey: queryKeys.searches(),
    queryFn: ({ signal }) => searchesService.listSearches(signal),
    ...options,
  });
}

export function useCreateSearch(
  options?: MutationOpts<Search, SearchCreate>,
): UseMutationResult<Search, ApiError, SearchCreate> {
  const client = useQueryClient();
  return useMutation<Search, ApiError, SearchCreate>({
    mutationFn: (payload) => searchesService.createSearch(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      void client.invalidateQueries({ queryKey: queryKeys.searches() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useUpdateSearch(
  options?: MutationOpts<Search, { id: number; payload: SearchUpdate }>,
): UseMutationResult<Search, ApiError, { id: number; payload: SearchUpdate }> {
  const client = useQueryClient();
  return useMutation<Search, ApiError, { id: number; payload: SearchUpdate }>({
    mutationFn: ({ id, payload }) => searchesService.updateSearch(id, payload),
    ...options,
    onSuccess: (data, vars, context) => {
      void client.invalidateQueries({ queryKey: queryKeys.searches() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useDeleteSearch(
  options?: MutationOpts<void, number>,
): UseMutationResult<void, ApiError, number> {
  const client = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) => searchesService.deleteSearch(id),
    ...options,
    onSuccess: (data, vars, context) => {
      void client.invalidateQueries({ queryKey: queryKeys.searches() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Jobs                                                                       */
/* -------------------------------------------------------------------------- */

export function useJobs(
  query: JobListQuery = {},
  options?: QueryOpts<Page<Job>>,
): UseQueryResult<Page<Job>, ApiError> {
  return useQuery<Page<Job>, ApiError>({
    queryKey: queryKeys.jobList(query),
    queryFn: ({ signal }) => jobsService.listJobs(query, signal),
    ...options,
  });
}

export function useJob(
  id: number,
  options?: QueryOpts<JobDetail>,
): UseQueryResult<JobDetail, ApiError> {
  return useQuery<JobDetail, ApiError>({
    queryKey: queryKeys.job(id),
    queryFn: ({ signal }) => jobsService.fetchJob(id, signal),
    enabled: Number.isFinite(id) && id > 0,
    ...options,
  });
}

export function useSkipJob(
  options?: MutationOpts<Job, number>,
): UseMutationResult<Job, ApiError, number> {
  const client = useQueryClient();
  return useMutation<Job, ApiError, number>({
    mutationFn: (id) => jobsService.skipJob(id),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData<JobDetail | undefined>(queryKeys.job(data.id), (previous) =>
        previous ? { ...previous, ...data } : undefined,
      );
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useAnalyzeJob(
  options?: MutationOpts<Job, number>,
): UseMutationResult<Job, ApiError, number> {
  const client = useQueryClient();
  return useMutation<Job, ApiError, number>({
    mutationFn: (id) => jobsService.analyzeJob(id),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData<JobDetail | undefined>(queryKeys.job(data.id), (previous) =>
        previous ? { ...previous, ...data } : undefined,
      );
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Applications                                                               */
/* -------------------------------------------------------------------------- */

export function useApplications(
  query: ApplicationListQuery = {},
  options?: QueryOpts<Page<Application>>,
): UseQueryResult<Page<Application>, ApiError> {
  return useQuery<Page<Application>, ApiError>({
    queryKey: queryKeys.applicationList(query),
    queryFn: ({ signal }) => applicationsService.listApplications(query, signal),
    ...options,
  });
}

export function useApplication(
  id: number,
  options?: QueryOpts<ApplicationDetail>,
): UseQueryResult<ApplicationDetail, ApiError> {
  return useQuery<ApplicationDetail, ApiError>({
    queryKey: queryKeys.application(id),
    queryFn: ({ signal }) => applicationsService.fetchApplication(id, signal),
    enabled: Number.isFinite(id) && id > 0,
    ...options,
  });
}

export function useApplicationEvents(
  id: number,
  options?: QueryOpts<ApplicationEvent[]>,
): UseQueryResult<ApplicationEvent[], ApiError> {
  return useQuery<ApplicationEvent[], ApiError>({
    queryKey: queryKeys.applicationEvents(id),
    queryFn: ({ signal }) => applicationsService.fetchApplicationEvents(id, signal),
    enabled: Number.isFinite(id) && id > 0,
    ...options,
  });
}

export function useUpdateApplication(
  options?: MutationOpts<ApplicationDetail, { id: number; payload: ApplicationUpdate }>,
): UseMutationResult<
  ApplicationDetail,
  ApiError,
  { id: number; payload: ApplicationUpdate }
> {
  const client = useQueryClient();
  return useMutation<ApplicationDetail, ApiError, { id: number; payload: ApplicationUpdate }>({
    mutationFn: ({ id, payload }) => applicationsService.updateApplication(id, payload),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applicationEvents(data.id) });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/**
 * The submit mutation. Assisted mode: callers must gate this behind an explicit,
 * separate user confirmation — never fire it as a side effect of another action.
 */
export function useSubmitApplication(
  options?: MutationOpts<ApplicationDetail, number>,
): UseMutationResult<ApplicationDetail, ApiError, number> {
  const client = useQueryClient();
  return useMutation<ApplicationDetail, ApiError, number>({
    mutationFn: (id) => applicationsService.submitApplication(id),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.session() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/**
 * Record an application the user made on the company's own site.
 *
 * Not a submission and not a quieter route to one: it writes down what already
 * happened elsewhere. It invalidates the same caches as a submission because the
 * *consequences* are the same — the application joins the board and the stats.
 */
export function useMarkApplied(
  options?: MutationOpts<ApplicationDetail, { id: number; note?: string | null }>,
): UseMutationResult<ApplicationDetail, ApiError, { id: number; note?: string | null }> {
  const client = useQueryClient();
  return useMutation<ApplicationDetail, ApiError, { id: number; note?: string | null }>({
    mutationFn: ({ id, note }) => applicationsService.markApplicationApplied(id, note),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      // `stats()` is the prefix of the outcome and segment keys, so this covers
      // the analytics that only now start seeing this application.
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useDiscardApplication(
  options?: MutationOpts<ApplicationDetail, number>,
): UseMutationResult<ApplicationDetail, ApiError, number> {
  const client = useQueryClient();
  return useMutation<ApplicationDetail, ApiError, number>({
    mutationFn: (id) => applicationsService.discardApplication(id),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Pipeline board                                                             */
/* -------------------------------------------------------------------------- */

export function useBoard(
  options?: QueryOpts<ApplicationCard[]>,
): UseQueryResult<ApplicationCard[], ApiError> {
  return useQuery<ApplicationCard[], ApiError>({
    queryKey: queryKeys.board(),
    queryFn: ({ signal }) => applicationsService.fetchBoard(signal),
    ...options,
  });
}

interface OutcomeVars {
  id: number;
  outcome: ApplicationOutcome;
  note?: string | null;
}

interface BoardContext {
  previous?: ApplicationCard[];
}

/**
 * Move a card to a new outcome, optimistically.
 *
 * The board cache is updated before the request returns so a drag feels instant;
 * a failure rolls back to the snapshot. This hook owns the board/analytics cache,
 * so it composes any caller `onSuccess`/`onError` rather than letting them replace
 * the rollback and invalidation.
 */
export function useUpdateOutcome(
  options?: MutationOpts<ApplicationDetail, OutcomeVars>,
): UseMutationResult<ApplicationDetail, ApiError, OutcomeVars> {
  const client = useQueryClient();
  return useMutation<ApplicationDetail, ApiError, OutcomeVars, BoardContext>({
    mutationFn: ({ id, outcome, note }) =>
      applicationsService.updateOutcome(id, outcome, note),
    onMutate: async ({ id, outcome }) => {
      await client.cancelQueries({ queryKey: queryKeys.board() });
      const previous = client.getQueryData<ApplicationCard[]>(queryKeys.board());
      if (previous) {
        client.setQueryData<ApplicationCard[]>(
          queryKeys.board(),
          previous.map((card) =>
            card.id === id
              ? { ...card, outcome, outcome_updated_at: new Date().toISOString() }
              : card,
          ),
        );
      }
      return { previous };
    },
    onError: (error, vars, context) => {
      if (context?.previous) {
        client.setQueryData(queryKeys.board(), context.previous);
      }
      options?.onError?.(error, vars, context);
    },
    onSuccess: (data, vars, context) => {
      options?.onSuccess?.(data, vars, context);
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.board() });
      void client.invalidateQueries({ queryKey: queryKeys.outcomeStats() });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
    },
  });
}

export function useOutcomeStats(
  options?: QueryOpts<OutcomeStats>,
): UseQueryResult<OutcomeStats, ApiError> {
  return useQuery<OutcomeStats, ApiError>({
    queryKey: queryKeys.outcomeStats(),
    queryFn: ({ signal }) => statsService.fetchOutcomeStats(signal),
    ...options,
  });
}

export function useSegmentStats(
  options?: QueryOpts<SegmentStats>,
): UseQueryResult<SegmentStats, ApiError> {
  return useQuery<SegmentStats, ApiError>({
    queryKey: queryKeys.segmentStats(),
    queryFn: ({ signal }) => statsService.fetchSegmentStats(signal),
    ...options,
  });
}

/* -------------------------------------------------------------------------- */
/* Automation                                                                 */
/* -------------------------------------------------------------------------- */

export function useSessionStatus(
  options?: QueryOpts<SessionStatus>,
): UseQueryResult<SessionStatus, ApiError> {
  return useQuery<SessionStatus, ApiError>({
    queryKey: queryKeys.session(),
    queryFn: ({ signal }) => automationService.fetchSessionStatus(signal),
    // The session.status event refreshes this; the interval is only a safety net.
    refetchInterval: 30_000,
    ...options,
  });
}

export function useStartSession(
  options?: MutationOpts<SessionStatus, void>,
): UseMutationResult<SessionStatus, ApiError, void> {
  const client = useQueryClient();
  return useMutation<SessionStatus, ApiError, void>({
    mutationFn: () => automationService.startSession(),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.session(), data);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useStopSession(
  options?: MutationOpts<SessionStatus, void>,
): UseMutationResult<SessionStatus, ApiError, void> {
  const client = useQueryClient();
  return useMutation<SessionStatus, ApiError, void>({
    mutationFn: () => automationService.stopSession(),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.session(), data);
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useRunSearch(
  options?: MutationOpts<AutomationRun, SearchRunRequest>,
): UseMutationResult<AutomationRun, ApiError, SearchRunRequest> {
  const client = useQueryClient();
  return useMutation<AutomationRun, ApiError, SearchRunRequest>({
    mutationFn: (payload) => automationService.runSearch(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      void client.invalidateQueries({ queryKey: queryKeys.automation() });
      void client.invalidateQueries({ queryKey: queryKeys.searches() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/** Read-only count the user must see before any form is filled. */
export function usePreviewJobs(
  options?: MutationOpts<PreviewResponse, PrepareRequest>,
): UseMutationResult<PreviewResponse, ApiError, PrepareRequest> {
  return useMutation<PreviewResponse, ApiError, PrepareRequest>({
    mutationFn: (payload) => automationService.previewJobs(payload),
    ...options,
  });
}

/** Fills forms and stops at review. Does NOT submit. */
export function usePrepareApplications(
  options?: MutationOpts<AutomationRun, PrepareRequest>,
): UseMutationResult<AutomationRun, ApiError, PrepareRequest> {
  const client = useQueryClient();
  return useMutation<AutomationRun, ApiError, PrepareRequest>({
    mutationFn: (payload) => automationService.prepareApplications(payload),
    ...options,
    onSuccess: (data, vars, context) => {
      void client.invalidateQueries({ queryKey: queryKeys.automation() });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/** Kill switch. */
export function useStopAutomation(
  options?: MutationOpts<Message, void>,
): UseMutationResult<Message, ApiError, void> {
  const client = useQueryClient();
  return useMutation<Message, ApiError, void>({
    mutationFn: () => automationService.stopAutomation(),
    ...options,
    onSuccess: (data, vars, context) => {
      void client.invalidateQueries({ queryKey: queryKeys.automation() });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

export function useRuns(
  limit?: number,
  options?: QueryOpts<AutomationRun[]>,
): UseQueryResult<AutomationRun[], ApiError> {
  return useQuery<AutomationRun[], ApiError>({
    queryKey: queryKeys.runs(limit),
    queryFn: ({ signal }) => automationService.listRuns(limit, signal),
    ...options,
  });
}

export function useRun(
  id: number,
  options?: QueryOpts<AutomationRun>,
): UseQueryResult<AutomationRun, ApiError> {
  return useQuery<AutomationRun, ApiError>({
    queryKey: queryKeys.run(id),
    queryFn: ({ signal }) => automationService.fetchRun(id, signal),
    enabled: Number.isFinite(id) && id > 0,
    ...options,
  });
}

/* -------------------------------------------------------------------------- */
/* Stats                                                                      */
/* -------------------------------------------------------------------------- */

export function useStats(
  options?: QueryOpts<DashboardStats>,
): UseQueryResult<DashboardStats, ApiError> {
  return useQuery<DashboardStats, ApiError>({
    queryKey: queryKeys.stats(),
    queryFn: ({ signal }) => statsService.fetchStats(signal),
    ...options,
  });
}

/* -------------------------------------------------------------------------- */
/* Admin panel                                                                */
/* -------------------------------------------------------------------------- */

/**
 * The whole admin dashboard, from one request.
 *
 * A single query rather than one per panel: every section shares the period, and
 * fanning out would let the tiles disagree about what "now" is. The backend
 * caches it for ~30s, so `staleTime` matches — refetching sooner would only
 * hand back the same snapshot.
 */
export function useAdminOverview(
  query: AdminPeriodQuery = {},
  options?: QueryOpts<AdminOverview>,
): UseQueryResult<AdminOverview, ApiError> {
  return useQuery<AdminOverview, ApiError>({
    queryKey: queryKeys.adminOverview(query),
    queryFn: ({ signal }) => adminService.fetchOverview(query, signal),
    staleTime: 30_000,
    ...options,
  });
}

export function useAdminUsers(
  query: AdminUserQuery = {},
  options?: QueryOpts<Page<AdminUserRow>>,
): UseQueryResult<Page<AdminUserRow>, ApiError> {
  return useQuery<Page<AdminUserRow>, ApiError>({
    queryKey: queryKeys.adminUsers(query),
    queryFn: ({ signal }) => adminService.listUsers(query, signal),
    ...options,
  });
}

export function useAdminJobInsights(
  query: AdminPeriodQuery = {},
  options?: QueryOpts<AdminJobInsights>,
): UseQueryResult<AdminJobInsights, ApiError> {
  return useQuery<AdminJobInsights, ApiError>({
    queryKey: queryKeys.adminJobs(query),
    queryFn: ({ signal }) => adminService.fetchJobInsights(query, signal),
    ...options,
  });
}

export function useAdminErrors(
  query: AdminPeriodQuery & { limit?: number } = {},
  options?: QueryOpts<AdminErrorEntry[]>,
): UseQueryResult<AdminErrorEntry[], ApiError> {
  return useQuery<AdminErrorEntry[], ApiError>({
    queryKey: queryKeys.adminErrors(query),
    queryFn: ({ signal }) => adminService.listErrors(query, signal),
    ...options,
  });
}

export function useAdminActivity(
  query: AdminPeriodQuery & { limit?: number } = {},
  options?: QueryOpts<AdminActivityEntry[]>,
): UseQueryResult<AdminActivityEntry[], ApiError> {
  return useQuery<AdminActivityEntry[], ApiError>({
    queryKey: queryKeys.adminActivity(query),
    queryFn: ({ signal }) => adminService.listActivity(query, signal),
    ...options,
  });
}

export function useAdminHealth(
  options?: QueryOpts<SystemHealth>,
): UseQueryResult<SystemHealth, ApiError> {
  return useQuery<SystemHealth, ApiError>({
    queryKey: queryKeys.adminHealth(),
    queryFn: ({ signal }) => adminService.fetchSystemHealth(signal),
    ...options,
  });
}

/**
 * "Atualizar dados": recompute server-side, then replace the cached snapshot.
 *
 * A mutation rather than `refetch()` because it is an explicit action with a
 * side effect on the server's cache, and it must show a pending state while the
 * aggregates run.
 */
export function useRefreshAdminOverview(
  query: AdminPeriodQuery = {},
  options?: MutationOpts<AdminOverview, void>,
): UseMutationResult<AdminOverview, ApiError, void> {
  const client = useQueryClient();
  return useMutation<AdminOverview, ApiError, void>({
    mutationFn: () => adminService.fetchOverview({ ...query, refresh: true }),
    ...options,
    onSuccess: (data, vars, context) => {
      client.setQueryData(queryKeys.adminOverview(query), data);
      // The other admin screens read the same rows through their own endpoints.
      void client.invalidateQueries({ queryKey: queryKeys.adminUsers() });
      void client.invalidateQueries({ queryKey: queryKeys.adminJobs() });
      void client.invalidateQueries({ queryKey: queryKeys.adminErrors() });
      void client.invalidateQueries({ queryKey: queryKeys.adminActivity() });
      void client.invalidateQueries({ queryKey: queryKeys.adminHealth() });
      options?.onSuccess?.(data, vars, context);
    },
  });
}

/** Escape hatch for pages that need ad-hoc cache invalidation. */
export function useInvalidate() {
  const client = useQueryClient();
  return {
    client,
    all: () => client.invalidateQueries(),
    jobs: () => client.invalidateQueries({ queryKey: queryKeys.jobs() }),
    applications: () => client.invalidateQueries({ queryKey: queryKeys.applications() }),
    automation: () => client.invalidateQueries({ queryKey: queryKeys.automation() }),
    stats: () => client.invalidateQueries({ queryKey: queryKeys.stats() }),
    admin: () => client.invalidateQueries({ queryKey: queryKeys.admin() }),
  };
}
