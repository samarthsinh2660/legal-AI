import { z } from "zod";

import { apiClient, readToken } from "@/lib/api";
import { paged, type Page } from "@/types/common";
import { API_BASE_URL } from "@/types/constant";
import {
  DraftSchema,
  MessageSchema,
  StartedDraftSchema,
  ReplySchema,
  ThreadSchema,
  type Draft,
  type Message,
  type ProgressStep,
  type Reply,
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
 * Send a message and yield each event as it arrives.
 *
 * Hand-rolled rather than `EventSource`, which can only issue a GET and
 * cannot carry an Authorization header. This is also why it does not go
 * through `apiClient`: that unwraps one JSON envelope, and a stream is a
 * sequence of frames.
 *
 * A researched turn takes one to two minutes; without these events the
 * pane is blank for the whole of it and the page reads as hung.
 */
export async function* streamMessage(
  threadId: string,
  message: string,
  verification: Verification,
  signal?: AbortSignal,
): AsyncGenerator<
  | { type: "step"; step: ProgressStep }
  | { type: "answer_chunk"; text: string }
  | { type: "done"; reply: Reply }
  | { type: "error"; message: string }
> {
  const token = readToken();
  const response = await fetch(
    `${API_BASE_URL}/threads/${threadId}/messages/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message, verification_level: verification }),
      signal,
    },
  );

  if (!response.ok || !response.body) {
    yield { type: "error", message: `The server answered ${response.status}.` };
    return;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;

    // Frames are separated by a blank line. A chunk can split one in half,
    // so whatever follows the last separator stays in the buffer.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;

      const parsed: unknown = JSON.parse(data);
      if (event === "step") {
        yield { type: "step", step: parsed as ProgressStep };
      } else if (event === "answer_chunk") {
        const { text } = parsed as { text: string };
        yield { type: "answer_chunk", text };
      } else if (event === "done") {
        yield { type: "done", reply: ReplySchema.parse(parsed) };
      } else if (event === "error") {
        const { message: text } = parsed as { message?: string };
        yield { type: "error", message: text ?? "The research failed." };
      }
    }
  }
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

