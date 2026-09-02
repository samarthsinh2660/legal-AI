/**
 * A thread inside a case has to say so.
 *
 * Without this a case-attached thread renders identically to a loose one,
 * so a reader cannot tell whether the answers were seeded with the
 * matter's context -- which is the only reason to attach a thread at all.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { ThreadCaseBanner } from "@/features/thread/component/thread-case-banner";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function serve(byPath: Record<string, unknown>) {
  return vi.fn().mockImplementation((url: string) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const data = byPath[path];
    return Promise.resolve({
      ok: data !== undefined,
      status: data === undefined ? 404 : 200,
      json: async () =>
        data === undefined
          ? { success: false, error: { code: "not_found", message: "no" } }
          : { success: true, data },
    });
  });
}

const THREAD = {
  thread_id: "t1",
  title: "Refund",
  case_id: "c1",
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

const CASE = {
  case_id: "c1",
  title: "Iyer v. Meridian Estates",
  court: null, state: null, case_number: null, parties: [],
  matter_type: null, status: null, description: null,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

afterEach(() => vi.unstubAllGlobals());

it("names the matter and links back to it", async () => {
  vi.stubGlobal("fetch", serve({ "/threads/t1": THREAD, "/cases/c1": CASE }));
  render(<ThreadCaseBanner threadId="t1" />, { wrapper });

  const link = await screen.findByRole("link");
  expect(link).toHaveAttribute("href", "/cases/c1");
  expect(await screen.findByText(/Iyer v\. Meridian Estates/)).toBeInTheDocument();
});

it("says the answers start from the matter's context", async () => {
  vi.stubGlobal("fetch", serve({ "/threads/t1": THREAD, "/cases/c1": CASE }));
  render(<ThreadCaseBanner threadId="t1" />, { wrapper });

  expect(await screen.findByText(/starts from the matter/i)).toBeInTheDocument();
});

it("shows nothing for a thread that belongs to no case", async () => {
  vi.stubGlobal("fetch", serve({ "/threads/t1": { ...THREAD, case_id: null } }));
  const { container } = render(<ThreadCaseBanner threadId="t1" />, { wrapper });

  await waitFor(() => expect(container).toBeEmptyDOMElement());
});

it("still links back when the case itself cannot be loaded", async () => {
  // The thread knows its case_id even when the case fetch fails; dropping
  // the banner would strand the reader with no way back to the matter.
  vi.stubGlobal("fetch", serve({ "/threads/t1": THREAD }));
  render(<ThreadCaseBanner threadId="t1" />, { wrapper });

  const link = await screen.findByRole("link");
  expect(link).toHaveAttribute("href", "/cases/c1");
});
