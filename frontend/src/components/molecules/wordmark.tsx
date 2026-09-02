import Image from "next/image";

/**
 * Molecule: the brand lockup, as artwork.
 *
 * The PNG rather than text or a redrawn SVG. `design/BRAND.md` is explicit
 * that an earlier attempt to trace the mark by hand produced something
 * recognisably *not* the logo, so the artwork is the source of truth.
 *
 * Rendered at 34px tall (lockup) and 32px (mark) against artwork roughly
 * 4x that height, which is what keeps it crisp on a high-density display.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <Image
      src="/brand/pramana-lockup.png"
      alt="Pramāṇa AI"
      width={475}
      height={132}
      priority
      className={`h-[34px] w-auto ${className ?? ""}`}
    />
  );
}

/** The mark alone, for the collapsed sidebar rail. */
export function Mark({ className }: { className?: string }) {
  return (
    <Image
      src="/brand/pramana-mark.png"
      alt="Pramāṇa AI"
      width={113}
      height={132}
      priority
      className={`h-8 w-auto ${className ?? ""}`}
    />
  );
}
