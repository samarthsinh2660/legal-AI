"use client";

import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAskForm } from "../hooks/useAskForm";
import { VerificationToggle } from "./verification-toggle";

/** Prompts, not data -- they seed the box and nothing more. */
const EXAMPLES = [
  "Can a homebuyer claim a refund for late possession?",
  "What does Section 138 of the NI Act require?",
  "When is anticipatory bail granted?",
] as const;

/**
 * Organism: the empty chat. Uses `useAskForm`, so it owns the submitting
 * and error states.
 *
 * The composer sits at the bottom, where a chat's composer is, and the
 * thread is created only when the first question is sent.
 */
export function NewResearch() {
  const {
    question, error, isCreating, verification, setVerification,
    handleChange, handleSubmit,
  } = useAskForm();

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-10 text-center">
        <h1 className="text-title">What would you like to research?</h1>
        <p className="max-w-lg text-ink-variant">
          Ask in your own words. The answer will carry the statutes and
          judgments it rests on, and say what it could not check.
        </p>

        <div className="flex flex-wrap justify-center gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => handleChange(example)}
              className="rounded-sm border border-line bg-surface-card px-3 py-1.5 text-sm text-ink-variant transition-colors duration-[120ms] ease-out hover:border-line-strong hover:bg-surface-sunken"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      <div className="sticky bottom-0 bg-surface pb-6 pt-4">
        <div className="rounded-md border border-line bg-surface-card p-3 shadow-1 transition-colors duration-[120ms] ease-out focus-within:border-primary">
          <Textarea
            autoFocus
            aria-label="Ask a legal question"
            placeholder="Ask a legal question…"
            rows={3}
            value={question}
            disabled={isCreating}
            onChange={(event) => handleChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
            className="resize-none border-0 bg-transparent p-0 text-base shadow-none focus-visible:ring-0 dark:bg-transparent"
          />

          {error && <p className="mt-2 text-sm text-danger">{error}</p>}

          <div className="mt-3 flex items-center gap-3">
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
        </div>
      </div>
    </div>
  );
}
