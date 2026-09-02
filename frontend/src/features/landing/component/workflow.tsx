import { CircleHelp, ClipboardList, ShieldCheck, Search } from "lucide-react";

import { LandingSectionHead } from "./section-head";

/** Molecule: the four-step workflow, numbered because it is a sequence --
 *  each step consumes what the one before it produced. */
const STEPS = [
  { icon: CircleHelp, title: "1. Ask",
    body: "Pose complex legal questions in natural language." },
  { icon: Search, title: "2. Research",
    body: "Queries statutes, judgments and live court sources in parallel." },
  { icon: ClipboardList, title: "3. Analyze",
    body: "Synthesizes precedents, statutes and the facts of your matter." },
  { icon: ShieldCheck, title: "4. Verify",
    body: "Every claim checked against its source before you see it." },
] as const;

export function Workflow() {
  return (
    <section id="how-it-works" className="border-t border-line py-[72px]">
      <LandingSectionHead
        title="The Computational Research Workflow"
        lede="A rigorous process ensuring reliability at every step."
      />
      <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="rounded-md border border-line bg-surface-card p-6 text-center"
          >
            <div className="mx-auto mb-4 flex size-11 items-center justify-center rounded-full bg-surface-tint text-primary">
              <Icon className="size-5" />
            </div>
            <h4 className="mb-1.5 font-sans text-sm font-semibold tracking-normal text-ink">
              {title}
            </h4>
            <p className="text-sm leading-[1.55] text-ink-variant">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
