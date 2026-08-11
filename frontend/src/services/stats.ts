import { api } from "@/services/client";
import type { DashboardStats } from "@/types/api";

/** GET /api/stats */
export function fetchStats(signal?: AbortSignal): Promise<DashboardStats> {
  return api.get<DashboardStats>("/stats", { signal });
}
