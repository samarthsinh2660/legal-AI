/** Molecule. Colour alone is never the carrier: each swatch pairs with a
 *  word, so the meaning survives greyscale and colour-blindness. */
const KEYS = [
  { label: "Judgment", className: "bg-primary" },
  { label: "Statute", className: "bg-prov-static" },
  { label: "Court", className: "bg-ink-muted" },
] as const;

export function GraphLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4">
      {KEYS.map(({ label, className }) => (
        <span key={label} className="flex items-center gap-2 text-xs text-ink-muted">
          <span className={`size-2.5 rounded-full ${className}`} />
          {label}
        </span>
      ))}
    </div>
  );
}
