"use client";

import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { useDocumentSearch } from "../hooks";
import type { SearchHit } from "../types";

/**
 * Organism: uses `useDocumentSearch`, so it owns the loading and empty
 * states. The graph needs an anchor and the corpus is 48,800 nodes -- a
 * list is not an option, so search is the way in.
 */
export function AnchorSearch({
  query,
  onQueryChange,
  onPick,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  onPick: (hit: SearchHit) => void;
}) {
  const { hits, isLoading } = useDocumentSearch(query);
  const searching = query.trim().length >= 3;

  return (
    <div className="relative">
      <div className="flex items-center gap-2 rounded border border-transparent bg-surface-sunken px-3 py-2 transition-colors duration-[120ms] ease-out focus-within:border-primary focus-within:bg-surface-card">
        <Search className="size-4 shrink-0 text-ink-muted" />
        <Input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Find a judgment or statute to centre on…"
          className="h-auto border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
      </div>

      {searching && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-line bg-surface-card shadow-2">
          {isLoading && (
            <p className="px-4 py-3 text-sm text-ink-muted">Searching…</p>
          )}
          {!isLoading && hits.length === 0 && (
            <p className="px-4 py-3 text-sm text-ink-muted">
              Nothing in the corpus matches that.
            </p>
          )}
          {hits.map((hit) => (
            <button
              key={hit.document_id}
              type="button"
              onClick={() => onPick(hit)}
              className="block w-full px-4 py-3 text-left transition-colors duration-[120ms] ease-out hover:bg-surface-sunken"
            >
              <span className="line-clamp-1 font-serif text-sm font-bold text-ink">
                {hit.title}
              </span>
              <span className="mono mt-1 block text-xs text-ink-muted">
                {hit.citation ?? hit.court ?? hit.kind}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
