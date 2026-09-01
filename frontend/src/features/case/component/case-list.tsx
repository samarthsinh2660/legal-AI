"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/molecules/empty-state";
import { useCases } from "../hooks";
import { CaseTile } from "./case-tile";
import { NewCaseForm } from "./new-case-form";

/** Organism: uses `useCases`, so it owns loading, empty and error. */
export function CaseList() {
  const { cases, error, isLoading } = useCases();
  const [creating, setCreating] = useState(false);

  return (
    <div className="mx-auto w-full max-w-5xl">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-title">Cases</h1>
          <p className="mt-1.5 text-lg text-ink-variant">
            A matter holds its documents, its findings and every thread about
            it.
          </p>
        </div>
        <Button onClick={() => setCreating((open) => !open)}>
          <Plus className="size-4" />
          New case
        </Button>
      </div>

      {creating && (
        <div className="mb-6">
          <NewCaseForm onCreated={() => setCreating(false)} />
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 rounded-md" />
          ))}
        </div>
      )}

      {/* A failed fetch must not read as "no cases" -- one means the work
          is missing, the other that it was never there. */}
      {!isLoading && error && (
        <EmptyState message="Could not load your cases. Refresh to try again." />
      )}

      {!isLoading && !error && cases.length === 0 && !creating && (
        <EmptyState message="No cases yet. Create one to keep a matter's research together." />
      )}

      {!isLoading && !error && cases.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cases.map((item) => (
            <CaseTile key={item.case_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
