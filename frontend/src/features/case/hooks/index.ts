"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Page } from "@/types/common";
import { createCase, fetchCases } from "../services";
import type { Case, NewCase } from "../types";

export const caseKeys = {
  all: ["cases"] as const,
  page: (limit: number, offset: number) =>
    [...caseKeys.all, { limit, offset }] as const,
};

export function useCases(limit = 20, offset = 0) {
  const { data, error, isLoading } = useQuery({
    queryKey: caseKeys.page(limit, offset),
    queryFn: () => fetchCases(limit, offset),
    staleTime: 60_000,
  });

  return {
    cases: data?.items ?? [],
    total: data?.total ?? 0,
    error,
    isLoading,
  };
}

export function useCreateCase() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (payload: NewCase) => createCase(payload),
    onSuccess: (created) => {
      // Prepend rather than refetch: the list is newest-first and this is
      // the newest.
      queryClient.setQueriesData<Page<Case>>(
        { queryKey: caseKeys.all },
        (old) =>
          old
            ? { ...old, items: [created, ...old.items], total: old.total + 1 }
            : old,
      );
    },
  });

  return { caseCreate: mutateAsync, isCreating: isPending };
}
