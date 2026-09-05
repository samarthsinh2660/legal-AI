"use client";

import { FileText } from "lucide-react";

/**
 * Molecule: the composer's "Legal document" control.
 *
 * One button, no menu. There was a document type to choose from, and it
 * could only offer the one instrument a template existed for -- so it read
 * "no document fits this thread" on almost every conversation. The model
 * reads what was asked and drafts what follows from it, so there is
 * nothing here for the reader to pick.
 *
 * Disabled while one is being prepared: the API refuses a second draft on
 * the same thread, and a control that can only fail should not invite the
 * click.
 */
export function DraftButton({
  onSelect,
  disabled,
}: {
  onSelect: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 rounded-sm border border-line bg-surface-card px-2.5 py-1 text-xs font-medium text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken disabled:opacity-50"
    >
      <FileText className="size-3.5" aria-hidden="true" />
      Legal document
    </button>
  );
}
