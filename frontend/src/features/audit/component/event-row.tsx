import { cn } from "@/lib/utils";
import type { AuditEvent } from "../types";

/** Molecule: one line of the trail.
 *
 *  A refusal is marked, not hidden. Someone reaching for a matter that is
 *  not theirs is the row a firm looks for first, so it has to read
 *  differently from an ordinary one at a glance. */
export function EventRow({ event }: { event: AuditEvent }) {
  const refused = event.status >= 400;
  const when = new Date(event.at);

  return (
    <div className="flex items-baseline gap-4 px-6 py-3">
      <span className="mono w-40 shrink-0 text-xs text-ink-muted">
        {when.toLocaleString(undefined, {
          day: "numeric", month: "short",
          hour: "2-digit", minute: "2-digit",
        })}
      </span>
      <span className="w-20 shrink-0 text-sm font-medium text-ink">
        {event.action}
      </span>
      <span className="min-w-0 flex-1 text-sm text-ink-variant">
        {event.resource_type}
        {event.resource_id && (
          <span className="mono ml-2 text-xs text-ink-muted">
            {event.resource_id}
          </span>
        )}
      </span>
      <span
        className={cn(
          "shrink-0 rounded-sm px-2 py-0.5 text-xs font-medium",
          refused ? "bg-danger-bg text-danger" : "bg-ok-bg text-ok",
        )}
      >
        {refused ? "refused" : "allowed"}
      </span>
    </div>
  );
}
