import { api } from "@/services/client";
import type { DashboardStats, OutcomeStats } from "@/types/api";

/** GET /api/stats */
export function fetchStats(signal?: AbortSignal): Promise<DashboardStats> {
  return api.get<DashboardStats>("/stats", { signal });
}

/** GET /api/stats/outcomes — interview rate by match-score band. */
export function fetchOutcomeStats(signal?: AbortSignal): Promise<OutcomeStats> {
  return api.get<OutcomeStats>("/stats/outcomes", { signal });
}
