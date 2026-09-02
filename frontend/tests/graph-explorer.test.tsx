/**
 * The graph screen.
 *
 * It opened on an empty box asking the reader to guess a document name.
 * Now it browses: named slices, a hundred nodes at a time. Drawing all
 * 50,890 is not the alternative -- a force layout stops being readable
 * long before that.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { GraphExplorer } from "@/features/graph/component/graph-explorer";

function provider({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function serve(nodes: number, truncated: boolean) {
  return vi.fn().mockImplementation((url: string) => {
    const offset = Number(new URL(url, "http://x").searchParams.get("offset") ?? 0);
    return Promise.resolve({
      ok: true, status: 200,
      json: async () => ({
        success: true,
        data: {
          nodes: Array.from({ length: nodes }, (_, i) => ({
            id: `judgment:${offset + i}`, kind: "Judgment",
            title: `Case ${offset + i}`, hops: 0,
          })),
          edges: [],
          truncated,
        },
      }),
    });
  });
}

afterEach(() => vi.unstubAllGlobals());

it("draws a slice without asking the reader to search first", async () => {
  vi.stubGlobal("fetch", serve(3, false));
  render(<GraphExplorer />, { wrapper: provider });

  expect(await screen.findByText(/3 nodes/)).toBeInTheDocument();
  // The search box is gone: slices are how a reader browses now.
  expect(screen.queryByPlaceholderText(/find a judgment/i)).not.toBeInTheDocument();
});

it("offers named slices instead of hop counts", async () => {
  vi.stubGlobal("fetch", serve(2, false));
  render(<GraphExplorer />, { wrapper: provider });

  expect(await screen.findByRole("button", { name: "Judgments" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Indian Penal Code" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /hop/i })).not.toBeInTheDocument();
});

it("offers more only when another batch exists", async () => {
  vi.stubGlobal("fetch", serve(2, true));
  render(<GraphExplorer />, { wrapper: provider });

  expect(await screen.findByRole("button", { name: /load 100 more/i })).toBeInTheDocument();
});

it("does not offer more when the slice is complete", async () => {
  vi.stubGlobal("fetch", serve(2, false));
  render(<GraphExplorer />, { wrapper: provider });

  await screen.findByText(/2 nodes/);
  expect(screen.queryByRole("button", { name: /load 100 more/i })).not.toBeInTheDocument();
});

it("shows a way back when a citation centred it on one document", async () => {
  vi.stubGlobal("fetch", serve(1, false));
  render(<GraphExplorer initialAnchor="act:2189:sec-138" />, { wrapper: provider });

  await waitFor(() =>
    expect(screen.getByText(/Centred on act:2189:sec-138/)).toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: /back to the graph/i })).toBeInTheDocument();
});

it("says why a slice has no connections instead of drawing loose dots", async () => {
  // The IPC landed after the judgments, so nothing cites its sections yet.
  vi.stubGlobal("fetch", serve(3, false));
  render(<GraphExplorer />, { wrapper: provider });

  expect(await screen.findByText(/no judgment we hold cites them yet/i)).toBeInTheDocument();
});
