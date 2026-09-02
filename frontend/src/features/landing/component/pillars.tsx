import { LandingSectionHead } from "./section-head";

/** Molecule: the three pillars. The eyebrow is the product's own
 *  provenance vocabulary, so a reader meets it here before an answer. */
const PILLARS = [
  { eyebrow: "Trusted knowledge", title: "A curated foundation, not a scrape",
    body: "The Constitution, India Code legislation and settled Supreme Court authority are ingested, normalised and versioned before any question is asked." },
  { eyebrow: "Dynamic research", title: "Current, matter-specific evidence",
    body: "For every question, live court and legislation sources are searched so the answer reflects what is current — not a stale snapshot." },
  { eyebrow: "Verified answers", title: "Nothing asserted without support",
    body: "A verification pass checks each claim against its cited source. Anything unsupported triggers more research instead of a confident guess." },
] as const;

export function Pillars() {
  return (
    <section className="border-t border-line py-[72px]">
      <LandingSectionHead title="Why this is different" />
      <div className="grid gap-6 lg:grid-cols-3">
        {PILLARS.map(({ eyebrow, title, body }) => (
          <div
            key={eyebrow}
            className="rounded-md border border-line bg-surface-card p-8"
          >
            <span className="caps mb-3 block text-primary">{eyebrow}</span>
            <h4 className="mb-2 text-statute">{title}</h4>
            <p className="text-sm leading-[1.6] text-ink-variant">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
