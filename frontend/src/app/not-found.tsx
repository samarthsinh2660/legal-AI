import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/molecules/wordmark";

/**
 * The 404. Its own page rather than a redirect to `/`.
 *
 * Silently landing someone on the home page hides the fact that the link
 * they followed was wrong -- they look for what they clicked, do not find
 * it, and cannot tell whether the product moved it or lost it. Saying so
 * costs one screen.
 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-5 bg-surface p-6 text-center">
      <Wordmark />

      <p className="caps text-ink-muted">Error 404</p>
      <h1 className="max-w-lg text-title">This page does not exist</h1>
      <p className="max-w-md leading-[1.7] text-ink-variant">
        The link may be out of date, or the matter or thread it pointed at
        may have been deleted. Nothing has gone wrong with your account.
      </p>

      <div className="mt-2 flex flex-wrap justify-center gap-3">
        <Button asChild>
          <Link href="/dashboard">Go to your dashboard</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/research/new">Start new research</Link>
        </Button>
      </div>
    </main>
  );
}
