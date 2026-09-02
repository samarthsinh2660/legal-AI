"use client";

/** The graph screen's own state: which document anchors it, and how far
 *  out to walk. Only this page uses it. */

import { useState } from "react";

import { MAX_HOPS, MAX_NODES, type SearchHit } from "../types";
import { useNeighbourhood } from "./index";

export function useGraphExplorer(initialAnchor?: string) {
  const [anchor, setAnchor] = useState<string | null>(initialAnchor ?? null);
  const [anchorLabel, setAnchorLabel] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hops, setHops] = useState(1);

  const graph = useNeighbourhood(anchor, hops, MAX_NODES);

  const pick = (hit: SearchHit) => {
    setAnchor(hit.document_id);
    setAnchorLabel(hit.title);
    setQuery("");
  };

  return {
    ...graph,
    anchor,
    anchorLabel,
    query,
    setQuery,
    hops,
    // Two hops is the backend's ceiling; offering three would be clamped
    // silently and read as a bug.
    setHops: (value: number) => setHops(Math.min(value, MAX_HOPS)),
    pick,
  };
}
