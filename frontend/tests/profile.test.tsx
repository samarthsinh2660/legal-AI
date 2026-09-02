/**
 * The display name.
 *
 * The sidebar showed an email address, which is a login credential and not
 * what anyone calls themselves. Registration now asks for a name, the
 * sidebar shows it, and the profile screen is where it is changed.
 *
 * The name is the only editable field: changing an address re-keys the
 * account and wants a confirmation round trip, and changing a password
 * wants the old one. Both are shown as facts here, not as inputs.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { AuthProvider } from "@/features/auth/hooks/useAuth";
import { AccountMenu } from "@/features/auth/component/account-menu";
import { ProfileView } from "@/features/auth/component/profile-view";
import { TOKEN_KEY } from "@/types/constant";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

function signedIn(name: string | null) {
  const claims = { sub: "u1", exp: Math.floor(Date.now() / 1000) + 3600 };
  window.localStorage.setItem(TOKEN_KEY, `h.${btoa(JSON.stringify(claims))}.s`);
  window.localStorage.setItem(
    "pramana_user",
    JSON.stringify({ user_id: "u1", email: "advocate@example.com", name }),
  );
}

function servesProfile(name: string | null) {
  return vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
    const saved =
      init?.method === "PATCH"
        ? JSON.parse(String(init.body)).name
        : name;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: {
          user_id: "u1",
          email: "advocate@example.com",
          name: saved,
          created_at: "2026-09-02T17:20:41Z",
        },
      }),
    });
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

it("shows the name in the sidebar, not the email", async () => {
  vi.stubGlobal("fetch", vi.fn());
  signedIn("Samarth Sinh");

  render(<AccountMenu />, { wrapper });

  expect(await screen.findByText("Samarth Sinh")).toBeInTheDocument();
  expect(screen.queryByText("advocate@example.com")).not.toBeInTheDocument();
});

it("falls back to the address for an account made before names existed", async () => {
  // Never a name guessed from the address: this is the one place a reader
  // trusts to be about them.
  vi.stubGlobal("fetch", vi.fn());
  signedIn(null);

  render(<AccountMenu />, { wrapper });

  expect(await screen.findByText("advocate@example.com")).toBeInTheDocument();
});

it("links the account block to the profile", async () => {
  vi.stubGlobal("fetch", vi.fn());
  signedIn("Samarth Sinh");

  render(<AccountMenu />, { wrapper });

  await waitFor(() =>
    expect(screen.getByRole("link", { name: /Samarth Sinh/ })).toHaveAttribute(
      "href",
      "/profile",
    ),
  );
});

it("shows the details, including when the account was made", async () => {
  vi.stubGlobal("fetch", servesProfile("Samarth Sinh"));
  signedIn("Samarth Sinh");

  render(<ProfileView />, { wrapper });

  expect(await screen.findByText("advocate@example.com")).toBeInTheDocument();
  expect(screen.getByText("2 September 2026")).toBeInTheDocument();
  expect(screen.getByText("u1")).toBeInTheDocument();
});

it("saves a new name and updates the sidebar with it", async () => {
  const fetch = servesProfile("Old Name");
  vi.stubGlobal("fetch", fetch);
  signedIn("Old Name");

  render(
    <>
      <AccountMenu />
      <ProfileView />
    </>,
    { wrapper },
  );

  await screen.findByRole("button", { name: "Edit name" });
  await userEvent.click(screen.getByRole("button", { name: "Edit name" }));

  const box = screen.getByLabelText("Name");
  await userEvent.clear(box);
  await userEvent.type(box, "New Name");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));

  // The sidebar reads the stored session, not the profile query, so it
  // only shows the new name if the save wrote through to it.
  await waitFor(() =>
    expect(screen.getByRole("link", { name: /New Name/ })).toBeInTheDocument(),
  );
});

it("refuses to save a blank name", async () => {
  // Saving an empty box would silently drop the name the user had.
  const fetch = servesProfile("Keep Me");
  vi.stubGlobal("fetch", fetch);
  signedIn("Keep Me");

  render(<ProfileView />, { wrapper });

  await userEvent.click(await screen.findByRole("button", { name: "Edit name" }));
  await userEvent.clear(screen.getByLabelText("Name"));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByText(/A name is required/i)).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({ method: "PATCH" }),
  );
});

it("offers no way to edit the password", async () => {
  // Absent rather than half-built.
  vi.stubGlobal("fetch", servesProfile("Samarth Sinh"));
  signedIn("Samarth Sinh");

  render(<ProfileView />, { wrapper });

  await screen.findByText("advocate@example.com");
  expect(screen.queryByRole("button", { name: /change password/i })).not.toBeInTheDocument();
});

it("asks for the password before moving the address", async () => {
  // A token alone must not be enough: the address is the sign-in handle.
  vi.stubGlobal("fetch", servesProfile("Samarth Sinh"));
  signedIn("Samarth Sinh");

  render(<ProfileView />, { wrapper });

  await userEvent.click(await screen.findByRole("button", { name: "Edit email" }));

  expect(screen.getByLabelText(/confirm with your current password/i)).toBeInTheDocument();
  // And says what it costs, before they commit rather than after.
  expect(screen.getByText(/no confirmation email/i)).toBeInTheDocument();
});

it("refuses to submit an email change with no password", async () => {
  const fetch = servesProfile("Samarth Sinh");
  vi.stubGlobal("fetch", fetch);
  signedIn("Samarth Sinh");

  render(<ProfileView />, { wrapper });

  await userEvent.click(await screen.findByRole("button", { name: "Edit email" }));
  await userEvent.click(screen.getByRole("button", { name: "Change email" }));

  expect(await screen.findByText(/current password is required/i)).toBeInTheDocument();
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).includes("/profile/email")),
  ).toHaveLength(0);
});
