import { LandingSectionHead } from "./section-head";

/** Molecule: the sources, named plainly. No logos and no claimed
 *  partnership -- design/UX_FLOWS.md forbids both, and neither would be
 *  true. */
const SOURCES = [
  "India Code",
  "Supreme Court of India",
  "High Courts",
  "District Courts & eCourts",
  "Verified legal sources",
] as const;

export function SourceStrip() {
  return (
    <section className="border-t border-line py-[72px]">
      <LandingSectionHead
        title="Source transparency"
        lede="Answers are grounded in primary Indian legal sources, with provenance retained end to end."
      />
      <div className="flex flex-wrap justify-center gap-3">
        {SOURCES.map((source) => (
          <span
            key={source}
            className="rounded border border-line bg-surface-card px-4 py-2.5 text-sm font-medium text-ink-variant"
          >
            {source}
          </span>
        ))}
      </div>
    </section>
  );
}
