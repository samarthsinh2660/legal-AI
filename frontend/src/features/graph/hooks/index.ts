"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchNeighbourhood, searchDocuments } from "../services";

export function useNeighbourhood(
  documentId: string | null,
  hops: number,
  limit: number,
) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["graph", documentId, hops, limit],
    queryFn: () => fetchNeighbourhood(documentId!, hops, limit),
    enabled: Boolean(documentId),
    // The corpus only changes when an ingest runs, which is never during
    // a reading session.
    staleTime: 10 * 60 * 1000,
  });

  return {
    nodes: data?.nodes ?? [],
    edges: data?.edges ?? [],
    truncated: data?.truncated ?? false,
    error,
    isLoading,
  };
}

export function useDocumentSearch(query: string) {
  const trimmed = query.trim();
  const { data, error, isLoading } = useQuery({
    queryKey: ["graph-search", trimmed],
    queryFn: () => searchDocuments(trimmed),
    // One letter matches most of the corpus and tells the reader nothing.
    enabled: trimmed.length >= 3,
    staleTime: 5 * 60 * 1000,
  });

  return { hits: data ?? [], error, isLoading };
}
