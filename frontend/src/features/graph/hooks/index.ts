"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { fetchNeighbourhood, fetchOverview } from "../services";
import { BATCH } from "../types";

/**
 * A slice of the graph, one batch at a time.
 *
 * `useInfiniteQuery` rather than a page index: batches accumulate on the
 * canvas, so asking for more must add to what is drawn rather than
 * replace it.
 */
export function useOverview(view: string, enabled: boolean) {
  const { data, error, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ["graph", "overview", view],
      queryFn: ({ pageParam }) => fetchOverview(view, pageParam, BATCH),
      initialPageParam: 0,
      getNextPageParam: (last, all) =>
        last.truncated ? all.length * BATCH : undefined,
      enabled,
      // The corpus only changes when an ingest runs.
      staleTime: 10 * 60 * 1000,
    });

  const pages = data?.pages ?? [];
  // A node can appear in more than one batch only if the corpus changed
  // mid-scroll; drawing it twice would put two dots on one judgment.
  const seen = new Set<string>();
  const nodes = pages
    .flatMap((page) => page.nodes)
    .filter((node) => !seen.has(node.id) && seen.add(node.id));

  return {
    nodes,
    edges: pages.flatMap((page) => page.edges),
    // Only the first batch carries it; later ones send null.
    total: pages[0]?.total ?? null,
    truncated: Boolean(hasNextPage),
    loadMore: fetchNextPage,
    isLoadingMore: isFetchingNextPage,
    error,
    isLoading,
  };
}


export function useNeighbourhood(documentId: string | null, limit: number) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["graph", documentId, limit],
    queryFn: () => fetchNeighbourhood(documentId!, limit),
    enabled: Boolean(documentId),
    // The corpus only changes when an ingest runs, which is never during
    // a reading session.
    staleTime: 10 * 60 * 1000,
  });

  return {
    nodes: data?.nodes ?? [],
    edges: data?.edges ?? [],
    total: null,
    truncated: data?.truncated ?? false,
    error,
    isLoading,
  };
}
