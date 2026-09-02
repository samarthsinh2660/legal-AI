/**
 * The activity screen.
 *
 * A refusal has to read differently from an ordinary row -- someone
 * reaching for a matter that is not theirs is what a firm looks for first.
 */

import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { AuditTrail } from "@/features/audit/component/audit-trail";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function serve(items: unknown[], total = items.length) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      success: true,
      data: { items, total, limit: 50, offset: 0, has_more: false },
    }),
  });
}

const ALLOWED = {
  event_id: 1, action: "read", resource_type: "case",
  resource_id: "c1", status: 200, at: "2026-09-02T10:00:00Z",
};
const REFUSED = {
  event_id: 2, action: "read", resource_type: "case",
  resource_id: "not-mine", status: 404, at: "2026-09-02T10:01:00Z",
};

afterEach(() => vi.unstubAllGlobals());

it("marks a refused attempt as refused", async () => {
  vi.stubGlobal("fetch", serve([REFUSED]));
  render(<AuditTrail />, { wrapper });

  expect(await screen.findByText("refused")).toBeInTheDocument();
  expect(screen.queryByText("allowed")).not.toBeInTheDocument();
});

it("marks an ordinary action as allowed", async () => {
  vi.stubGlobal("fetch", serve([ALLOWED]));
  render(<AuditTrail />, { wrapper });

  expect(await screen.findByText("allowed")).toBeInTheDocument();
});

it("shows which resource was touched", async () => {
  vi.stubGlobal("fetch", serve([ALLOWED]));
  render(<AuditTrail />, { wrapper });

  expect(await screen.findByText("c1")).toBeInTheDocument();
});

it("says plainly that questions and answers are not recorded here", async () => {
  vi.stubGlobal("fetch", serve([]));
  render(<AuditTrail />, { wrapper });

  expect(
    await screen.findByText(/not recorded here|not what was said/i),
  ).toBeInTheDocument();
});

it("does not read an empty trail as an error", async () => {
  vi.stubGlobal("fetch", serve([]));
  render(<AuditTrail />, { wrapper });

  expect(await screen.findByText(/nothing recorded yet/i)).toBeInTheDocument();
  expect(screen.queryByText(/could not load/i)).not.toBeInTheDocument();
});
