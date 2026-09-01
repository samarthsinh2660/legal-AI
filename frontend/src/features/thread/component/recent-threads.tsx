"use client";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/molecules/empty-state";
import { LoadingRow } from "@/components/molecules/loading";
import { useThreads } from "../hooks";
import { ThreadRow } from "./thread-row";

/** Organism: uses `useThreads`, so it owns loading, empty and error. */
export function RecentThreads({ limit = 5 }: { limit?: number }) {
  const { threads, error, isLoading } = useThreads(limit);

  return (
    <Card className="gap-0 divide-y divide-line overflow-hidden p-0">
      {isLoading &&
        Array.from({ length: 3 }).map((_, index) => <LoadingRow key={index} />)}

      {/* A failed fetch must not render as "no research yet" -- the two
          mean opposite things to someone looking for their work. */}
      {!isLoading && error && (
        <EmptyState message="Could not load your research. Refresh to try again." />
      )}

      {!isLoading && !error && threads.length === 0 && (
        <EmptyState message="No research yet. Ask your first question above." />
      )}

      {!isLoading &&
        !error &&
        threads.map((thread) => (
          <ThreadRow key={thread.thread_id} thread={thread} />
        ))}
    </Card>
  );
}
