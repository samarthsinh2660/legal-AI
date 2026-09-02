/**
 * Being signed out and being unable to reach the server are different.
 *
 * `useAuth` already keeps the token when `/auth/me` fails for any reason
 * other than 401 -- a server that is merely down must not sign a user out.
 * But `user` stayed null, so the guard bounced to the login screen anyway
 * and the user saw exactly what a signed-out user sees. Their session was
 * intact the whole time.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { AuthProvider } from "@/features/auth/hooks/useAuth";
import { RequireAuth } from "@/features/auth/component/require-auth";
import { TOKEN_KEY } from "@/types/constant";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
});

it("keeps the user where they are when the server cannot be reached", async () => {
  window.localStorage.setItem(TOKEN_KEY, "a-good-token");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  expect(await screen.findByText(/could not reach the server/i)).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
  // The token is theirs and still valid; nothing may discard it.
  expect(window.localStorage.getItem(TOKEN_KEY)).toBe("a-good-token");
});

it("sends a visitor with no token to the login screen", async () => {
  vi.stubGlobal("fetch", vi.fn());

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
});

it("sends a spent token to the login screen", async () => {
  window.localStorage.setItem(TOKEN_KEY, "expired");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false, status: 401,
    json: async () => ({ success: false, error: { code: "unauthorized", message: "no" } }),
  }));

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
});

it("renders the app for a signed-in user", async () => {
  window.localStorage.setItem(TOKEN_KEY, "good");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ success: true, data: { user_id: "u1", email: "a@b.c" } }),
  }));

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  expect(await screen.findByText("the app")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
});
