import { AlertTriangle } from "lucide-react";

import type { GoodLaw, SourceLink } from "../types";
import { shortLabel } from "../evidence";

/**
 * Molecule: the judgments in this answer a later court held wrongly decided.
 *
 * Above the answer, because it changes whether the reader should use it at
 * all — an overruled authority relied on in a filing is the failure a
 * citator exists to prevent.
 *
 * Only DOUBTED is shown. The clean state is reported on the source itself,
 * where it belongs next to its denominator, and NOT_CHECKED is not sent at
 * all. A caution printed on most answers is one a reader learns to skip.
 */
export function GoodLawBanner({
  notes,
  sources,
}: {
  notes: GoodLaw[];
  sources: SourceLink[];
}) {
  const doubted = notes.filter((note) => note.status === "DOUBTED");
  if (doubted.length === 0) return null;

  const byId = new Map(sources.map((s) => [s.document_id, s]));
  const name = (id: string) => byId.get(id)?.title || shortLabel(id, byId.get(id)?.citation);

  return (
    <section className="rounded-md border border-danger/30 bg-danger-bg px-4 py-3">
      <div className="flex items-center gap-2 text-danger">
        <AlertTriangle className="size-4 shrink-0" />
        <span className="caps">Doubted authority</span>
      </div>
      <ul className="mt-2 space-y-1.5">
        {doubted.map((note) => (
          <li key={note.document_id} className="text-sm leading-[1.7] text-ink-variant">
            <span className="font-serif font-bold">{name(note.document_id)}</span>
            {note.overruled_by.length > 0 && (
              <>
                {" was held wrongly decided by "}
                <span className="font-serif font-bold">
                  {note.overruled_by.map(name).join("; ")}
                </span>
              </>
            )}
            .
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs leading-relaxed text-ink-muted">
        Read from the treatments recorded in this corpus. Confirm against the
        reporter before relying on either judgment.
      </p>
    </section>
  );
}
