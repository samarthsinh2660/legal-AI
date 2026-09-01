import { Provenance } from "@/types/common";

/**
 * The product's core idiom: always make clear what came from the curated
 * foundation and what came from the reader's own file.
 *
 * Each badge pairs its colour with a dot and a word, so the meaning
 * survives greyscale printing and colour-blindness -- colour alone is
 * never the carrier.
 */
const LOOK = {
  [Provenance.Static]: {
    label: "Static knowledge",
    className: "bg-prov-static-bg text-prov-static",
    dot: "bg-prov-static",
  },
  [Provenance.Dynamic]: {
    label: "Dynamic research",
    className: "bg-prov-dynamic-bg text-prov-dynamic",
    dot: "bg-prov-dynamic",
  },
  [Provenance.Document]: {
    label: "Your document",
    className: "bg-prov-document-bg text-prov-document",
    dot: "bg-prov-document",
  },
} as const;

export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  const look = LOOK[provenance];
  return (
    <span
      className={`caps inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 ${look.className}`}
    >
      <span className={`size-1.5 rounded-full ${look.dot}`} />
      {look.label}
    </span>
  );
}
