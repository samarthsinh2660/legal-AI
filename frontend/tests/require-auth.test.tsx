/**
 * The gate reads the session from storage and makes no request.
 *
 * It used to ask `/auth/me` on every page load, which cost a round trip to
 * learn what was already on disk and made a down server look like being
 * signed out. Boot is now entirely local, so a server that is merely
 * unreachable cannot sign anyone out -- there is nothing left to fail.
 *
 * Expiry comes from the token's own `exp`. That claim is editable by the
 * user, so it is trusted for one thing only: deciding not to bother. A
 * forged later `exp` still 401s at the API.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { AuthProvider, useAuth } from "@/features/auth/hooks/useAuth";
import { RequireAuth } from "@/features/auth/component/require-auth";
import { TOKEN_KEY } from "@/types/constant";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

/** A token shaped like the real one: the payload is what `session.read`
 *  inspects, and nothing here checks a signature. */
function token(expiresInSeconds: number) {
  const claims = { sub: "u1", exp: Math.floor(Date.now() / 1000) + expiresInSeconds };
  return `header.${btoa(JSON.stringify(claims))}.signature`;
}

function signedIn(expiresInSeconds = 3600) {
  window.localStorage.setItem(TOKEN_KEY, token(expiresInSeconds));
  window.localStorage.setItem(
    "pramana_user",
    JSON.stringify({ user_id: "u1", email: "a@b.c" }),
  );
}

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

it("renders the app for a signed-in user without calling the server", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  signedIn();

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  expect(await screen.findByText("the app")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
  // The whole point: boot asks nobody anything.
  expect(fetch).not.toHaveBeenCalled();
});

it("keeps the user signed in when the server cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
  signedIn();

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  expect(await screen.findByText("the app")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
});

it("sends a visitor with no token to the login screen", async () => {
  vi.stubGlobal("fetch", vi.fn());

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
});

it("sends a spent token to the login screen and discards it", async () => {
  vi.stubGlobal("fetch", vi.fn());
  signedIn(-60);

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
});

it("discards a token whose expiry cannot be read", async () => {
  vi.stubGlobal("fetch", vi.fn());
  window.localStorage.setItem(TOKEN_KEY, "not-a-jwt");
  window.localStorage.setItem("pramana_user", JSON.stringify({ user_id: "u1", email: "a@b.c" }));

  render(<RequireAuth><p>the app</p></RequireAuth>, { wrapper });

  // Not one we issued. Treating it as valid forever is the wrong way to be wrong.
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
});

it("signs in with one request, not two", async () => {
  // Login used to be followed by /auth/me to learn the identity. It now
  // comes back with the token.
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      success: true,
      data: {
        access_token: token(3600),
        token_type: "bearer",
        user_id: "u1",
        email: "a@b.c",
      },
    }),
  });
  vi.stubGlobal("fetch", fetch);

  function SignIn() {
    const { signIn, user } = useAuth();
    return (
      <>
        <button onClick={() => void signIn({ email: "a@b.c", password: "x".repeat(12) })}>
          go
        </button>
        {user && <p>{user.email}</p>}
      </>
    );
  }

  render(<SignIn />, { wrapper });
  (await screen.findByText("go")).click();

  expect(await screen.findByText("a@b.c")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(String(fetch.mock.calls[0][0])).toContain("/auth/login");
});
