/**
 * What kind of vacancy this account is looking for.
 *
 * Saving also keeps one managed saved search in step with the stated role, so
 * a new account never has to open the search form. That happens on the server;
 * nothing here needs to know about it beyond invalidating the search list.
 */

import { api } from "@/services/client";
import type { JobPreferences, JobPreferencesUpdate } from "@/types/api";

/** GET /api/preferences — empty on first access, which means "nothing ruled out". */
export function fetchPreferences(signal?: AbortSignal): Promise<JobPreferences> {
  return api.get<JobPreferences>("/preferences", { signal });
}

/** PUT /api/preferences — only the fields sent are touched. */
export function updatePreferences(payload: JobPreferencesUpdate): Promise<JobPreferences> {
  return api.put<JobPreferences>("/preferences", payload);
}
