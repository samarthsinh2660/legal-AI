"use client";

/** The graph screen's own state: which slice is shown, and whether a
 *  document was picked to centre on. Only this page uses it. */

import { useState } from "react";

import { MAX_NODES, VIEWS } from "../types";
import { useNeighbourhood, useOverview } from "./index";

export function useGraphExplorer(initialAnchor?: string) {
  // An anchor arrives from a citation in an answer. There is no search box
  // on this screen: the views below are how a reader browses, and a
  // citation is how they arrive at one document.
  const [anchor, setAnchor] = useState<string | null>(initialAnchor ?? null);
  const [view, setView] = useState<string>(VIEWS[0].id);

  const anchored = useNeighbourhood(anchor, MAX_NODES);
  const overview = useOverview(view, anchor === null);

  return {
    ...(anchor ? { ...anchored, loadMore: undefined, isLoadingMore: false } : overview),
    anchor,
    clearAnchor: () => setAnchor(null),
    view,
    setView,
  };
}
