"use client";

import { AlertTriangle, FileText, Loader2 } from "lucide-react";
import { useState } from "react";

import { downloadDraft } from "../services";
import type { Draft } from "../types";

/**
 * Molecule: one drafted document in the thread.
 *
 * The three states are deliberately different objects, not one card with a
 * spinner swapped for an icon. A document being prepared, a document ready
 * to send, and a draft that could not be produced are three different
 * things to a reader, and the last of them has to carry its reason.
 *
 * The warning line is not decoration. What we produce is a draft on our
 * template, without the advocate's letterhead or enrolment number, and a
 * reader who misses that could send it as it is.
 */
export function DraftCard({ draft }: { draft: Draft }) {
  const [failed, setFailed] = useState<string | null>(null);

  if (draft.status === "running") {
    return (
      <p className="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Preparing your document. This keeps running whether or not the page is
        open.
      </p>
    );
  }

  if (draft.status === "failed") {
    return (
      <div className="rounded-md border border-line bg-surface-card p-4">
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <AlertTriangle className="size-4 text-danger" aria-hidden="true" />
          The document could not be prepared.
        </p>
        {draft.error && (
          <p className="mt-1.5 text-sm text-ink-muted">{draft.error}</p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-line bg-surface-card p-4">
      <button
        type="button"
        onClick={() => downloadDraft(draft).catch((error) => setFailed(String(error.message)))}
        className="flex w-full items-center gap-3 text-left"
      >
        <FileText className="size-8 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0">
          <span className="block truncate font-medium text-ink underline-offset-2 hover:underline">
            {draft.filename}
          </span>
          <span className="mono block text-sm text-ink-muted">
            DOCX · draft — review and put on your letterhead before sending
          </span>
        </span>
      </button>

      {draft.warnings.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-sm font-medium text-ink">Resolve before sending</p>
          <ul className="mt-1.5 space-y-1">
            {draft.warnings.map((warning) => (
              <li key={warning} className="text-sm text-ink-muted">
                {warning}
              </li>
            ))}
          </ul>
        </div>
      )}

      {draft.needs_input.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-sm font-medium text-ink">You still need to supply</p>
          <ul className="mt-1.5 space-y-1">
            {draft.needs_input.map((item) => (
              <li key={item} className="text-sm text-ink-muted">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failed && <p className="mt-2 text-sm text-danger">{failed}</p>}
    </div>
  );
}
