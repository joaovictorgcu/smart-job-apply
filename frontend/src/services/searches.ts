import { api } from "@/services/client";
import type { Search, SearchCreate, SearchUpdate } from "@/types/api";

/** GET /api/searches */
export function listSearches(signal?: AbortSignal): Promise<Search[]> {
  return api.get<Search[]>("/searches", { signal });
}

/** POST /api/searches */
export function createSearch(payload: SearchCreate): Promise<Search> {
  return api.post<Search>("/searches", payload);
}

/** PATCH /api/searches/{id} */
export function updateSearch(id: number, payload: SearchUpdate): Promise<Search> {
  return api.patch<Search>(`/searches/${id}`, payload);
}

/** DELETE /api/searches/{id} */
export async function deleteSearch(id: number): Promise<void> {
  await api.delete<null>(`/searches/${id}`);
}
