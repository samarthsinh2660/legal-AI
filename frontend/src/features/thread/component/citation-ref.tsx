import Link from "next/link";

import { shortLabel, sourceKind } from "../evidence";

/** Molecule: one evidence id as a clickable marker.
 *
 *  A provision the reader cannot open is not usable, so every id links to
 *  its neighbourhood in the graph. Case files are the exception -- they
 *  are the reader's own upload and are not in the citation graph. */
export function CitationRef({ id }: { id: string }) {
  const kind = sourceKind(id);
  const label = shortLabel(id);

  if (kind === "document" || kind === "unknown") {
    return (
      <span
        title={id}
        className="mono inline-flex h-5 items-center rounded-sm bg-surface-muted px-1.5 text-xs font-semibold text-ink-variant"
      >
        {label}
      </span>
    );
  }

  return (
    <Link
      href={`/graph?anchor=${encodeURIComponent(id)}`}
      title={id}
      className="mono inline-flex h-5 items-center rounded-sm bg-surface-muted px-1.5 text-xs font-semibold text-ink-variant transition-colors duration-[120ms] ease-out hover:bg-surface-tint hover:text-primary"
    >
      {label}
    </Link>
  );
}
