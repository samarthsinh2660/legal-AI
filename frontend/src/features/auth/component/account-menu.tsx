"use client";

import Link from "next/link";
import { LogOut } from "lucide-react";

import { useAuth } from "../hooks/useAuth";

/**
 * Organism: reads the session, so it owns the signed-out case.
 *
 * Lives at the foot of the sidebar, not in a top bar. Who you are signed in
 * as belongs with the rest of the persistent chrome; a header carrying only
 * an avatar was a 64px strip of empty rule across every page.
 *
 * The name and avatar are a link to the profile; sign-out is a button
 * beside it rather than inside it, so leaving is never one stray click
 * away from a page you meant to open.
 */
export function AccountMenu() {
  const { user, signOut } = useAuth();
  if (!user) return null;

  // The name when there is one. Accounts made before names existed fall
  // back to the address -- a name guessed from it would be a fabrication
  // in the one place a reader trusts.
  const label = user.name || user.email;
  // Initials off whichever is shown, so they always match the label.
  const initials = label.slice(0, 2).toUpperCase();

  return (
    <div className="flex items-center gap-2 border-t border-line pt-3 lg:gap-3">
      <Link
        href="/profile"
        title={user.name ? `${user.name} — ${user.email}` : user.email}
        className="flex min-w-0 flex-1 items-center gap-3 rounded p-1 transition-colors duration-[120ms] ease-out hover:bg-surface-sunken"
      >
        <span className="flex size-[34px] shrink-0 items-center justify-center rounded-full bg-surface-tint text-xs font-semibold text-primary">
          {initials}
        </span>
        <span className="hidden min-w-0 flex-1 lg:block">
          <span className="block truncate text-sm font-semibold text-ink">
            {label}
          </span>
          <span className="caps block text-ink-muted">View profile</span>
        </span>
      </Link>

      <button
        type="button"
        title="Sign out"
        aria-label="Sign out"
        onClick={() => void signOut()}
        className="hidden size-9 shrink-0 items-center justify-center rounded text-ink-variant transition-colors duration-[120ms] ease-out hover:bg-surface-sunken hover:text-ink lg:flex"
      >
        <LogOut className="size-[18px]" />
      </button>
    </div>
  );
}
