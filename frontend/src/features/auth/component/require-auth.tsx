"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { PageLoader } from "@/components/molecules/loading";
import { useAuth } from "../hooks/useAuth";

/**
 * The gate on every authenticated route.
 *
 * Client-side because the token lives in localStorage, which no server
 * component can read. That means the check is a convenience, not a
 * security boundary -- the API refuses an unauthenticated request on its
 * own, and that is what actually protects the data.
 *
 * Rendering the loader while `isLoading` matters: routing on `!user`
 * alone would bounce a signed-in user to /login on every refresh, before
 * the stored token has been checked.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading, unreachable } = useAuth();
  const router = useRouter();

  useEffect(() => {
    // `unreachable` means the token is still good and the server did not
    // answer. Sending them to the login screen would say they are signed
    // out, which is not true and which signing in again cannot fix.
    if (!isLoading && !user && !unreachable) router.replace("/login");
  }, [isLoading, user, unreachable, router]);

  if (isLoading) return <PageLoader />;

  if (!user && unreachable) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-heading">Could not reach the server</h1>
        <p className="max-w-md text-ink-variant">
          You are still signed in. The research service is not answering —
          it may be starting up.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded border border-line px-4 py-2 text-sm font-medium text-ink transition-colors duration-[120ms] ease-out hover:bg-surface-sunken"
        >
          Try again
        </button>
      </main>
    );
  }

  if (!user) return null;
  return <>{children}</>;
}
