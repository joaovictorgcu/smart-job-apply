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

import * as applicationsService from "@/services/applications";
import * as automationService from "@/services/automation";
import * as jobsService from "@/services/jobs";
import * as profileService from "@/services/profile";
import * as searchesService from "@/services/searches";
import * as statsService from "@/services/stats";
import type { ApiError } from "@/services/client";
import type {
  AIStatus,
  Application,
  ApplicationDetail,
  ApplicationEvent,
  ApplicationListQuery,
  ApplicationUpdate,
  AutomationRun,
  DashboardStats,
  Job,
  JobDetail,
  JobListQuery,
  Message,
  Page,
  PrepareRequest,
  PreviewResponse,
  Profile,
  ProfileUpdate,
  Search,
  SearchCreate,
  SearchRunRequest,
  SearchUpdate,
  SessionStatus,
  UserSettings,
  UserSettingsUpdate,
} from "@/types/api";

export const queryKeys = {
  me: () => ["me"] as const,

  profile: () => ["profile"] as const,
  settings: () => ["settings"] as const,
  aiStatus: () => ["ai", "status"] as const,
  health: () => ["health"] as const,

  searches: () => ["searches"] as const,

  jobs: () => ["jobs"] as const,
  jobList: (query: JobListQuery = {}) => ["jobs", "list", query] as const,
  job: (id: number) => ["jobs", "detail", id] as const,

  applications: () => ["applications"] as const,
  applicationList: (query: ApplicationListQuery = {}) =>
    ["applications", "list", query] as const,
  application: (id: number) => ["applications", "detail", id] as const,
  applicationEvents: (id: number) => ["applications", "events", id] as const,

  automation: () => ["automation"] as const,
  session: () => ["automation", "session"] as const,
  // Prefix over every runs list: `runs(limit)` appends the limit, so invalidating
  // `runs()` alone would miss `runs(8)` and leave the caller's list stale.
  runsAll: () => ["automation", "runs"] as const,
  runs: (limit?: number) => ["automation", "runs", limit ?? null] as const,
  run: (id: number) => ["automation", "run", id] as const,

  stats: () => ["stats"] as const,
} as const;

type QueryOpts<T> = Omit<UseQueryOptions<T, ApiError>, "queryKey" | "queryFn">;
type MutationOpts<TData, TVars> = Omit<
  UseMutationOptions<TData, ApiError, TVars>,
  "mutationFn"
>;

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
    onSuccess: (data) => client.setQueryData(queryKeys.profile(), data),
    ...options,
  });
}

export function useUploadResume(
  options?: MutationOpts<Profile, File>,
): UseMutationResult<Profile, ApiError, File> {
  const client = useQueryClient();
  return useMutation<Profile, ApiError, File>({
    mutationFn: (file) => profileService.uploadResume(file),
    onSuccess: (data) => client.setQueryData(queryKeys.profile(), data),
    ...options,
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
    onSuccess: (data) => {
      client.setQueryData(queryKeys.settings(), data);
      // Caps and dry-run live in the session banner too.
      void client.invalidateQueries({ queryKey: queryKeys.session() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
    },
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
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.searches() }),
    ...options,
  });
}

export function useUpdateSearch(
  options?: MutationOpts<Search, { id: number; payload: SearchUpdate }>,
): UseMutationResult<Search, ApiError, { id: number; payload: SearchUpdate }> {
  const client = useQueryClient();
  return useMutation<Search, ApiError, { id: number; payload: SearchUpdate }>({
    mutationFn: ({ id, payload }) => searchesService.updateSearch(id, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.searches() }),
    ...options,
  });
}

export function useDeleteSearch(
  options?: MutationOpts<void, number>,
): UseMutationResult<void, ApiError, number> {
  const client = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: (id) => searchesService.deleteSearch(id),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.searches() }),
    ...options,
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
    onSuccess: (data) => {
      client.setQueryData<JobDetail | undefined>(queryKeys.job(data.id), (previous) =>
        previous ? { ...previous, ...data } : undefined,
      );
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
    },
    ...options,
  });
}

export function useAnalyzeJob(
  options?: MutationOpts<Job, number>,
): UseMutationResult<Job, ApiError, number> {
  const client = useQueryClient();
  return useMutation<Job, ApiError, number>({
    mutationFn: (id) => jobsService.analyzeJob(id),
    onSuccess: (data) => {
      client.setQueryData<JobDetail | undefined>(queryKeys.job(data.id), (previous) =>
        previous ? { ...previous, ...data } : undefined,
      );
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
    },
    ...options,
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
    onSuccess: (data) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applicationEvents(data.id) });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
    },
    ...options,
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
    onSuccess: (data) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.session() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
    },
    ...options,
  });
}

export function useDiscardApplication(
  options?: MutationOpts<ApplicationDetail, number>,
): UseMutationResult<ApplicationDetail, ApiError, number> {
  const client = useQueryClient();
  return useMutation<ApplicationDetail, ApiError, number>({
    mutationFn: (id) => applicationsService.discardApplication(id),
    onSuccess: (data) => {
      client.setQueryData(queryKeys.application(data.id), data);
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
      void client.invalidateQueries({ queryKey: queryKeys.stats() });
    },
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
    onSuccess: (data) => client.setQueryData(queryKeys.session(), data),
    ...options,
  });
}

export function useStopSession(
  options?: MutationOpts<SessionStatus, void>,
): UseMutationResult<SessionStatus, ApiError, void> {
  const client = useQueryClient();
  return useMutation<SessionStatus, ApiError, void>({
    mutationFn: () => automationService.stopSession(),
    onSuccess: (data) => client.setQueryData(queryKeys.session(), data),
    ...options,
  });
}

export function useRunSearch(
  options?: MutationOpts<AutomationRun, SearchRunRequest>,
): UseMutationResult<AutomationRun, ApiError, SearchRunRequest> {
  const client = useQueryClient();
  return useMutation<AutomationRun, ApiError, SearchRunRequest>({
    mutationFn: (payload) => automationService.runSearch(payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.automation() });
      void client.invalidateQueries({ queryKey: queryKeys.searches() });
    },
    ...options,
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
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.automation() });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
      void client.invalidateQueries({ queryKey: queryKeys.jobs() });
    },
    ...options,
  });
}

/** Kill switch. */
export function useStopAutomation(
  options?: MutationOpts<Message, void>,
): UseMutationResult<Message, ApiError, void> {
  const client = useQueryClient();
  return useMutation<Message, ApiError, void>({
    mutationFn: () => automationService.stopAutomation(),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.automation() });
      void client.invalidateQueries({ queryKey: queryKeys.applications() });
    },
    ...options,
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
  };
}
