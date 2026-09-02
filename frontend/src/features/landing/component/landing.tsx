import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Capabilities } from "./capabilities";
import { HeroDemo } from "./hero-demo";
import { LandingNav } from "./landing-nav";
import { Pillars } from "./pillars";
import { SourceStrip } from "./source-strip";
import { Workflow } from "./workflow";

/**
 * Screen 1 in design/UX_FLOWS.md. Public: no session, no fetch, no hook,
 * which is why it sits outside the `(app)` group that wraps everything in
 * RequireAuth.
 *
 * Composes the sections; each is its own molecule.
 */
export function Landing() {
  return (
    <div className="min-h-screen bg-surface">
      <LandingNav />

      <div className="mx-auto max-w-[1280px] px-4 sm:px-10">
        <section className="grid items-center gap-12 py-14 lg:grid-cols-2 lg:py-[88px] lg:pb-24">
          <div>
            <h1 className="mb-6 text-display leading-[1.15]">
              Research Indian Law with Evidence, Not Guesswork.
            </h1>
            <p className="mb-8 max-w-[46ch] text-lg leading-[1.6] text-ink-variant">
              AI-powered legal research, case analysis, document
              understanding, and citation-verified answers grounded strictly
              in authoritative Indian legal sources.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild>
                <Link href="/register">Start Legal Research</Link>
              </Button>
              <Button asChild variant="outline">
                <a href="#how-it-works">Explore How It Works</a>
              </Button>
            </div>
          </div>

          <HeroDemo />
        </section>

        <Workflow />
        <Capabilities />
        <Pillars />
        <SourceStrip />

        {/* The design's own footer line. Kept because it is true: the
            corpus is partial and nothing here is legal advice. */}
        <div className="border-t border-line pb-12 pt-8 text-center text-sm text-ink-muted">
          Pramāṇa AI researches primary Indian legal sources. It is legal
          information, not legal advice, and no lawyer-client relationship
          arises from its use.
        </div>
      </div>
    </div>
  );
}
