"use client";

import { Maximize2 } from "lucide-react";

import { useForceGraph } from "../hooks/useForceGraph";
import type { GraphEdge, GraphNode } from "../types";
import { GraphLegend } from "./graph-legend";
import { NodeDetails } from "./node-details";

/** Organism: owns the simulation, the hover and the selection. */
export function GraphCanvas({
  nodes,
  edges,
  truncated,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}) {
  const { canvasRef, wrapRef, hovered, selected, resetView } = useForceGraph(
    nodes,
    edges,
  );

  return (
    <div className="relative">
      <div
        ref={wrapRef}
        className="h-[68vh] min-h-[60vh] w-full overflow-hidden rounded-md border border-line bg-surface-card"
      >
        <canvas ref={canvasRef} className="block cursor-grab" />
      </div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-4 p-4">
        <div className="pointer-events-auto rounded border border-line bg-surface-card/90 px-3 py-2 backdrop-blur">
          <GraphLegend />
        </div>
        <button
          type="button"
          onClick={resetView}
          title="Reset view"
          className="pointer-events-auto flex size-9 items-center justify-center rounded border border-line bg-surface-card text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken hover:text-ink"
        >
          <Maximize2 className="size-4" />
        </button>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-4 p-4">
        <span className="rounded border border-line bg-surface-card/90 px-3 py-1.5 text-xs text-ink-muted backdrop-blur">
          {hovered?.title ?? "Scroll to zoom · drag a node to pull it"}
        </span>

        {/* The server's own flag, shown where the reader can see it: a
            graph quietly missing half its edges is a picture that lies
            about how connected something is. */}
        {truncated && (
          <span className="rounded border border-warn/30 bg-warn-bg px-3 py-1.5 text-xs font-medium text-warn">
            Showing part of this neighbourhood — raise the node limit to see more
          </span>
        )}
      </div>

      {selected && (
        <div className="pointer-events-auto absolute right-4 top-16 w-72">
          <NodeDetails node={selected} />
        </div>
      )}
    </div>
  );
}
