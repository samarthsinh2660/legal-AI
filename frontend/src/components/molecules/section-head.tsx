export function SectionHead({ children }: { children: React.ReactNode }) {
  /* Serif and letter-spacing come from the base layer -- every heading in
     the app gets them, so they are not repeated here. */
  return <h2 className="mb-4 text-heading">{children}</h2>;
}
