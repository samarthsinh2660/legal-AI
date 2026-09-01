"use client";

import Link from "next/link";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/molecules/confirm-dialog";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { relativeDate } from "@/lib/utils";
import { useThreadActions } from "../hooks/useThreadActions";
import type { Thread } from "../types";

/**
 * Organism: it uses `useThreadActions`, so it owns the editing and busy
 * states.
 *
 * The title is the only thing editable. A thread is the record of what was
 * asked and what the system answered; a rewritten question sitting above
 * the old answer would be a false record, which is why the backend has no
 * route for it either.
 *
 * Shows only what the API returns. The reference design put a source
 * count, a jurisdiction and a status on this row; `ThreadModel` carries
 * none of them, so neither does this.
 */
export function ThreadRow({ thread }: { thread: Thread }) {
  const { editing, startEditing, cancel, draft, setDraft, save, remove, error, isBusy } =
    useThreadActions(thread.thread_id, thread.title);
  const [confirming, setConfirming] = useState(false);

  if (editing) {
    return (
      <div className="px-6 py-4">
        <Input
          autoFocus
          value={draft}
          disabled={isBusy}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => void save()}
          onKeyDown={(event) => {
            if (event.key === "Enter") void save();
            if (event.key === "Escape") cancel();
          }}
        />
        {error && <p className="mt-1.5 text-sm text-danger">{error}</p>}
      </div>
    );
  }

  return (
    <div className="group flex items-center justify-between gap-4 px-6 py-4 transition-colors duration-[120ms] ease-out hover:bg-surface-sunken">
      <Link href={`/research/${thread.thread_id}`} className="min-w-0 flex-1">
        <div className="truncate font-medium text-ink">{thread.title}</div>
        <div className="mono mt-1.5 text-sm text-ink-muted">
          {relativeDate(thread.updated_at)}
        </div>
      </Link>

      {thread.case_id && (
        <span className="shrink-0 rounded-sm bg-surface-muted px-2.5 py-1 text-xs font-medium text-ink-variant">
          Case
        </span>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="Thread actions"
          className="flex size-8 shrink-0 items-center justify-center rounded text-ink-muted opacity-0 transition-opacity duration-[120ms] ease-out group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
        >
          <MoreHorizontal className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={startEditing}>
            <Pencil className="size-4" />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setConfirming(true)}
          >
            <Trash2 className="size-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete this thread?"
        description={`"${thread.title}" and every question and answer in it are deleted for good.`}
        confirmLabel="Delete thread"
        isBusy={isBusy}
        onConfirm={async () => {
          await remove();
          setConfirming(false);
        }}
      />
    </div>
  );
}
