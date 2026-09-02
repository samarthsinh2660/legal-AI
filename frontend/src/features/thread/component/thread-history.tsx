"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/molecules/empty-state";
import { LoadingRow } from "@/components/molecules/loading";
import { useThreads } from "../hooks";
import { ThreadRow } from "./thread-row";

const PER_PAGE = 20;

/**
 * Organism: uses `useThreads`, so it owns loading, empty and error.
 *
 * Paged rather than infinite. Paging is what the API offers (offset,
 * limit, has_more) and what someone looking for a particular past question
 * wants -- an infinite list gives no way back to where they were.
 *
 * Each row links into the thread, where the existing ask box continues the
 * conversation. Nothing here needs its own "continue" control.
 */
export function ThreadHistory() {
  const [offset, setOffset] = useState(0);
  const { threads, total, hasMore, error, isLoading } = useThreads(
    PER_PAGE,
    offset,
  );

  const first = total === 0 ? 0 : offset + 1;
  const last = offset + threads.length;

  return (
    <div className="flex flex-col gap-4">
      <Card className="gap-0 divide-y divide-line overflow-hidden p-0">
        {isLoading &&
          Array.from({ length: 5 }).map((_, index) => (
            <LoadingRow key={index} />
          ))}

        {/* A failed fetch must not render as "no research yet" -- the two
            mean opposite things to someone looking for their work. */}
        {!isLoading && error && (
          <EmptyState message="Could not load your history. Refresh to try again." />
        )}

        {!isLoading && !error && threads.length === 0 && (
          <EmptyState
            message={
              offset === 0
                ? "No research yet. Start a new one and it will appear here."
                : "Nothing on this page."
            }
          />
        )}

        {!isLoading &&
          !error &&
          threads.map((thread) => (
            <ThreadRow key={thread.thread_id} thread={thread} />
          ))}
      </Card>

      {!isLoading && !error && total > 0 && (
        <div className="flex items-center justify-between">
          <p className="mono text-sm text-ink-muted">
            {first}–{last} of {total}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PER_PAGE))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              disabled={!hasMore}
              onClick={() => setOffset(offset + PER_PAGE)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
