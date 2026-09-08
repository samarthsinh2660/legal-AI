import { z } from "zod";

import { apiClient, readToken } from "@/lib/api";
import { paged, type Page } from "@/types/common";
import { API_BASE_URL } from "@/types/constant";
import {
  DraftSchema,
  MessageSchema,
  StartedDraftSchema,
  StartedRunSchema,
  ThreadSchema,
  type Draft,
  type Message,
  type ProgressStep,
  type StartedRun,
  type Thread,
  type Verification,
} from "../types";

export async function fetchThreads(
  limit: number,
  offset: number,
): Promise<Page<Thread>> {
  const data = await apiClient.get<unknown>(
    `/threads?limit=${limit}&offset=${offset}`,
  );
  return paged(ThreadSchema).parse(data);
}

export async function createThread(
  title?: string,
  caseId?: string,
): Promise<Thread> {
  const data = await apiClient.post<unknown>("/threads", {
    title: title ?? null,
    case_id: caseId ?? null,
  });
  return ThreadSchema.parse(data);
}

export async function fetchThread(threadId: string): Promise<Thread> {
  const data = await apiClient.get<unknown>(`/threads/${threadId}`);
  return ThreadSchema.parse(data);
}

export async function fetchMessages(threadId: string): Promise<Message[]> {
  const data = await apiClient.get<unknown>(`/threads/${threadId}/messages`);
  return z.array(MessageSchema).parse(data);
}

/**
 * Ask a question. Returns the run that will answer it, not the answer.
 *
 * The answer takes 30-130 seconds and is produced by a worker, so this
 * request only queues the job. What the reader watches is `watchRun`
 * below -- which is the same thing a reopened tab does, so there is one
 * path here rather than one for asking and another for coming back.
 */
export async function sendMessage(
  threadId: string,
  message: string,
  verification: Verification,
): Promise<StartedRun> {
  const data = await apiClient.post<unknown>(
    `/threads/${threadId}/messages`,
    { message, verification_level: verification },
  );
  return StartedRunSchema.parse(data);
}

/**
 * Stop a run that is still going.
 *
 * A queued run never costs a model call. A running one stops at the
 * worker's next node -- so this is not instant, and the button should not
 * claim it is.
 */
export async function cancelRun(runId: string): Promise<void> {
  await apiClient.post(`/runs/${runId}/cancel`, {});
}

export async function renameThread(
  threadId: string,
  title: string,
): Promise<Thread> {
  const data = await apiClient.patch<unknown>(`/threads/${threadId}`, { title });
  return ThreadSchema.parse(data);
}

export async function deleteThread(threadId: string): Promise<void> {
  await apiClient.delete(`/threads/${threadId}`);
}

export async function startDraft(
  threadId: string,
): Promise<{ draft_id: string; status: string }> {
  const data = await apiClient.post<unknown>(`/threads/${threadId}/drafts`, {});
  return StartedDraftSchema.parse(data);
}

export async function fetchDrafts(threadId: string): Promise<Draft[]> {
  const data = await apiClient.get<unknown>(`/threads/${threadId}/drafts`);
  return z.array(DraftSchema).parse(data);
}

/**
 * Download the .docx.
 *
 * Not `apiClient`: that unwraps a JSON envelope, and this route returns
 * the file itself. The bearer token still has to go with it, so the
 * browser cannot simply follow a link.
 */
export async function downloadDraft(draft: Draft): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/drafts/${draft.draft_id}/download`,
    { headers: { Authorization: `Bearer ${readToken() ?? ""}` } },
  );
  if (!response.ok) throw new Error("Could not download the document.");

  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = draft.filename || "document.docx";
  link.click();
  URL.revokeObjectURL(url);
}


/**
 * Attach to a run already in flight.
 *
 * A reopened tab has no hold on the stream the original POST opened, and
 * that POST cannot be repeated -- it would ask the question twice. This
 * watches the run itself.
 *
 * `fetch` rather than `EventSource`, for the same reason `streamMessage`
 * uses it: `EventSource` cannot carry an Authorization header, and the
 * alternative is a token in a URL and therefore in every access log. The
 * cost is that resuming is ours to do -- hence `since`, which the caller
 * advances as events arrive and passes back on reconnect.
 */
export async function* watchRun(
  runId: string,
  since: number,
  signal?: AbortSignal,
): AsyncGenerator<
  | { type: "step"; seq: number; step: ProgressStep }
  | { type: "answer_chunk"; seq: number; text: string }
  | { type: "done"; seq: number }
  | { type: "error"; code: string; message: string }
> {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/stream`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // SSE's own resume header. The server replays from here.
      ...(since ? { "Last-Event-ID": String(since) } : {}),
    },
    signal,
  });

  if (!response.ok || !response.body) {
    yield {
      type: "error",
      code: "http",
      message: `The server answered ${response.status}.`,
    };
    return;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let event = "message";
      let data = "";
      let id = 0;
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
        else if (line.startsWith("id:")) id = Number(line.slice(3).trim()) || 0;
      }
      if (!data) continue;

      if (event === "step") {
        yield { type: "step", seq: id, step: JSON.parse(data) as ProgressStep };
      } else if (event === "answer_chunk") {
        const { text } = JSON.parse(data) as { text: string };
        yield { type: "answer_chunk", seq: id, text };
      } else if (event === "done") {
        yield { type: "done", seq: id };
      } else if (event === "error") {
        // The code matters: the server sends `timeout` to say it has
        // stopped *watching*, not that the run stopped. Dropping it made
        // the client treat "still going" as "finished".
        const { code, message } = JSON.parse(data) as {
          code?: string;
          message?: string;
        };
        yield {
          type: "error",
          code: code ?? "error",
          message: message ?? "The run failed.",
        };
      }
    }
  }
}
