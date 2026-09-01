"use client";

/** Renaming and deleting one thread, with the inline-edit state the row
 *  needs. Used by the thread row wherever it appears. */

import { useCallback, useState } from "react";

import { RequestError } from "@/lib/api";
import { useDeleteThread, useRenameThread } from "./index";

export function useThreadActions(threadId: string, currentTitle: string) {
  const { threadRename, isRenaming } = useRenameThread();
  const { threadDelete, isDeleting } = useDeleteThread();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(currentTitle);
  const [error, setError] = useState<string | null>(null);

  const startEditing = useCallback(() => {
    setDraft(currentTitle);
    setError(null);
    setEditing(true);
  }, [currentTitle]);

  const save = useCallback(async () => {
    const title = draft.trim();
    // An empty title would leave a row nobody can identify, and the
    // backend refuses it anyway.
    if (!title) {
      setError("A thread needs a title.");
      return;
    }
    if (title === currentTitle) {
      setEditing(false);
      return;
    }
    try {
      await threadRename({ threadId, title });
      setEditing(false);
    } catch (caught) {
      setError(
        caught instanceof RequestError ? caught.message : "Could not rename.",
      );
    }
  }, [draft, currentTitle, threadRename, threadId]);

  const remove = useCallback(async () => {
    try {
      await threadDelete(threadId);
      return true;
    } catch {
      setError("Could not delete this thread.");
      return false;
    }
  }, [threadDelete, threadId]);

  return {
    editing,
    startEditing,
    cancel: () => setEditing(false),
    draft,
    setDraft,
    save,
    remove,
    error,
    isBusy: isRenaming || isDeleting,
  };
}
