import { AlertTriangle, CircleHelp, Info } from "lucide-react";

/**
 * Molecule: one of the three claim buckets that is *not* a clean pass.
 *
 * Each gets its own word, its own icon and its own semantic colour,
 * because they are three different facts:
 *
 *   partially   the source is narrower than the claim   (warn)
 *   against     the evidence contradicts the claim      (danger)
 *   unchecked   nobody looked                           (neutral)
 *
 * "Unchecked" is deliberately neutral, not red. A claim nobody examined
 * is not a claim that failed, and colouring it like one would tell a
 * lawyer something we never established.
 */
const LOOK = {
  partially: {
    title: "Supported in part",
    note: "The source is narrower than the claim, or drops a condition it carries.",
    icon: Info,
    box: "border-warn/30 bg-warn-bg",
    ink: "text-warn",
  },
  against: {
    title: "Evidence against this",
    note: "What we retrieved does not support the claim.",
    icon: AlertTriangle,
    box: "border-danger/30 bg-danger-bg",
    ink: "text-danger",
  },
  unchecked: {
    title: "Not checked",
    note: "We could not verify these — not that they are wrong, but that nobody looked.",
    icon: CircleHelp,
    box: "border-line bg-surface-sunken",
    ink: "text-ink-muted",
  },
} as const;

export function EvidenceBlock({
  variant,
  claims,
}: {
  variant: keyof typeof LOOK;
  claims: string[];
}) {
  if (claims.length === 0) return null;
  const look = LOOK[variant];
  const Icon = look.icon;

  return (
    <section className={`rounded-md border p-4 ${look.box}`}>
      <div className={`flex items-center gap-2 ${look.ink}`}>
        <Icon className="size-4 shrink-0" />
        <span className="caps">{look.title}</span>
      </div>
      <p className="mt-1.5 text-xs text-ink-muted">{look.note}</p>
      <ul className="mt-3 space-y-2">
        {claims.map((claim, index) => (
          <li key={index} className="text-sm leading-[1.7] text-ink-variant">
            {claim}
          </li>
        ))}
      </ul>
    </section>
  );
}
