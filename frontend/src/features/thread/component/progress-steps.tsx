import { Check, Loader2 } from "lucide-react";

import type { ProgressStep } from "../types";

/**
 * Molecule: the steps the graph has actually finished, plus a spinner for
 * the one still running.
 *
 * There is no progress bar and no timer. A step that sits there for 78
 * seconds is the truth about a slow search, and design/UX_FLOWS.md
 * requires this pane to show real work rather than fake thinking.
 */
export function ProgressSteps({ steps }: { steps: ProgressStep[] }) {
  return (
    <div className="rounded-md border border-line bg-surface-sunken px-4 py-3">
      <ul className="space-y-1.5">
        {steps.map((step) => (
          <li
            key={step.node}
            className="flex items-center gap-2 text-sm text-ink-variant"
          >
            <Check className="size-4 text-ok" />
            {step.label}
          </li>
        ))}
        <li className="flex items-center gap-2 text-sm text-ink-muted">
          <Loader2 className="size-4 animate-spin" />
          {steps.length === 0 ? "Starting research…" : "Working…"}
        </li>
      </ul>
    </div>
  );
}
