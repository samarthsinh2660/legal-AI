import Link from "next/link";

import { relativeDate } from "@/lib/utils";
import type { Thread } from "../types";

/** Molecule: one thread, from a prop. No hook, no fetching.
 *
 *  Shows only what the API returns. The reference design put a source
 *  count, a jurisdiction and a status on this row; `ThreadModel` carries
 *  none of them, so neither does this. */
export function ThreadRow({ thread }: { thread: Thread }) {
  return (
    <Link
      href={`/research/${thread.thread_id}`}
      className="flex items-center justify-between gap-4 px-6 py-4 transition-colors duration-[120ms] ease-out hover:bg-surface-sunken"
    >
      <div className="min-w-0">
        <div className="truncate font-medium text-ink">{thread.title}</div>
        <div className="mono mt-1.5 text-sm text-ink-muted">
          {relativeDate(thread.updated_at)}
        </div>
      </div>
      {thread.case_id && (
        <span className="shrink-0 rounded-sm bg-surface-muted px-2.5 py-1 text-xs font-medium text-ink-variant">
          Case
        </span>
      )}
    </Link>
  );
}
