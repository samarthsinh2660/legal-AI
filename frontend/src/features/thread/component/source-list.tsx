import Link from "next/link";
import { ExternalLink, Share2 } from "lucide-react";

import { sourceKind } from "../evidence";
import type { SourceLink } from "../types";

/** Molecule: what each claim rests on, with a way to open it.
 *
 *  Two kinds of link, and never none. Where the stored URL is the document
 *  itself it is offered directly. Where it is a bundled archive -- a
 *  judgment year tar, the single JSON the IPC and CrPC were parsed from --
 *  handing a reader a several-hundred-megabyte download and calling it the
 *  judgment is worse than not linking, so the graph stands in: it shows the
 *  document and what cites it, which is somewhere to go rather than a dead
 *  end.
 *
 *  This used to print "No direct link" as plain text while the inline
 *  citation chip for the same document linked to the graph, so the same
 *  source was a link in one place and not in another. */
export function SourceList({ sources }: { sources: SourceLink[] }) {
  if (sources.length === 0) return null;

  return (
    <section className="border-t border-line pt-4">
      <span className="caps text-ink-muted">Sources</span>
      <ul className="mt-3 space-y-2.5">
        {sources.map((source) => {
          const meta = [source.citation, source.court].filter(Boolean).join(" · ");
          const label = source.title || source.document_id;
          // The reader's own upload is in no graph and at no public
          // address, so it is the one source with nowhere to send them.
          const inGraph = sourceKind(source.document_id) !== "document";

          return (
            <li key={source.document_id} className="text-sm leading-snug">
              {source.openable && source.url ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1.5 text-primary hover:underline"
                >
                  <span className="font-serif font-bold">{label}</span>
                  <ExternalLink className="mt-0.5 size-3.5 shrink-0" />
                </a>
              ) : inGraph ? (
                <Link
                  href={`/graph?anchor=${encodeURIComponent(source.document_id)}`}
                  className="inline-flex items-start gap-1.5 text-primary hover:underline"
                >
                  <span className="font-serif font-bold">{label}</span>
                  <Share2 className="mt-0.5 size-3.5 shrink-0" />
                </Link>
              ) : (
                <span className="font-serif font-bold text-ink">{label}</span>
              )}

              {meta && <div className="mono mt-0.5 text-xs text-ink-muted">{meta}</div>}

              {!source.openable && inGraph && (
                <div className="text-xs text-ink-muted">
                  We hold no public page for this one — opens in the citation
                  graph. Look it up by the citation above to read it.
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
