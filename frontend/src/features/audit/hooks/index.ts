"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchTrail } from "../services";

export function useTrail(limit = 50, offset = 0) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["audit", { limit, offset }],
    queryFn: () => fetchTrail(limit, offset),
    // Reading the trail is itself recorded, so it changes on every visit.
    staleTime: 0,
  });

  return {
    events: data?.items ?? [],
    total: data?.total ?? 0,
    hasMore: data?.has_more ?? false,
    error,
    isLoading,
  };
}
