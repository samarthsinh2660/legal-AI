/**
 * A thread reopened after an interrupted turn -- a refresh, a closed tab,
 * a timeout mid-research -- must say so, not sit there as though nothing
 * had been asked.
 *
 * The question is now stored before research runs (api/threads/controller.py),
 * so this state is reachable: the last message is from the user, with no
 * reply after it.
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

function serveMessages(messages: unknown[]) {
  return vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      String(url).includes("/messages")
        ? { ok: true, status: 200, json: async () => ({ success: true, data: messages }) }
        : { ok: true, status: 200, json: async () => ({ success: true, data: [] }) },
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("says the turn did not finish when the last message has no reply", async () => {
  vi.stubGlobal(
    "fetch",
    serveMessages([
      {
        message_id: 1,
        role: "user",
        content: "what is section 420",
        answer: null,
        created_at: new Date().toISOString(),
      },
    ]),
  );

  render(<ResearchThread threadId="t1" />, { wrapper });

  await waitFor(() =>
    expect(screen.getByText(/didn.t finish/i)).toBeInTheDocument(),
  );
  // The question itself is still visible -- it was not lost.
  expect(screen.getByText("what is section 420")).toBeInTheDocument();
});

it("says nothing when the last turn was answered", async () => {
  vi.stubGlobal(
    "fetch",
    serveMessages([
      {
        message_id: 1,
        role: "user",
        content: "what is section 420",
        answer: null,
        created_at: new Date().toISOString(),
      },
      {
        message_id: 2,
        role: "assistant",
        content: "Section 420 covers cheating.",
        answer: null,
        created_at: new Date().toISOString(),
      },
    ]),
  );

  render(<ResearchThread threadId="t1" />, { wrapper });

  await screen.findByText("Section 420 covers cheating.");
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();
});

it("says nothing on a brand new, empty thread", async () => {
  vi.stubGlobal("fetch", serveMessages([]));

  render(<ResearchThread threadId="t1" />, { wrapper });

  await screen.findByText("Ask your first question below.");
  expect(screen.queryByText(/didn.t finish/i)).not.toBeInTheDocument();
});
