import { z } from "zod";

import { apiClient } from "@/lib/api";
import {
  NeighbourhoodSchema,
  SearchHitSchema,
  type Neighbourhood,
  type SearchHit,
} from "../types";

export async function fetchNeighbourhood(
  documentId: string,
  hops: number,
  limit: number,
): Promise<Neighbourhood> {
  const data = await apiClient.get<unknown>(
    `/graph/${encodeURIComponent(documentId)}?hops=${hops}&limit=${limit}`,
  );
  return NeighbourhoodSchema.parse(data);
}

/** The graph needs an anchor, and the corpus is far too large to list.
 *  Search is how the reader finds one. */
export async function searchDocuments(
  query: string,
  limit = 8,
): Promise<SearchHit[]> {
  const data = await apiClient.get<unknown>(
    `/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
  return z.array(SearchHitSchema).parse(data);
}
