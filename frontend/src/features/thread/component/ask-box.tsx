"use client";

import Link from "next/link";
import { Paperclip, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useAskForm } from "../hooks/useAskForm";
import { VerificationToggle } from "./verification-toggle";

/** The examples are prompts, not data -- they seed the box and nothing
 *  more, so they belong here rather than behind a request. */
const EXAMPLES = [
  "Find precedents for…",
  "Explain Section…",
] as const;

/** Organism: uses `useAskForm`, so it owns the submitting and error state. */
export function AskBox({ caseId }: { caseId?: string }) {
  const {
    question, error, isCreating, verification, setVerification,
    handleChange, handleSubmit,
  } = useAskForm(caseId);

  return (
    <Card className="gap-0 p-6 shadow-1 transition-colors duration-[120ms] ease-out focus-within:border-primary">
      <Textarea
        aria-label="Ask a legal question"
        placeholder="Ask a legal question…"
        rows={3}
        value={question}
        disabled={isCreating}
        onChange={(event) => handleChange(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends, Shift+Enter breaks the line -- the convention
          // every chat box shares, and the one a lawyer will assume.
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void handleSubmit();
          }
        }}
        className="resize-none border-0 bg-transparent p-0 text-base shadow-none focus-visible:ring-0 dark:bg-transparent"
      />

      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {caseId ? (
          <span className="text-sm text-ink-muted">
            This thread will be attached to the case.
          </span>
        ) : (
          <span className="text-sm text-ink-muted">Examples:</span>
        )}
        {!caseId &&
          EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => handleChange(example)}
              className="rounded-sm border border-line bg-surface-card px-2.5 py-1 text-xs font-medium text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken"
            >
              {example}
            </button>
          ))}

        {/* Uploads belong to a case, not to a thread -- that is what the
            API stores against, and it is what lets one bundle serve every
            question about the same matter. Without this the upload screen
            is real and unreachable from where a reader looks for it. */}
        {!caseId && (
          <Link
            href="/cases"
            className="inline-flex items-center gap-1.5 rounded-sm border border-line bg-surface-card px-2.5 py-1 text-xs font-medium text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken"
          >
            <Paperclip className="size-3.5" />
            Attach documents
          </Link>
        )}

        <VerificationToggle
          value={verification}
          onChange={setVerification}
          disabled={isCreating}
        />

        <Button
          className="ml-auto"
          disabled={isCreating}
          onClick={() => void handleSubmit()}
        >
          <Sparkles className="size-4" />
          {isCreating ? "Starting…" : "Ask Legal AI"}
        </Button>
      </div>
    </Card>
  );
}
