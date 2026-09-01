import { ShieldCheck } from "lucide-react";

import { ProvenanceBadge } from "@/components/molecules/provenance-badge";
import { provenanceOf } from "../evidence";
import type { Answer } from "../types";
import { CitationRef } from "./citation-ref";
import { EvidenceBlock } from "./evidence-block";

/** The distinct provenances actually present, so the answer is marked
 *  once at the top rather than on every line. */
function provenances(answer: Answer) {
  const seen = new Set<string>();
  const found = [];
  for (const id of [
    ...answer.citations,
    ...answer.key_elements.flatMap((claim) => claim.evidence_ids),
  ]) {
    const provenance = provenanceOf(id);
    if (provenance && !seen.has(provenance)) {
      seen.add(provenance);
      found.push(provenance);
    }
  }
  return found;
}

/**
 * Molecule: one structured answer, from a prop.
 *
 * The order is the reader's: the direct answer, then what holds it up,
 * then everything that is *less* than settled — and those never share a
 * heading, a colour or a word with the parts that are.
 */
export function AnswerView({ answer }: { answer: Answer }) {
  const marks = provenances(answer);

  return (
    <div className="space-y-5">
      {marks.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {marks.map((provenance) => (
            <ProvenanceBadge key={provenance} provenance={provenance} />
          ))}
        </div>
      )}

      {/* Above the answer: it changes how everything below should be read. */}
      {answer.coverage_note && (
        <p className="rounded-md border border-warn/30 bg-warn-bg px-4 py-3 text-sm leading-[1.7] text-warn">
          {answer.coverage_note}
        </p>
      )}

      {answer.lede && (
        <p className="text-lg leading-[1.7] text-ink">{answer.lede}</p>
      )}

      {answer.key_elements.length > 0 && (
        <section>
          <div className="flex items-center gap-2 text-ok">
            <ShieldCheck className="size-4 shrink-0" />
            <span className="caps text-ink-muted">Checked against the source</span>
          </div>
          <ul className="mt-3 space-y-3">
            {answer.key_elements.map((claim, index) => (
              <li key={index} className="text-sm leading-[1.7] text-ink-variant">
                {claim.text}
                {claim.evidence_ids.length > 0 && (
                  <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
                    {claim.evidence_ids.map((id) => (
                      <CitationRef key={id} id={id} />
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Three separate blocks, never merged. See evidence-block.tsx. */}
      <EvidenceBlock
        variant="partially"
        claims={answer.partially_supported}
      />
      <EvidenceBlock variant="against" claims={answer.needs_verification} />
      <EvidenceBlock variant="unchecked" claims={answer.unchecked} />

      {/* Said once, at the answer level: the citations were checked, only
          their support was not. */}
      {answer.support_not_checked && (
        <p className="rounded-md border border-line bg-surface-sunken px-4 py-3 text-xs text-ink-muted">
          Quick mode: every citation was checked to exist, but whether each
          source actually supports the claim was not verified.
        </p>
      )}

      {(answer.applicable_law.length > 0 || answer.key_judgments.length > 0) && (
        <section className="border-t border-line pt-4">
          <span className="caps text-ink-muted">Sources</span>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[...answer.applicable_law, ...answer.key_judgments].map((id) => (
              <CitationRef key={id} id={id} />
            ))}
          </div>
        </section>
      )}

      {answer.disclaimer && (
        <p className="text-xs leading-relaxed text-ink-muted">
          {answer.disclaimer}
        </p>
      )}
    </div>
  );
}
