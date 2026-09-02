import {
  BookOpenCheck,
  FileText,
  Layers,
  Search,
  Share2,
  ShieldCheck,
} from "lucide-react";

import { LandingSectionHead } from "./section-head";

/** Molecule: what the product does. Six cards, wording from the design. */
const CAPABILITIES = [
  { icon: Search, title: "Legal Research",
    body: "Ask in plain language; receive a structured answer with the statutes and judgments that support each proposition." },
  { icon: FileText, title: "Document Analysis",
    body: "Upload a deed, notice or brief. Parties, dates, clauses, provisions and risks are extracted with page references." },
  { icon: Layers, title: "Case Analysis",
    body: "Build a matter workspace: timeline, issues, arguments and every authority you have relied on, in one place." },
  { icon: Share2, title: "Legal Knowledge Graph",
    body: "See how a section is interpreted, which judgment follows which, and where an authority has been overruled." },
  { icon: ShieldCheck, title: "Citation Verification",
    body: "Each citation is checked for existence, relevant paragraph, jurisdiction and current precedent status." },
  { icon: BookOpenCheck, title: "Statutory Research",
    body: "Browse Acts section by section, with legislative history and the judgments that interpret each provision." },
] as const;

export function Capabilities() {
  return (
    <section id="product" className="border-t border-line py-[72px]">
      <LandingSectionHead title="Built for Indian legal practice" />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
        {CAPABILITIES.map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="flex flex-col gap-2 rounded-md border border-line bg-surface-card p-6"
          >
            <Icon className="mb-1 size-[22px] text-primary" />
            <h4 className="text-statute">{title}</h4>
            <p className="text-sm leading-[1.55] text-ink-variant">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
