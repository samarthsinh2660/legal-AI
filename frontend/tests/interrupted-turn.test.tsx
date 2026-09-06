/**
 * A thread reopened mid-turn, and one reopened after a turn that died.
 *
 * These look identical in the messages -- a question from the user with no
 * reply after it -- and used to be told apart by a five-minute clock. The
 * run row says which it is, so the screen can too: still going, or over
 * with nothing to show.
 *
 * The question is stored before any work starts (api/threads/controller.py),
 * which is what makes both states reachable at all.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { ResearchThread } from "@/features/thread/component/research-thread";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ASKED = {
  message_id: 1,
  role: "user",
  content: "what is section 420",
  answer: null,
  created_at: "2026-09-05T10:00:00+00:00",
};

function thread(activeRun: unknown = null) {
  return {
    thread_id: "t1",
    title: "Section 420",
    case_id: null,
    created_at: "2026-09-05T09:59:00+00:00",
    updated_at: "2026-09-05T10:00:00+00:00",
    active_run: activeRun,
  };
}

/** The API, as this screen reads it: the thread, its messages, its drafts. */
function serve(messages: unknown[], activeRun: unknown = null, stream = "") {
  return vi.fn().mockImplementation((url: string) => {
    const path = String(url);
    if (path.includes("/runs/") && path.endsWith("/stream")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        body: new ReadableStream<Uint8Array>({
          start(controller) {
            if (stream) controller.enqueue(new TextEncoder().encode(stream));
            // Left open: a run in flight does not close its stream.
          },
        }),
      });
    }
    const data = path.includes("/messages")
      ? messages
      : path.includes("/drafts")
        ? []
        : thread(activeRun);
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data }),
    });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("says the turn did not finish when there is no run behind the question", async () => {
  vi.stubGlobal("fetch", serve([ASKED]));

  render(<ResearchThread threadId="t1" />, { wrapper });

  await waitFor(() =>
    expect(screen.getByText(/didn.t finish/i)).toBeInTheDocument(),
  );
  // The question itself is still visible -- it was not lost.
  expect(screen.getByText("what is section 420")).toBeInTheDocument();
});

it("attaches to a run still in flight and shows what it is doing", async () => {
  vi.stubGlobal(
    "fetch",
    serve(
      [ASKED],
      { run_id: "r1", kind: "research", status: "running", current_step: "research" },
      'id: 1\nevent: step\ndata: {"node": "research", "label": "Searching statutes and judgments"}\n\n',
    ),
  );

  render(<ResearchThread threadId="t1" />, { wrapper });

  // One pane, not two. The progress box says everything the wait needs to
  // say, including that it survives a closed page.
  await waitFor(() =>
    expect(screen.getByText(/keeps running whether or not/i)).toBeInTheDocument(),
  );
  // The step arrives over the stream, from a run this tab never started.
  await screen.findByText(/Searching statutes and judgments/i);
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Still researching/i)).not.toBeInTheDocument();
});

it("says nothing when the last turn was answered", async () => {
  vi.stubGlobal(
    "fetch",
    serve([
      ASKED,
      {
        message_id: 2,
        role: "assistant",
        content: "Section 420 covers cheating.",
        answer: null,
        created_at: "2026-09-05T10:02:00+00:00",
      },
    ]),
  );

  render(<ResearchThread threadId="t1" />, { wrapper });

  await screen.findByText("Section 420 covers cheating.");
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();
});

it("says nothing on a brand new, empty thread", async () => {
  vi.stubGlobal("fetch", serve([]));

  render(<ResearchThread threadId="t1" />, { wrapper });

  await screen.findByText("Ask your first question below.");
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();
});

it("does not flash 'didn't finish' between a run ending and its reply arriving", async () => {
  // The gap that made this necessary: the run's stream says `done`, so the
  // thread has no active run, but the reply is still being refetched. For
  // that moment the last message is a question with nothing under it --
  // which is exactly the shape of a turn that died.
  let resolveMessages!: (value: unknown) => void;
  const held = new Promise((resolve) => {
    resolveMessages = resolve;
  });
  let firstMessagesCall = true;

  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string) => {
      const path = String(url);
      if (path.includes("/runs/") && path.endsWith("/stream")) {
        return {
          ok: true,
          status: 200,
          body: new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(
                new TextEncoder().encode(
                  'id: 1\nevent: done\ndata: {"text":"x"}\n\n',
                ),
              );
              controller.close();
            },
          }),
        };
      }
      if (path.includes("/messages")) {
        if (firstMessagesCall) {
          firstMessagesCall = false;
          return {
            ok: true,
            status: 200,
            json: async () => ({ success: true, data: [ASKED] }),
          };
        }
        // The refetch after the run ends: held open, so the test sits in
        // exactly the gap being asserted about.
        await held;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            data: [
              ASKED,
              {
                message_id: 2,
                role: "assistant",
                content: "Section 420 covers cheating.",
                answer: null,
                created_at: "2026-09-05T10:02:00+00:00",
              },
            ],
          }),
        };
      }
      const data = path.includes("/drafts")
        ? []
        : thread({
            run_id: "r1",
            kind: "research",
            status: "running",
            current_step: "draft",
          });
      return { ok: true, status: 200, json: async () => ({ success: true, data }) };
    }),
  );

  render(<ResearchThread threadId="t1" />, { wrapper });

  await waitFor(() => expect(screen.getByText("what is section 420")).toBeInTheDocument());
  // The stream has closed and the refetch is still in flight.
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();

  resolveMessages(null);
  await screen.findByText("Section 420 covers cheating.");
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();
});

it("keeps delivering while the tab is in the background", async () => {
  // What a reader actually does with a two-minute answer: switch tabs.
  //
  // Browsers throttle timers and rAF in a hidden tab, but they do not pause
  // an in-flight response body -- so the stream keeps arriving as long as
  // nothing in our own code gates on visibility. This asserts that nothing
  // does. (The run itself is server-side and does not care either way; that
  // is covered by the QA suite dropping the connection entirely.)
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => "hidden",
  });
  document.dispatchEvent(new Event("visibilitychange"));

  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });

  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const path = String(url);
      if (path.includes("/runs/") && path.endsWith("/stream")) {
        return Promise.resolve({ ok: true, status: 200, body });
      }
      const data = path.includes("/messages")
        ? [ASKED]
        : path.includes("/drafts")
          ? []
          : thread({
              run_id: "r1",
              kind: "research",
              status: "running",
              current_step: "research",
            });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ success: true, data }),
      });
    }),
  );

  render(<ResearchThread threadId="t1" />, { wrapper });
  await waitFor(() =>
    expect(screen.getByText(/keeps running whether or not/i)).toBeInTheDocument(),
  );

  controller.enqueue(
    encoder.encode(
      'id: 1\nevent: step\ndata: {"node":"research","label":"Searching statutes and judgments"}\n\n',
    ),
  );
  await screen.findByText(/Searching statutes and judgments/i);

  controller.enqueue(
    encoder.encode('id: 2\nevent: answer_chunk\ndata: {"text":"Two years."}\n\n'),
  );
  await screen.findByText(/Two years\./);

  // @ts-expect-error -- restore jsdom's own descriptor for the next test
  delete document.visibilityState;
});
