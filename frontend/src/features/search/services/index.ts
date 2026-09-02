import { z } from "zod";

import { apiClient } from "@/lib/api";
import { SearchResultSchema, type SearchKind, type SearchResult } from "../types";

export async function search(
  query: string,
  kind: SearchKind,
  limit = 20,
): Promise<SearchResult[]> {
  const data = await apiClient.get<unknown>(
    `/search?q=${encodeURIComponent(query)}&kind=${kind}&limit=${limit}`,
  );
  return z.array(SearchResultSchema).parse(data);
}
