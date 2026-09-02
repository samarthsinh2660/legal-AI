/** Molecule: the mark, in the serif that carries the product's authority. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={`font-serif text-statute font-bold text-primary-deep ${className ?? ""}`}
    >
      Pramāṇa AI
    </span>
  );
}
