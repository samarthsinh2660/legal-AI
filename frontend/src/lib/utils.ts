import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * A timestamp as a lawyer would say it: "Today, 2:30 PM", "Yesterday",
 * then the date. Rendered client-side only -- "today" depends on the
 * reader's clock, and computing it on the server would hydrate wrong for
 * anyone in another timezone.
 */
export function relativeDate(iso: string): string {
  const at = new Date(iso);
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  const dayMs = 86_400_000;

  if (at.getTime() >= midnight.getTime()) {
    return `Today, ${at.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    })}`;
  }
  if (at.getTime() >= midnight.getTime() - dayMs) return "Yesterday";
  return at.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
