/**
 * The lede streams ahead of the finished message.
 *
 * Not a token stream from the model -- the lede is already past
 * verification by the time these events fire (see
 * api/threads/controller.py's docstring on the same change). What is
 * tested here is the wire contract and the reveal, not the backend's
 * reasoning for withholding raw generation.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { ResearchThread } from "@/features/thread/component/research-thread";
import { streamMessage } from "@/features/thread/services";
import { Verification } from "@/features/thread/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** An SSE body: one frame per event, exactly what `pg_dump`-style
 *  event/data pairs look like on the wire. */
function sseBody(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function serveStream(frames: string[]) {
  return vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      String(url).includes("/stream")
        ? { ok: true, status: 200, body: sseBody(frames) }
        : { ok: true, status: 200, json: async () => ({ success: true, data: [] }) },
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("streamMessage yields answer_chunk events in order, before done", async () => {
  vi.stubGlobal(
    "fetch",
    serveStream([
      frame("step", { node: "research", label: "Searching" }),
      frame("answer_chunk", { text: "Anticipatory bail " }),
      frame("answer_chunk", { text: "is granted by " }),
      frame("done", {
        text: "Anticipatory bail is granted by the court.",
        answer: null,
        clarification_needed: null,
        route: "RESEARCH",
        verification_level: "quick",
      }),
    ]),
  );

  const events = [];
  for await (const event of streamMessage("t1", "q", Verification.Quick)) {
    events.push(event);
  }

  const kinds = events.map((e) => e.type);
  expect(kinds.indexOf("answer_chunk")).toBeLessThan(kinds.indexOf("done"));
  expect(
    events
      .filter((e): e is { type: "answer_chunk"; text: string } => e.type === "answer_chunk")
      .map((e) => e.text)
      .join(""),
  ).toBe("Anticipatory bail is granted by ");
});

it("shows the lede growing on screen before the turn finishes", async () => {
  // Held open deliberately: enqueue one chunk, let the reveal render, then
  // finish the stream. A stream that closes immediately races React's
  // render against the turn's own cleanup, which clears the transient
  // preview the moment "done" arrives.
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });

  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        String(url).includes("/stream")
          ? { ok: true, status: 200, body }
          : { ok: true, status: 200, json: async () => ({ success: true, data: [] }) },
      ),
    ),
  );

  render(
    <ResearchThread threadId="t1" initialQuestion="when is bail granted" initialMode={Verification.Quick} />,
    { wrapper },
  );

  controller.enqueue(encoder.encode(frame("answer_chunk", { text: "Anticipatory bail " })));
  await waitFor(() => expect(screen.getByText(/Anticipatory bail/)).toBeInTheDocument());

  controller.enqueue(encoder.encode(frame("answer_chunk", { text: "is granted." })));
  await waitFor(() => expect(screen.getByText(/Anticipatory bail is granted\./)).toBeInTheDocument());

  controller.enqueue(
    encoder.encode(
      frame("done", {
        text: "Anticipatory bail is granted.",
        answer: null,
        clarification_needed: null,
        route: "RESEARCH",
        verification_level: "quick",
      }),
    ),
  );
  controller.close();

  // The transient preview is gone once the turn settles -- MessageBubble
  // (from the persisted message) is what carries the answer from here.
  await waitFor(() => expect(screen.queryByText(/Anticipatory bail/)).not.toBeInTheDocument());
});
