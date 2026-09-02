"use client";

/**
 * The research workspace's own state: the composer, the live progress
 * steps, and the send that produces both. Only this screen uses it.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { streamMessage } from "../services";
import { Verification, type Message, type ProgressStep } from "../types";
import { threadKeys, useMessages } from "./index";

export function useResearchThread(threadId: string) {
  const { messages, error: loadError, isLoading } = useMessages(threadId);
  const queryClient = useQueryClient();

  const [draft, setDraft] = useState("");
  // Quick by default, matching the ask box. `send` takes an explicit mode
  // so the first turn runs the way the reader chose on the way in.
  const [verification, setVerification] = useState<Verification>(
    Verification.Quick,
  );
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  // Leaving the page mid-run must not leave the stream reading into a
  // component that no longer exists.
  useEffect(() => () => abort.current?.abort(), []);

  const messageKey = [...threadKeys.all, threadId, "messages"] as const;

  const send = useCallback(
    async (text: string, mode?: Verification) => {
      const asked = text.trim();
      if (!asked || isSending) return;

      setDraft("");
      setSendError(null);
      setSteps([]);
      setIsSending(true);

      // Show the question immediately. A negative id cannot collide with a
      // real one, and the refetch below replaces it.
      queryClient.setQueryData<Message[]>(messageKey, (old = []) => [
        ...old,
        {
          message_id: -Date.now(),
          role: "user",
          content: asked,
          created_at: new Date().toISOString(),
        },
      ]);

      const controller = new AbortController();
      abort.current = controller;

      try {
        for await (const event of streamMessage(
          threadId,
          asked,
          mode ?? verification,
          controller.signal,
        )) {
          if (event.type === "step") {
            setSteps((previous) => [...previous, event.step]);
          } else if (event.type === "error") {
            setSendError(event.message);
          }
        }
        // Read the turn back rather than trusting the optimistic row: the
        // server stored both messages, and the assistant's carries the
        // structured answer this does not reconstruct.
        await queryClient.invalidateQueries({ queryKey: messageKey });
        await queryClient.invalidateQueries({ queryKey: threadKeys.all });
      } catch (caught) {
        if (!controller.signal.aborted) {
          setSendError(
            caught instanceof Error
              ? caught.message
              : "The research could not be completed.",
          );
        }
      } finally {
        setIsSending(false);
        setSteps([]);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [threadId, isSending, verification, queryClient],
  );

  return {
    messages,
    isLoading,
    loadError,
    draft,
    setDraft,
    verification,
    setVerification,
    steps,
    isSending,
    sendError,
    send,
  };
}
