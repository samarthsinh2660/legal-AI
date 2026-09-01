import { Zap, ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import { Verification } from "../types";

/** Molecule: the two checking modes, in the composer where the question
 *  is asked rather than buried in settings — it is a per-question choice,
 *  and its cost (about a minute) is paid on this turn. */
const MODES = [
  {
    value: Verification.Verified,
    label: "Verified",
    icon: ShieldCheck,
    title: "Check every claim against its source. Slower.",
  },
  {
    value: Verification.Quick,
    label: "Quick",
    icon: Zap,
    title: "Check citations exist, but not whether they support the claim.",
  },
] as const;

export function VerificationToggle({
  value,
  onChange,
  disabled,
}: {
  value: Verification;
  onChange: (value: Verification) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-1 rounded border border-line bg-surface-card p-0.5">
      {MODES.map((mode) => {
        const Icon = mode.icon;
        return (
          <button
            key={mode.value}
            type="button"
            title={mode.title}
            disabled={disabled}
            onClick={() => onChange(mode.value)}
            className={cn(
              "flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors duration-[120ms] ease-out disabled:opacity-50",
              value === mode.value
                ? "bg-surface-tint text-primary"
                : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
            )}
          >
            <Icon className="size-3.5" />
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}
