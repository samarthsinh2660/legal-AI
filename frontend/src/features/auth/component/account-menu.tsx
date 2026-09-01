"use client";

import { LogOut } from "lucide-react";

import { useAuth } from "../hooks/useAuth";

/** Organism: reads the session, so it owns the signed-out case. */
export function AccountMenu() {
  const { user, signOut } = useAuth();
  if (!user) return null;

  // Two letters off the address. It is not a name -- the API stores none --
  // but it is stable, and it is what the reader recognises as themselves.
  const initials = user.email.slice(0, 2).toUpperCase();

  return (
    <div className="flex items-center gap-3">
      <div className="flex size-[34px] shrink-0 items-center justify-center rounded-full bg-surface-tint text-xs font-semibold text-primary">
        {initials}
      </div>
      <div className="hidden sm:block">
        <div className="text-sm font-semibold text-ink">{user.email}</div>
        <div className="caps text-ink-muted">Signed in</div>
      </div>
      <button
        type="button"
        title="Sign out"
        onClick={() => void signOut()}
        className="flex size-9 items-center justify-center rounded text-ink-variant transition-colors duration-[120ms] ease-out hover:bg-surface-sunken hover:text-ink"
      >
        <LogOut className="size-[18px]" />
      </button>
    </div>
  );
}
