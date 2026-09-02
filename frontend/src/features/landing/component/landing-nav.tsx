import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/molecules/wordmark";

/** Molecule: the public header. Sticky, hairline rule, and the section
 *  links collapse below 640px as the design specifies. */
export function LandingNav() {
  return (
    <nav className="sticky top-0 z-10 flex items-center gap-10 border-b border-line bg-surface-card px-4 py-4 sm:px-10">
      <Wordmark />
      <div className="flex-1" />
      {["Product", "How it works", "Pricing"].map((label) => (
        <a
          key={label}
          href={`#${label.toLowerCase().replace(/\s+/g, "-")}`}
          className="caps hidden text-ink-variant transition-colors duration-[120ms] ease-out hover:text-primary sm:inline"
        >
          {label}
        </a>
      ))}
      <Button asChild size="sm">
        <Link href="/login">Sign in</Link>
      </Button>
    </nav>
  );
}
