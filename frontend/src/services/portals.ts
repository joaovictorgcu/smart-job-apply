import { api } from "@/services/client";
import type { PortalSearchResult } from "@/types/api";

/** POST /api/portals/search — loginless discovery on an external portal. */
export function searchPortal(
  portal: string,
  keywords: string,
  location?: string | null,
  limit = 25,
): Promise<PortalSearchResult> {
  return api.post<PortalSearchResult>("/portals/search", {
    portal,
    keywords,
    location: location || null,
    limit,
  });
}
