"use client";

/**
 * The research workspace's own state: the composer, the run it is watching,
 * and the send that starts one. Only this screen uses it.
 *
 * Asking and watching are separate now. The request queues a job and
 * returns a run id; everything after that -- the steps, the lede, the
 * finished answer -- arrives over the run's stream, which is the same
 * stream a reopened tab attaches to. A closed laptop costs the progress
 * view and nothing else.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { cancelRun, sendMessage } from "../services";
import { Verification, type Message } from "../types";
import { threadKeys, useMessages, useThread } from "./index";
import { useRunStream } from "./useRunStream";

export function useResearchThread(threadId: string) {
  const {
    messages,
    error: loadError,
    isLoading,
    isFetching,
  } = useMessages(threadId);
  const { thread } = useThread(threadId);
  const queryClient = useQueryClient();

  const [draft, setDraft] = useState("");
  // Quick by default, matching the ask box. `send` takes an explicit mode
  // so the first turn runs the way the reader chose on the way in.
  const [verification, setVerification] = useState<Verification>(
    Verification.Quick,
  );
  const [sendError, setSendError] = useState<string | null>(null);

  // The run this tab started, held until the thread query catches up. The
  // server's `active_run` is the same fact a moment later, but a composer
  // that stayed enabled for that moment would take a second question.
  const [started, setStarted] = useState<string | null>(null);
  // A run already watched to its end. Without this the still-cached
  // `active_run` would send the stream straight back to a finished run.
  const [ended, setEnded] = useState<string | null>(null);

  const active = thread?.active_run ?? null;
  const researching = active?.kind === "research" ? active.run_id : null;
  const running = started ?? researching;
  const watching = running === ended ? null : running;
  const live = useRunStream(watching);

  const messageKey = [...threadKeys.all, threadId, "messages"] as const;

  useEffect(() => {
    if (!live.finished || !watching) return;
    setEnded(watching);
    setStarted(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.finished, watching]);

  // Whenever the run goes away -- because its stream said so, or because
  // the thread poll noticed -- read the turn back. The stream's own words
  // are not enough: the worker stored both messages, and the assistant's
  // carries the structured answer this does not reconstruct.
  const previous = useRef<string | null>(null);
  useEffect(() => {
    if (previous.current && !watching) {
      void queryClient.invalidateQueries({ queryKey: messageKey });
      void queryClient.invalidateQueries({ queryKey: threadKeys.all });
    }
    previous.current = watching;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watching, threadId, queryClient]);

  // Asking to stop is not stopping: the worker finishes the node it is
  // inside and quits at the next boundary. The run's own stream is what
  // reports the end, so nothing here pretends it already happened.
  const [stopping, setStopping] = useState(false);
  const stop = useCallback(async () => {
    if (!watching) return;
    setStopping(true);
    try {
      await cancelRun(watching);
    } catch (caught) {
      setStopping(false);
      setSendError(
        caught instanceof Error ? caught.message : "Could not stop this run.",
      );
    }
  }, [watching]);

  useEffect(() => {
    if (!watching) setStopping(false);
  }, [watching]);

  const send = useCallback(
    async (text: string, mode?: Verification) => {
      const asked = text.trim();
      if (!asked || watching) return;

      setDraft("");
      setSendError(null);

      // Show the question immediately. A negative id cannot collide with a
      // real one, and the refetch on completion replaces it.
      queryClient.setQueryData<Message[]>(messageKey, (old = []) => [
        ...old,
        {
          message_id: -Date.now(),
          role: "user",
          content: asked,
          created_at: new Date().toISOString(),
        },
      ]);

      try {
        const run = await sendMessage(threadId, asked, mode ?? verification);
        setEnded(null);
        setStarted(run.run_id);
      } catch (caught) {
        setSendError(
          caught instanceof Error
            ? caught.message
            : "The question could not be sent.",
        );
        await queryClient.invalidateQueries({ queryKey: messageKey });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [threadId, watching, verification, queryClient],
  );

  return {
    messages,
    isLoading,
    loadError,
    draft,
    setDraft,
    verification,
    setVerification,
    steps: live.steps,
    streamingLede: live.lede,
    // A run in flight, whether this tab started it or found it.
    isSending: Boolean(watching),
    stop,
    stopping,
    // The thread ends on a question with no run behind it: the turn did not
    // finish. An honest state, not a five-minute guess -- there is a row
    // saying so. Held back while the messages are being refetched, or a
    // turn that just succeeded flashes "didn't finish" in the gap between
    // its run ending and its reply arriving.
    unfinished:
      !watching && !isFetching && messages.length > 0 &&
      messages[messages.length - 1].role === "user",
    sendError: sendError ?? live.error,
    send,
  };
}
