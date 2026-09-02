"use client";

import Link from "next/link";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/molecules/empty-state";
import { LoadingRow } from "@/components/molecules/loading";
import { useThreads } from "@/features/thread/hooks";
import { ThreadRow } from "@/features/thread/component/thread-row";

/**
 * Organism: the threads attached to this matter.
 *
 * There is no "threads for one case" route, so this filters the user's
 * threads by `case_id` client-side -- which means it can only see the page
 * it fetched.
 *
 * This is the one component that reaches across features, into `thread`.
 * That is deliberate: a matter showing its own research is inherently
 * cross-domain, and forking `ThreadRow` here would fork the rename and
 * delete behaviour with it. The guide's rule bans sharing *types* across
 * features (move those to `types/common`); reusing the organism that
 * already owns this row is the alternative to duplicating it.
 */
export function CaseThreads({ caseId }: { caseId: string }) {
  const { threads, error, isLoading } = useThreads(50);
  const mine = threads.filter((thread) => thread.case_id === caseId);

  return (
    <div>
      {isLoading && (
        <Card className="gap-0 p-0">
          {Array.from({ length: 2 }).map((_, index) => (
            <LoadingRow key={index} />
          ))}
        </Card>
      )}

      {!isLoading && error && (
        <EmptyState message="Could not load this matter's threads." />
      )}

      {!isLoading && !error && mine.length === 0 && (
        <div className="rounded-md border border-line bg-surface-card px-6 py-8 text-center">
          <p className="text-sm text-ink-muted">
            No research on this matter yet.
          </p>
          <Button asChild className="mt-4">
            <Link href={`/?case=${caseId}`}>
              <Plus className="size-4" />
              Start a thread on this case
            </Link>
          </Button>
        </div>
      )}

      {!isLoading && !error && mine.length > 0 && (
        <Card className="gap-0 divide-y divide-line overflow-hidden p-0">
          {mine.map((thread) => (
            <ThreadRow key={thread.thread_id} thread={thread} />
          ))}
        </Card>
      )}
    </div>
  );
}
