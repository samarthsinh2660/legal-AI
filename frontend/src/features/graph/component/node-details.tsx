import Link from "next/link";

import type { GraphNode } from "../types";

/** Molecule: the selected node, from a prop.
 *
 *  Read-only, deliberately. The corpus is not a reader's to edit, and the
 *  API has no write path for it. */
export function NodeDetails({ node }: { node: GraphNode }) {
  return (
    <div className="rounded-md border border-line bg-surface-card p-4">
      <span className="caps text-ink-muted">{node.kind}</span>
      <h3 className="mt-2 text-statute leading-snug">
        {node.title ?? "Untitled"}
      </h3>
      <p className="mono mt-2 text-xs text-ink-muted">{node.id}</p>
      <Link
        href={`/graph?anchor=${encodeURIComponent(node.id)}`}
        className="mt-3 inline-block text-sm text-primary hover:underline"
      >
        Centre the graph here →
      </Link>
    </div>
  );
}
