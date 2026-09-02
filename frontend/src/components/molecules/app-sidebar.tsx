"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderOpen, Home, Plus, ScrollText, Search, Share2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/molecules/wordmark";
import { cn } from "@/lib/utils";

/**
 * The persistent nav. A molecule: `usePathname` is a framework hook, not a
 * data hook, so this owns no loading or error state.
 *
 * History and Settings from the reference design are still absent:
 * History would be this same thread list under another name, and Settings
 * has nothing behind it. Every item below goes somewhere real.
 *
 * Collapsing to a 68px icon rail below 860px is CSS, not a breakpoint
 * hook: JS would render one width on the server and another after mount.
 */
const ITEMS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/cases", label: "Cases", icon: FolderOpen },
  { href: "/search", label: "Search", icon: Search },
  { href: "/graph", label: "Graph", icon: Share2 },
  { href: "/activity", label: "Activity", icon: ScrollText },
] as const;

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 flex h-screen w-[68px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-line bg-surface-card px-2 py-4 lg:w-64 lg:px-4">
      <Link
        href="/"
        className="flex h-9 items-center justify-center lg:justify-start"
      >
        <Wordmark className="hidden lg:inline" />
        <span className="font-serif text-statute font-bold text-primary-deep lg:hidden">
          प
        </span>
      </Link>

      {/* Home is the ask screen, so a new question starts there. */}
      <Button asChild className="w-full justify-center lg:justify-start">
        <Link href="/">
          <Plus className="size-4" />
          <span className="hidden lg:inline">New Research</span>
        </Link>
      </Button>

      <nav className="flex flex-col gap-0.5">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          // "/" would otherwise light up on every route.
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              className={cn(
                // A 2px left border marks the selection and the radius is
                // squared off against it -- depth here is tonal, never a
                // shadow.
                "flex items-center gap-3 rounded-r border-l-2 border-transparent px-3 py-2.5",
                "text-sm font-medium text-ink-variant transition-colors duration-[120ms] ease-out",
                "hover:bg-surface-sunken hover:text-ink",
                active &&
                  "border-l-primary bg-surface-tint font-semibold text-primary",
              )}
            >
              <Icon className="size-[18px] shrink-0" />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
