"use client";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/molecules/empty-state";
import { LoadingRow } from "@/components/molecules/loading";
import { useTrail } from "../hooks";
import { EventRow } from "./event-row";

/** Organism: uses `useTrail`, so it owns loading, empty and error. */
export function AuditTrail() {
  const { events, total, error, isLoading } = useTrail();

  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="mb-6">
        <h1 className="text-title">Activity</h1>
        <p className="mt-1.5 text-lg text-ink-variant">
          Everything this account has done, newest first — including
          anything that was refused.
        </p>
        <p className="mt-2 text-sm text-ink-muted">
          Your questions and answers are not recorded here. They live in the
          chat itself; this is a record of what was opened, not what was said.
        </p>
      </div>

      {!isLoading && !error && total > 0 && (
        <p className="mono mb-3 text-sm text-ink-muted">{total} events</p>
      )}

      <Card className="gap-0 divide-y divide-line overflow-hidden p-0">
        {isLoading &&
          Array.from({ length: 4 }).map((_, index) => <LoadingRow key={index} />)}

        {!isLoading && error && (
          <EmptyState message="Could not load your activity. Refresh to try again." />
        )}

        {!isLoading && !error && events.length === 0 && (
          <EmptyState message="Nothing recorded yet." />
        )}

        {!isLoading &&
          !error &&
          events.map((event) => (
            <EventRow key={event.event_id} event={event} />
          ))}
      </Card>
    </div>
  );
}
