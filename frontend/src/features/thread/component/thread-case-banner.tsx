"use client";

import Link from "next/link";
import { FolderOpen } from "lucide-react";

import { useCase } from "@/features/case/hooks";
import { useThread } from "../hooks";

/**
 * Organism: says which matter this thread belongs to, and links back.
 *
 * Without it a case-attached thread looks exactly like a loose one, so a
 * reader has no way to tell that the answers were seeded with the matter's
 * context -- which is the whole reason to attach a thread to a case.
 *
 * Reaches into the `case` feature, the mirror of `case-threads.tsx`
 * reaching into this one. A matter and its research are one thing to a
 * reader, and duplicating either side to keep the folders apart would
 * fork behaviour that has to stay identical.
 */
export function ThreadCaseBanner({ threadId }: { threadId: string }) {
  const { thread } = useThread(threadId);
  const { item } = useCase(thread?.case_id ?? "");

  if (!thread?.case_id) return null;

  return (
    <Link
      href={`/cases/${thread.case_id}`}
      className="flex items-center gap-2.5 rounded-md border border-line bg-surface-tint px-4 py-2.5 transition-colors duration-[120ms] ease-out hover:border-primary"
    >
      <FolderOpen className="size-4 shrink-0 text-primary" />
      <span className="min-w-0 text-sm text-ink-variant">
        Part of{" "}
        <span className="font-serif font-bold text-primary-deep">
          {item?.title ?? "this case"}
        </span>
        {" — "}every answer here starts from the matter&apos;s context.
      </span>
    </Link>
  );
}
