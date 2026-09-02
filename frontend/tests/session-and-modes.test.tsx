/**
 * Two things a reader noticed, and what they should do instead.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { AuthProvider } from "@/features/auth/hooks/useAuth";
import { RedirectIfSignedIn } from "@/features/auth/component/redirect-if-signed-in";
import { NewResearch } from "@/features/thread/component/new-research";
import { TOKEN_KEY } from "@/types/constant";

const replace = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push }) }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  replace.mockClear();
  push.mockClear();
});

describe("a live session is not asked to sign in again", () => {
  it("sends a signed-in visitor to the dashboard", async () => {
    const claims = { sub: "u", exp: Math.floor(Date.now() / 1000) + 3600 };
    window.localStorage.setItem(TOKEN_KEY, `h.${btoa(JSON.stringify(claims))}.s`);
    window.localStorage.setItem(
      "pramana_user",
      JSON.stringify({ user_id: "u", email: "a@b.c" }),
    );
    vi.stubGlobal("fetch", vi.fn());

    render(<RedirectIfSignedIn><p>the login form</p></RedirectIfSignedIn>, { wrapper });

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("the login form")).not.toBeInTheDocument();
  });

  it("still shows the form to someone with no session", async () => {
    vi.stubGlobal("fetch", vi.fn());

    render(<RedirectIfSignedIn><p>the login form</p></RedirectIfSignedIn>, { wrapper });

    expect(await screen.findByText("the login form")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("the new-research screen", () => {
  it("offers the verification choice before the question is asked", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NewResearch />, { wrapper });

    expect(await screen.findByRole("button", { name: /verified/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /quick/i })).toBeInTheDocument();
  });

  it("creates no thread until a question is actually sent", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<NewResearch />, { wrapper });

    // Opening the screen must leave nothing behind, or every click of
    // "New Research" would litter the sidebar with empty threads.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses an empty question rather than creating a thread", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<NewResearch />, { wrapper });
    (await screen.findByRole("button", { name: /ask legal ai/i })).click();

    expect(await screen.findByText(/ask a question first/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
