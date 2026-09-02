import Link from "next/link";

import { shortLabel, sourceKind } from "../evidence";
import type { SourceLink } from "../types";

/** Molecule: one evidence id as a clickable marker.
 *
 *  Opens the source itself -- the India Code page, the reporter's copy --
 *  whenever the answer carried a URL for it. The graph is where a reader
 *  goes to see what a provision connects to, not to read it, so sending
 *  every citation there answered a question nobody had asked.
 *
 *  Falls back to the graph when there is no URL, which is the honest
 *  second best: it still shows the document and what cites it. Case files
 *  get neither -- they are the reader's own upload, in no graph and at no
 *  public address. */
export function CitationRef({ id, source }: { id: string; source?: SourceLink }) {
  const kind = sourceKind(id);
  // The citation is what tells one judgment from another.
  const label = shortLabel(id, source?.citation);
  const chip =
    "mono inline-flex h-5 items-center rounded-sm bg-surface-muted px-1.5 text-xs font-semibold text-ink-variant";
  const interactive =
    " transition-colors duration-[120ms] ease-out hover:bg-surface-tint hover:text-primary";

  if (kind === "document" || kind === "unknown") {
    return (
      <span title={id} className={chip}>
        {label}
      </span>
    );
  }

  if (source?.openable && source.url) {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        title={source.title || id}
        className={chip + interactive}
      >
        {label}
      </a>
    );
  }

  return (
    <Link
      href={`/graph?anchor=${encodeURIComponent(id)}`}
      title={`${source?.title || id} — no direct link; showing what cites it`}
      className={chip + interactive}
    >
      {label}
    </Link>
  );
}
