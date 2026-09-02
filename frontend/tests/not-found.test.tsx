/**
 * The 404.
 *
 * Redirecting to `/` instead would hide the broken link: the reader looks
 * for what they clicked, does not find it, and cannot tell whether the
 * product moved it or lost it.
 */

import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import NotFound from "@/app/not-found";

it("says the page does not exist rather than pretending nothing happened", () => {
  render(<NotFound />);
  expect(screen.getByText(/does not exist/i)).toBeInTheDocument();
  expect(screen.getByText(/404/)).toBeInTheDocument();
});

it("reassures that the account is fine", () => {
  // A dead link and a lost session look identical to a reader, and one of
  // them is frightening.
  render(<NotFound />);
  expect(screen.getByText(/nothing has gone wrong with your account/i)).toBeInTheDocument();
});

it("offers a way onward without deciding for them", () => {
  render(<NotFound />);
  expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/dashboard");
  expect(screen.getByRole("link", { name: /new research/i })).toHaveAttribute("href", "/research/new");
});
