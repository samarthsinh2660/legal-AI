"use client";

/** Core API hooks for threads. Shared by every component in the feature. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Page } from "@/types/common";
import {
  createThread,
  fetchMessages,
  fetchThread,
  fetchThreads,
} from "../services";
import type { Thread } from "../types";

export const threadKeys = {
  all: ["threads"] as const,
  page: (limit: number, offset: number) =>
    [...threadKeys.all, { limit, offset }] as const,
};

export function useThreads(limit = 20, offset = 0) {
  const { data, error, isLoading } = useQuery({
    queryKey: threadKeys.page(limit, offset),
    queryFn: () => fetchThreads(limit, offset),
    // A thread's updated_at moves whenever the user sends a message, so
    // this list goes stale fast. Cheap query, short window.
    staleTime: 30_000,
  });

  return {
    // Never hand an undefined array to a component.
    threads: data?.items ?? [],
    total: data?.total ?? 0,
    hasMore: data?.has_more ?? false,
    error,
    isLoading,
  };
}

export function useCreateThread() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: ({ title, caseId }: { title?: string; caseId?: string }) =>
      createThread(title, caseId),

    onSuccess: (created) => {
      // Prepend to every cached page rather than refetching: the list is
      // ordered by updated_at, and a new thread is the newest.
      queryClient.setQueriesData<Page<Thread>>(
        { queryKey: threadKeys.all },
        (old) =>
          old
            ? { ...old, items: [created, ...old.items], total: old.total + 1 }
            : old,
      );
    },
  });

  return { threadCreate: mutateAsync, isCreating: isPending };
}

export function useThread(threadId: string) {
  const { data: thread, error, isLoading } = useQuery({
    queryKey: [...threadKeys.all, threadId],
    queryFn: () => fetchThread(threadId),
    enabled: Boolean(threadId),
  });
  return { thread, error, isLoading };
}

export function useMessages(threadId: string) {
  const { data, error, isLoading } = useQuery({
    queryKey: [...threadKeys.all, threadId, "messages"],
    queryFn: () => fetchMessages(threadId),
    enabled: Boolean(threadId),
  });
  return { messages: data ?? [], error, isLoading };
}
