import { Loader2, ListChecks, Search } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Molecule: the hero visual -- a research interface mid-run.
 *
 * design/UX_FLOWS.md asks for "a realistic research interface mid-run"
 * rather than an abstract AI illustration, and these are the product's own
 * step labels. The spinner is the only motion on the page; it stops under
 * prefers-reduced-motion, where the step still reads correctly.
 */
const STEPS = [
  { icon: Loader2, label: "Searching India Code (Specific Relief Act, 1963)…", running: true },
  { icon: Search, label: "Analyzing Supreme Court precedents…", running: false },
  { icon: ListChecks, label: "Verifying citations…", running: false },
] as const;

export function HeroDemo() {
  return (
    <div className="overflow-hidden rounded-md border border-line bg-surface-card shadow-2">
      <div className="flex gap-1.5 border-b border-line px-4 py-3.5">
        {[0, 1, 2].map((dot) => (
          <i key={dot} className="size-2.5 rounded-full bg-surface-muted" />
        ))}
      </div>

      <div className="flex min-h-[300px] flex-col gap-4 p-6">
        <p className="rounded border border-line px-4 py-3.5 text-sm leading-[1.6] text-ink">
          &ldquo;What legal remedies may be available if someone is occupying
          my property without permission in Gujarat?&rdquo;
        </p>

        {STEPS.map(({ icon: Icon, label, running }) => (
          <div
            key={label}
            className={cn(
              "flex items-center gap-3 text-sm",
              running ? "text-ink" : "text-ink-muted",
            )}
          >
            <span
              className={cn(
                "flex size-5 shrink-0 items-center justify-center",
                running ? "text-primary" : "text-line-strong",
              )}
            >
              <Icon className={cn("size-4", running && "spin")} />
            </span>
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
