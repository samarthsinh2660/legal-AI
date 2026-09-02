/** Molecule: a centred section heading, with an optional line under it. */
export function LandingSectionHead({
  title,
  lede,
}: {
  title: string;
  lede?: string;
}) {
  return (
    <div className="mb-10 text-center">
      <h2 className="text-heading">{title}</h2>
      {lede && <p className="mt-2 text-ink-variant">{lede}</p>}
    </div>
  );
}
