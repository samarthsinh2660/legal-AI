/**
 * One question must produce one turn.
 *
 * The handed-over question lived in `?ask=` and stayed there. A ref guarded
 * the effect within a single mount, but a reload or a back-navigation
 * mounted the component again and asked the same question a second time --
 * and the thread, having already answered it, replayed in under a second.
 * The reader saw one question three times over.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { ResearchThread } from "@/features/thread/component/research-thread";
import { shortLabel } from "@/features/thread/evidence";
import { Verification } from "@/features/thread/types";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function serve() {
  return vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      String(url).includes("/stream")
        ? { ok: true, status: 200, body: null, text: async () => "" }
        : {
            ok: true,
            status: 200,
            json: async () => ({ success: true, data: [] }),
          },
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  replace.mockClear();
});

it("takes the question out of the URL as soon as it is asked", async () => {
  vi.stubGlobal("fetch", serve());

  render(
    <ResearchThread
      threadId="t1"
      initialQuestion="When is anticipatory bail granted?"
      initialMode={Verification.Quick}
    />,
    { wrapper },
  );

  // Nothing left in the address bar to re-fire on the next mount.
  await waitFor(() =>
    expect(replace).toHaveBeenCalledWith("/research/t1", { scroll: false }),
  );
});

it("does not ask again when the same thread is opened without the question", async () => {
  const fetch = serve();
  vi.stubGlobal("fetch", fetch);

  render(<ResearchThread threadId="t1" />, { wrapper });

  await screen.findByLabelText("Ask a follow-up");
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).includes("/stream")),
  ).toHaveLength(0);
});

it("labels a section by its number, whatever the Act id looks like", () => {
  // The codes ingested in September are named, not numbered, and the old
  // pattern required digits -- so this rendered as the raw identifier.
  expect(shortLabel("act:crpc-1973:sec-438")).toBe("s. 438");
  expect(shortLabel("act:2189:sec-138")).toBe("s. 138");
  expect(shortLabel("act:ipc-1860:sec-302")).toBe("s. 302");
});

it("tells two judgments apart by their citation", () => {
  // Three cited authorities all rendered as "judgment" before.
  expect(shortLabel("judgment:lavesh", "[2012] 7 S.C.R. 469")).toBe(
    "[2012] 7 S.C.R. 469",
  );
  expect(shortLabel("judgment:x")).toBe("judgment");
});
