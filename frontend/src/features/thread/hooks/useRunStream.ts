"use client";

/**
 * Watch a run.
 *
 * One path for both cases that need it: the turn this tab just asked for,
 * and a run it found already going on a thread it reopened. They were two
 * code paths while asking and answering were the same HTTP request; now the
 * answer is a worker's job either way, and a reopened tab is simply a
 * watcher that arrived late.
 *
 * Not polling: one connection, then nothing until the server has something
 * to say.
 */

import { useEffect, useRef, useState } from "react";

import { watchRun } from "../services";
import type { ProgressStep } from "../types";

type RunState = {
  steps: ProgressStep[];
  /** The lede, revealed as its chunks arrive. Empty until one does. */
  lede: string;
  /** True once the run ends, so the caller knows to read the thread back. */
  finished: boolean;
  error: string | null;
};

const IDLE: RunState = { steps: [], lede: "", finished: false, error: null };

/** How long to wait before reattaching after a dropped connection. */
const RETRY_MS = 2000;

export function useRunStream(runId: string | null): RunState {
  const [state, setState] = useState<RunState>(IDLE);
  // The last event seen, so a reconnect resumes rather than replaying the
  // run or missing its middle. A ref because the reconnect reads it outside
  // React's render cycle.
  const seen = useRef(0);

  useEffect(() => {
    if (!runId) {
      setState(IDLE);
      return;
    }

    seen.current = 0;
    setState(IDLE);
    const controller = new AbortController();
    let stopped = false;

    async function follow() {
      // Reconnects on its own, from the last event seen. A stream can end
      // because the run finished or because the connection dropped, and the
      // two look identical from here -- so it reattaches and lets the
      // replay decide.
      while (!stopped) {
        try {
          for await (const event of watchRun(
            runId!,
            seen.current,
            controller.signal,
          )) {
            if (event.type === "step") {
              seen.current = event.seq;
              setState((previous) => ({
                ...previous,
                steps: [...previous.steps, event.step],
              }));
            } else if (event.type === "answer_chunk") {
              seen.current = event.seq;
              setState((previous) => ({
                ...previous,
                lede: previous.lede + event.text,
              }));
            } else if (event.type === "done") {
              stopped = true;
              setState((previous) => ({ ...previous, finished: true }));
            } else {
              stopped = true;
              setState((previous) => ({
                ...previous,
                finished: true,
                error: event.message,
              }));
            }
          }
        } catch {
          // An aborted fetch is the component unmounting, not a failure.
          if (controller.signal.aborted) return;
        }
        if (stopped) return;
        // A dropped connection, not a finished run. Wait before reattaching
        // so a server that is down is not hammered.
        await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
      }
    }

    void follow();
    return () => {
      stopped = true;
      controller.abort();
    };
  }, [runId]);

  return state;
}
