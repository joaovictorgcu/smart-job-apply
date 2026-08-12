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
import * as tailoringService from "@/services/tailoring";
import type { ApiError } from "@/services/client";
import type {
  AIStatus,
  Application,
  ApplicationCard,
  ApplicationDetail,
  ApplicationEvent,
  ApplicationListQuery,
  ApplicationOutcome,
  ApplicationUpdate,
  AutomationRun,
  DashboardStats,
  OutcomeStats,
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
  TailoredResume,
  UserSettings,
  UserSettingsUpdate,
} from "@/types/api";

export const queryKeys = {
  me: () => ["me"] as const,

  profile: () => ["profile"] as const,
  settings: () => ["settings"] as const,
  aiStatus: () => ["ai", "status"] as const,
  tailoredResume: (jobId: number) => ["ai", "tailored-cv", jobId] as const,
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
  board: () => ["applications", "board"] as const,
  outcomeStats: () => ["stats", "outcomes"] as const,

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
      options?.onSuccess?.(data, vars, context);
    },
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
