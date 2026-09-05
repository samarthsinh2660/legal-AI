"use client";

/**
 * The home page's ask box: the question, its validation, and what happens
 * on submit. Only this screen uses it, so it is its own file rather than
 * part of `hooks/index.ts`. It wraps `useCreateThread` and never touches
 * the service.
 *
 * Submitting creates the thread and hands the question to the research
 * workspace through the URL. The alternative -- sending the message here
 * and then navigating -- would leave the user on the home page watching
 * nothing for the ~100 seconds a research run takes.
 */

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { RequestError } from "@/lib/api";
import { useCreateThread } from "./index";
import { QUESTION_MAX_LENGTH, Verification } from "../types";

/** Matches api.threads.controller.TITLE_CHARS. A sidebar of full questions
 *  is unreadable, and a nowrap title that long distorts the grid holding it. */
const TITLE_CHARS = 60;

export function useAskForm(caseId?: string) {
  const [question, setQuestion] = useState("");
  // Quick by default. It still checks every citation exists; what it
  // skips is whether each source supports the claim, and the answer says
  // so. Verified costs a third model call and roughly doubles the wait,
  // which is a choice worth making per question rather than paying by
  // default on the first one someone asks.
  const [verification, setVerification] = useState<Verification>(
    Verification.Quick,
  );
  const [error, setError] = useState<string | null>(null);
  const { threadCreate, isCreating } = useCreateThread();
  const router = useRouter();

  const handleChange = useCallback((value: string) => {
    setQuestion(value);
    setError(null);
  }, []);

  const handleSubmit = useCallback(async () => {
    const asked = question.trim();
    if (!asked) {
      setError("Ask a question first.");
      return;
    }
    if (asked.length > QUESTION_MAX_LENGTH) {
      setError(`Questions are limited to ${QUESTION_MAX_LENGTH} characters.`);
      return;
    }

    try {
      // The question doubles as the title: the backend renames the thread
      // from the first exchange anyway, and an untitled row in the sidebar
      // is useless until it does. Cut to the same length the backend uses
      // (TITLE_CHARS), since a title set here is one it will not replace.
      const thread = await threadCreate({
        title: asked.slice(0, TITLE_CHARS),
        caseId,
      });
      router.push(
        `/research/${thread.thread_id}?ask=${encodeURIComponent(asked)}`
        + `&mode=${verification}`,
      );
    } catch (caught) {
      setError(
        caught instanceof RequestError
          ? caught.message
          : "Could not start the research. Try again.",
      );
    }
  }, [question, threadCreate, caseId, verification, router]);

  return {
    question, error, isCreating, verification, setVerification,
    handleChange, handleSubmit,
  };
}
