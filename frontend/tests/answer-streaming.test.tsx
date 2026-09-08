/**
 * The lede streams ahead of the finished message.
 *
 * Not a token stream from the model -- the lede is already past
 * verification by the time these events fire (see `worker/research.py`'s
 * docstring on the same change). What is tested here is the reveal, not the
 * backend's reasoning for withholding raw generation.
 *
 * The chunks reach this screen over the run's stream, the same one a
 * reopened tab attaches to, so this exercises the whole path a reader
 * actually takes.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { ResearchThread } from "@/features/thread/component/research-thread";
import { Verification } from "@/features/thread/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function frame(event: string, data: unknown, id?: number): string {
  return `${id ? `id: ${id}\n` : ""}event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const THREAD = {
  thread_id: "t1",
  title: "Bail",
  case_id: null,
  created_at: "2026-09-01T10:00:00+00:00",
  updated_at: "2026-09-01T10:00:00+00:00",
  active_run: null,
};

/**
 * Stand in for the API: POST returns a queued run, the run's stream is
 * `body`, and every other read is empty.
 */
function serve(body: ReadableStream<Uint8Array>) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = String(url);
    if (path.includes("/runs/") && path.endsWith("/stream")) {
      return Promise.resolve({ ok: true, status: 200, body });
    }
    if (init?.method === "POST") {
      return Promise.resolve({
        ok: true,
        status: 202,
        json: async () => ({
          success: true,
          data: { run_id: "r1", thread_id: "t1", status: "queued" },
        }),
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: path.includes("/messages") || path.includes("/drafts") ? [] : THREAD,
      }),
    });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
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

  vi.stubGlobal("fetch", serve(body));

  render(
    <ResearchThread
      threadId="t1"
      initialQuestion="when is bail granted"
      initialMode={Verification.Quick}
    />,
    { wrapper },
  );

  controller.enqueue(
    encoder.encode(frame("answer_chunk", { text: "Anticipatory bail " }, 1)),
  );
  await waitFor(() =>
    expect(screen.getByText(/Anticipatory bail/)).toBeInTheDocument(),
  );

  controller.enqueue(
    encoder.encode(frame("answer_chunk", { text: "is granted." }, 2)),
  );
  await waitFor(() =>
    expect(
      screen.getByText(/Anticipatory bail is granted\./),
    ).toBeInTheDocument(),
  );

  controller.enqueue(encoder.encode(frame("done", { text: "x" }, 3)));
  controller.close();

  // The transient preview is gone once the run settles -- MessageBubble
  // (from the stored message) is what carries the answer from here.
  await waitFor(() =>
    expect(screen.queryByText(/Anticipatory bail/)).not.toBeInTheDocument(),
  );
});
