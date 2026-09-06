"use client";

/** Core API hooks for threads. Shared by every component in the feature. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Page } from "@/types/common";
import {
  createThread,
  deleteThread,
  fetchDrafts,
  fetchMessages,
  fetchThread,
  fetchThreads,
  renameThread,
  startDraft,
} from "../services";
import type { Draft, Message, Thread } from "../types";

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
    // The backstop, not the mechanism. A run's progress and its end arrive
    // over the run stream; this covers the one case SSE cannot self-heal --
    // a proxy that holds the connection open and buffers it, so the browser
    // sees a healthy stream, never reconnects, and nothing reaches it. Only
    // while something is actually running.
    refetchInterval: (query) => (query.state.data?.active_run ? POLL_MS : false),
    // Polling stops on an unfocused tab by default, and waiting out a
    // two-minute answer in another tab is exactly what people do -- the
    // answer then landed only once they came back and looked.
    refetchIntervalInBackground: true,
  });
  return { thread, error, isLoading };
}

/** How often a backstop poll runs. See `useThread`. */
const POLL_MS = 15000;

export function useMessages(threadId: string) {
  const { data, error, isLoading, isFetching } = useQuery({
    queryKey: [...threadKeys.all, threadId, "messages"],
    queryFn: () => fetchMessages(threadId),
    enabled: Boolean(threadId),
    // Not polled. The run stream says when a turn is over, and the hook
    // watching it invalidates this query -- so a poll here would be asking
    // the same question a second way.
  });
  // `isFetching` covers the refetch after a run ends, when the reply exists
  // on the server and not yet here. Without it the screen has a moment
  // where the last message is a question with no run behind it, which is
  // the shape of a turn that died.
  return { messages: data ?? [], error, isLoading, isFetching };
}

export function useRenameThread() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      renameThread(threadId, title),
    onSuccess: (updated) => {
      queryClient.setQueriesData<Page<Thread>>(
        { queryKey: threadKeys.all },
        (old) =>
          old
            ? {
                ...old,
                items: old.items.map((thread) =>
                  thread.thread_id === updated.thread_id ? updated : thread,
                ),
              }
            : old,
      );
      queryClient.setQueryData([...threadKeys.all, updated.thread_id], updated);
    },
  });

  return { threadRename: mutateAsync, isRenaming: isPending };
}

export function useDeleteThread() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (threadId: string) => deleteThread(threadId),
    onSuccess: (_result, threadId) => {
      queryClient.setQueriesData<Page<Thread>>(
        { queryKey: threadKeys.all },
        (old) =>
          old
            ? {
                ...old,
                items: old.items.filter((t) => t.thread_id !== threadId),
                total: Math.max(0, old.total - 1),
              }
            : old,
      );
    },
  });

  return { threadDelete: mutateAsync, isDeleting: isPending };
}

/**
 * Documents drafted from this thread.
 *
 * Polls while one is being prepared, for the same reason the messages do:
 * the run is detached from the request, so it finishes and stores the file
 * whether or not this tab is watching.
 */
export function useDrafts(threadId: string) {
  const queryClient = useQueryClient();
  const key = [...threadKeys.all, threadId, "drafts"] as const;

  const { data, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => fetchDrafts(threadId),
    enabled: Boolean(threadId),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((draft) => draft.status === "running")
        ? POLL_MS
        : false,
    refetchIntervalInBackground: true,
  });

  const { mutateAsync, isPending, error } = useMutation({
    mutationFn: () => startDraft(threadId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  const drafts = data ?? [];
  return {
    drafts,
    isLoading,
    preparing: drafts.some((draft) => draft.status === "running") || isPending,
    startDraft: mutateAsync,
    startError: error instanceof Error ? error.message : null,
  };
}
