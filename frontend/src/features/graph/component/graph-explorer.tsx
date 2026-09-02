"use client";

import { EmptyState } from "@/components/molecules/empty-state";
import { PageLoader } from "@/components/molecules/loading";
import { cn } from "@/lib/utils";
import { useGraphExplorer } from "../hooks/useGraphExplorer";
import { MAX_HOPS } from "../types";
import { AnchorSearch } from "./anchor-search";
import { GraphCanvas } from "./graph-canvas";

/** Organism: owns the anchor, the hop depth, and every state the fetch
 *  can be in. */
export function GraphExplorer({ initialAnchor }: { initialAnchor?: string }) {
  const {
    nodes,
    edges,
    truncated,
    error,
    isLoading,
    anchor,
    anchorLabel,
    query,
    setQuery,
    hops,
    setHops,
    pick,
  } = useGraphExplorer(initialAnchor);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="mb-6">
        <h1 className="text-title">Citation graph</h1>
        <p className="mt-1.5 text-lg text-ink-variant">
          What cites what, drawn from the corpus we hold. Read-only.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="min-w-72 flex-1">
          <AnchorSearch query={query} onQueryChange={setQuery} onPick={pick} />
        </div>

        <div className="flex items-center gap-1 rounded border border-line bg-surface-card p-1">
          {Array.from({ length: MAX_HOPS }, (_, index) => index + 1).map(
            (value) => (
              <button
                key={value}
                type="button"
                onClick={() => setHops(value)}
                className={cn(
                  "rounded-sm px-3 py-1.5 text-xs font-medium transition-colors duration-[120ms] ease-out",
                  hops === value
                    ? "bg-surface-tint text-primary"
                    : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
                )}
              >
                {value} hop{value > 1 ? "s" : ""}
              </button>
            ),
          )}
        </div>
      </div>

      {anchorLabel && (
        <p className="mb-3 text-sm text-ink-muted">
          Centred on <span className="font-serif font-bold text-ink">{anchorLabel}</span>
          {" · "}
          <span className="mono">{nodes.length} nodes, {edges.length} edges</span>
        </p>
      )}

      {!anchor && (
        <EmptyState message="Search for a judgment or a statute above to draw its neighbourhood." />
      )}
      {anchor && isLoading && <PageLoader />}
      {anchor && !isLoading && error && (
        <EmptyState message="Could not load that neighbourhood. It may not be in the corpus." />
      )}
      {anchor && !isLoading && !error && nodes.length === 0 && (
        <EmptyState message="Nothing in the corpus cites this, and it cites nothing we hold." />
      )}
      {anchor && !isLoading && !error && nodes.length > 0 && (
        <GraphCanvas nodes={nodes} edges={edges} truncated={truncated} />
      )}
    </div>
  );
}
