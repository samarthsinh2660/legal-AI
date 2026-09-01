"use client";

import { useQuery } from "@tanstack/react-query";

import { search } from "../services";
import { SearchKind } from "../types";

export function useSearch(query: string, kind: SearchKind) {
  const trimmed = query.trim();
  const { data, error, isLoading, isFetching } = useQuery({
    queryKey: ["search", trimmed, kind],
    queryFn: () => search(trimmed, kind),
    // One or two letters match most of the corpus and tell nobody anything.
    enabled: trimmed.length >= 3,
    // The corpus only changes when an ingest runs, never mid-session.
    staleTime: 5 * 60 * 1000,
  });

  return { results: data ?? [], error, isLoading, isFetching };
}
