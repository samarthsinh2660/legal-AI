"use client";

/** The search screen's own state. Only this page uses it. */

import { useState } from "react";

import { useSearch } from "./index";
import { SearchKind } from "../types";

export function useSearchForm(initialQuery = "") {
  // Two fields: what is typed, and what has been asked for. Without the
  // split every keystroke is a query, and the corpus is too big for that.
  const [draft, setDraft] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [kind, setKind] = useState<SearchKind>(SearchKind.All);

  const results = useSearch(query, kind);

  return {
    ...results,
    draft,
    setDraft,
    query,
    kind,
    setKind,
    submit: () => setQuery(draft),
  };
}
