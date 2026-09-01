import { relativeDate } from "@/lib/utils";
import type { Case } from "../types";

/** Molecule: one matter, from a prop. */
export function CaseTile({ item }: { item: Case }) {
  return (
    <article className="flex flex-col gap-3 rounded-md border border-line bg-surface-card p-6 transition-colors duration-[120ms] ease-out hover:border-line-strong">
      <div>
        {item.matter_type && <span className="caps text-ink-muted">{item.matter_type}</span>}
        <h3 className="mt-1 text-statute leading-snug">{item.title}</h3>
      </div>

      {item.description && (
        <p className="line-clamp-2 text-sm leading-[1.7] text-ink-variant">
          {item.description}
        </p>
      )}

      <div className="mono mt-auto flex flex-wrap items-center gap-2 text-xs text-ink-muted">
        {item.court && (
          <span className="rounded-sm bg-surface-muted px-2.5 py-1 font-medium text-ink-variant">
            {item.court}
          </span>
        )}
        <span>{relativeDate(item.updated_at)}</span>
      </div>
    </article>
  );
}
