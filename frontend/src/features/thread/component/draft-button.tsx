"use client";

import { FileText } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { DocumentType } from "../types";

/**
 * Molecule: the composer's "Legal document" control.
 *
 * A menu rather than a button, because the document type is the one thing
 * the reader has to choose and there will be more than one of them. It
 * sits in the composer because the document is drafted from the
 * conversation above it, not from a separate screen.
 *
 * Disabled while one is being prepared: the API refuses a second draft on
 * the same thread, and a control that can only fail should not invite the
 * click.
 */
export function DraftButton({
  types,
  onSelect,
  disabled,
}: {
  types: DocumentType[];
  onSelect: (documentType: string) => void;
  disabled?: boolean;
}) {
  // Nothing to offer means the conversation has not settled the law any
  // document rests on. Saying so beats a menu that can only fail.
  if (types.length === 0) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-sm border border-line px-2.5 py-1 text-xs font-medium text-ink-muted"
        title="Ask a question the document would rest on, then draft from the answer."
      >
        <FileText className="size-3.5" aria-hidden="true" />
        No document fits this thread yet
      </span>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-sm border border-line bg-surface-card px-2.5 py-1 text-xs font-medium text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken disabled:opacity-50"
      >
        <FileText className="size-3.5" aria-hidden="true" />
        Legal document
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {types.map((type) => (
          <DropdownMenuItem
            key={type.value}
            onSelect={() => onSelect(type.value)}
          >
            {type.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
