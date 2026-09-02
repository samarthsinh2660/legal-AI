import Link from "next/link";
import { FolderOpen, PenLine, Search, Share2 } from "lucide-react";

/** Molecule: four links, every one to a screen that exists and to an API
 *  that answers. The reference design's "Analyze Document" is not here --
 *  a document can only be uploaded to a case that already exists, so it
 *  belongs on the case, not on a cold start. */
const ACTIONS = [
  { href: "/research/new", label: "New Research", icon: PenLine },
  { href: "/cases", label: "Cases", icon: FolderOpen },
  { href: "/search", label: "Search corpus", icon: Search },
  { href: "/graph", label: "Citation graph", icon: Share2 },
] as const;

export function QuickActions() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {ACTIONS.map(({ href, label, icon: Icon }) => (
        <Link
          key={label}
          href={href}
          className="flex flex-col items-center gap-2 rounded-md border border-line bg-surface-card p-5 text-center transition-colors duration-[120ms] ease-out hover:border-primary hover:bg-surface-tint"
        >
          <Icon className="size-5 text-primary" />
          <span className="text-sm font-medium text-ink-variant">{label}</span>
        </Link>
      ))}
    </div>
  );
}
