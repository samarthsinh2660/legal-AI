import { apiClient } from "@/lib/api";
import { NeighbourhoodSchema, type Neighbourhood } from "../types";

export async function fetchNeighbourhood(
  documentId: string,
  limit: number,
): Promise<Neighbourhood> {
  const data = await apiClient.get<unknown>(
    `/graph/${encodeURIComponent(documentId)}?limit=${limit}`,
  );
  return NeighbourhoodSchema.parse(data);
}

/** One batch of a named slice. No anchor: a reader browses the graph
 *  before naming a document in it. */
export async function fetchOverview(
  view: string,
  offset: number,
  limit: number,
): Promise<Neighbourhood> {
  const data = await apiClient.get<unknown>(
    `/graph/overview?view=${encodeURIComponent(view)}`
    + `&offset=${offset}&limit=${limit}`,
  );
  return NeighbourhoodSchema.parse(data);
}
