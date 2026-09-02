import { ExternalLink } from "lucide-react";

import type { SourceLink } from "../types";

/** Molecule: what each claim rests on, with a way to open it.
 *
 *  A source whose stored URL is a bundled archive gets no link -- handing
 *  a reader a several-hundred-megabyte download and calling it the
 *  judgment is worse than none. Its citation is shown instead, which is
 *  what they would look up. */
export function SourceList({ sources }: { sources: SourceLink[] }) {
  if (sources.length === 0) return null;

  return (
    <section className="border-t border-line pt-4">
      <span className="caps text-ink-muted">Sources</span>
      <ul className="mt-3 space-y-2.5">
        {sources.map((source) => {
          const meta = [source.citation, source.court].filter(Boolean).join(" · ");
          const label = source.title || source.document_id;
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
              ) : (
                <span className="font-serif font-bold text-ink">{label}</span>
              )}
              {meta && <div className="mono mt-0.5 text-xs text-ink-muted">{meta}</div>}
              {!source.openable && (
                <div className="text-xs text-ink-muted">
                  No direct link — look it up by the citation above.
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
