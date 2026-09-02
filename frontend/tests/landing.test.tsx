/**
 * The public home page.
 *
 * A visitor with no account has to be able to read it, so it lives outside
 * the `(app)` group that wraps everything in RequireAuth. Logging in is a
 * choice they make, not a wall they hit.
 */

import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { Landing } from "@/features/landing/component/landing";

it("reaches the login screen only when the visitor asks for it", () => {
  render(<Landing />);
  const login = screen.getAllByRole("link", { name: /sign in/i });
  expect(login.length).toBeGreaterThan(0);
  expect(login[0]).toHaveAttribute("href", "/login");
});

it("offers a way to create an account", () => {
  render(<Landing />);
  expect(
    screen.getByRole("link", { name: /start legal research/i }),
  ).toHaveAttribute("href", "/register");
});

it("names its sources without claiming a partnership", () => {
  render(<Landing />);
  expect(screen.getAllByText(/india code/i).length).toBeGreaterThan(0);
  expect(screen.getByText("Supreme Court of India")).toBeInTheDocument();
  // design/UX_FLOWS.md forbids fabricated partnerships and logos.
  expect(screen.queryByText(/partner|endorsed|official tool/i)).not.toBeInTheDocument();
});

it("shows the four-step workflow as a numbered sequence", () => {
  render(<Landing />);
  for (const step of ["1. Ask", "2. Research", "3. Analyze", "4. Verify"]) {
    expect(screen.getByText(step)).toBeInTheDocument();
  }
});

it("shows a research interface mid-run, not an abstract illustration", () => {
  render(<Landing />);
  expect(screen.getByText(/Specific Relief Act, 1963/)).toBeInTheDocument();
  expect(screen.getByText(/Verifying citations/i)).toBeInTheDocument();
});

it("says on the public page that this is not legal advice", () => {
  render(<Landing />);
  expect(screen.getByText(/not legal advice/i)).toBeInTheDocument();
});

it("promises verification in the words the product uses", () => {
  render(<Landing />);
  expect(screen.getByText(/Nothing asserted without support/i)).toBeInTheDocument();
});
