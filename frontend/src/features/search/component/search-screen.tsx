"use client";

import { Search as SearchIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/molecules/empty-state";
import { LoadingRow } from "@/components/molecules/loading";
import { cn } from "@/lib/utils";
import { useSearchForm } from "../hooks/useSearchForm";
import { SearchKind } from "../types";
import { ResultRow } from "./result-row";

const TABS = [
  { kind: SearchKind.All, label: "Everything" },
  { kind: SearchKind.Judgment, label: "Judgments" },
  { kind: SearchKind.Section, label: "Statutes" },
] as const;

/** Organism: owns the query and every state the fetch can be in. */
export function SearchScreen({ initialQuery }: { initialQuery?: string }) {
  const {
    results,
    error,
    isLoading,
    draft,
    setDraft,
    query,
    kind,
    setKind,
    submit,
  } = useSearchForm(initialQuery);

  const asked = query.trim().length >= 3;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="mb-6">
        <h1 className="text-title">Search the corpus</h1>
        <p className="mt-1.5 text-lg text-ink-variant">
          The same retrieval a research thread runs — so anything here is
          something the agents could find too.
        </p>
      </div>

      <div className="flex items-center gap-2 rounded border border-transparent bg-surface-sunken px-3 py-2.5 transition-colors duration-[120ms] ease-out focus-within:border-primary focus-within:bg-surface-card">
        <SearchIcon className="size-4 shrink-0 text-ink-muted" />
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && submit()}
          placeholder="Search judgments and statutes…"
          className="h-auto border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
      </div>

      <div className="mt-4 flex gap-6 border-b border-line">
        {TABS.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            onClick={() => setKind(tab.kind)}
            className={cn(
              "relative top-px border-b-2 border-transparent py-3 text-sm font-medium text-ink-muted transition-colors duration-[120ms] ease-out hover:text-ink",
              kind === tab.kind && "border-b-primary font-semibold text-primary",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {!asked && (
          <EmptyState message="Type at least three characters, then press Enter." />
        )}
        {asked && isLoading && (
          <Card className="gap-0 p-0">
            {Array.from({ length: 4 }).map((_, index) => (
              <LoadingRow key={index} />
            ))}
          </Card>
        )}
        {asked && !isLoading && error && (
          <EmptyState message="The search failed. Try again." />
        )}
        {asked && !isLoading && !error && results.length === 0 && (
          <EmptyState message="Nothing in the corpus matches that." />
        )}
        {asked && !isLoading && !error && results.length > 0 && (
          <Card className="gap-0 overflow-hidden p-0">
            {results.map((result) => (
              <ResultRow key={result.document_id} result={result} />
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}
