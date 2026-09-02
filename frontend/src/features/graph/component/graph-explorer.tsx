"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/molecules/empty-state";
import { PageLoader } from "@/components/molecules/loading";
import { cn } from "@/lib/utils";
import { useGraphExplorer } from "../hooks/useGraphExplorer";
import { VIEWS } from "../types";
import { GraphCanvas } from "./graph-canvas";

/**
 * Organism: owns which slice is shown and every state the fetch can be in.
 *
 * No search box and no hop control. A reader browses by picking a slice,
 * and arrives at a single document by clicking a citation in an answer --
 * which is what sets `anchor`.
 */
export function GraphExplorer({ initialAnchor }: { initialAnchor?: string }) {
  const {
    nodes, edges, total, truncated, error, isLoading,
    loadMore, isLoadingMore, anchor, clearAnchor, view, setView,
  } = useGraphExplorer(initialAnchor);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="mb-6">
        <h1 className="text-title">Citation graph</h1>
        <p className="mt-1.5 text-lg text-ink-variant">
          What cites what, drawn from the corpus we hold. Read-only.
        </p>
      </div>

      {anchor ? (
        <div className="mb-4 flex items-center gap-3">
          <span className="mono text-sm text-ink-muted">
            Centred on {anchor}
          </span>
          <Button variant="outline" size="sm" onClick={clearAnchor}>
            <X className="size-3.5" />
            Back to the graph
          </Button>
        </div>
      ) : (
        <div className="mb-4 flex flex-wrap gap-1 rounded border border-line bg-surface-card p-1">
          {VIEWS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setView(option.id)}
              className={cn(
                "rounded-sm px-3 py-1.5 text-xs font-medium transition-colors duration-[120ms] ease-out",
                view === option.id
                  ? "bg-surface-tint text-primary"
                  : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      {!isLoading && !error && nodes.length > 0 && (
        <p className="mono mb-3 text-sm text-ink-muted">
          {/* Counted apart, because they are different things. `total`
              sizes the slice itself; the hops-1 nodes are judgments pulled
              in to give the sections something to connect to, and folding
              them into one number produced "200 of 155". */}
          {(() => {
            const own = nodes.filter((n) => n.hops === 0).length;
            const pulled = nodes.length - own;
            const head =
              total !== null && total > own
                ? `${own} of ${total.toLocaleString("en-IN")} nodes`
                : `${own} nodes`;
            return [
              head,
              pulled > 0 ? ` + ${pulled} citing judgments` : "",
              `, ${edges.length} edges`,
            ].join("");
          })()}
        </p>
      )}

      {isLoading && <PageLoader />}

      {!isLoading && error && (
        <EmptyState
          message={
            anchor
              ? "Could not load that neighbourhood. It may not be in the corpus."
              : "Could not load the graph. Refresh to try again."
          }
        />
      )}

      {!isLoading && !error && nodes.length === 0 && (
        <EmptyState message="Nothing in this part of the corpus is connected yet." />
      )}

      {/* Nodes with no edges are not a rendering failure -- the citation
          edges are built when a judgment is ingested, so an Act added
          afterwards has none until they are rebuilt. Saying so beats
          drawing a hundred unconnected dots and letting the reader guess. */}
      {!isLoading && !error && nodes.length > 0 && edges.length === 0 && (
        <p className="mb-3 rounded-md border border-warn/30 bg-warn-bg px-4 py-3 text-sm text-warn">
          These sections are in the corpus, but no judgment we hold cites
          them yet — the citation links are built when a judgment is
          ingested, and this Act was added after them. Of 36,887 sections,
          2,295 are cited by a judgment we hold.
        </p>
      )}

      {!isLoading && !error && nodes.length > 0 && (
        <>
          <GraphCanvas nodes={nodes} edges={edges} truncated={truncated} />

          {loadMore && truncated && (
            <div className="mt-4 flex justify-center">
              <Button
                variant="outline"
                disabled={isLoadingMore}
                onClick={() => void loadMore()}
              >
                {isLoadingMore ? "Loading…" : "Load 100 more"}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
