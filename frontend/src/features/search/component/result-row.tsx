import Link from "next/link";
import { Share2 } from "lucide-react";

/** Molecule: one hit, from a prop.
 *
 *  No verification badge. Nothing has been claimed about a search hit, so
 *  there is nothing to check -- rendering one with the marks an answer's
 *  citations carry would assert a check that never ran. */
export function ResultRow({
  result,
}: {
  result: {
    document_id: string;
    kind: string;
    title: string;
    citation?: string | null;
    court?: string | null;
    extract?: string | null;
  };
}) {
  return (
    <article className="border-b border-line px-6 py-4 last:border-b-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="caps text-ink-muted">{result.kind}</span>
          <h3 className="mt-1 text-statute leading-snug">{result.title}</h3>
          <p className="mono mt-1.5 text-xs text-ink-muted">
            {[result.citation, result.court].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Link
          href={`/graph?anchor=${encodeURIComponent(result.document_id)}`}
          title="See what cites this"
          className="flex shrink-0 items-center gap-1.5 rounded border border-line px-2.5 py-1.5 text-xs font-medium text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken hover:text-ink"
        >
          <Share2 className="size-3.5" />
          Graph
        </Link>
      </div>
      {result.extract && (
        <p className="mt-3 line-clamp-3 text-sm leading-[1.7] text-ink-variant">
          {result.extract}
        </p>
      )}
    </article>
  );
}
