import { cn } from "@/lib/utils";
import { AnswerSchema, type Message } from "../types";
import { AnswerView } from "./answer-view";

/**
 * Molecule: one message.
 *
 * An assistant turn carries its structured answer as well as its prose.
 * Where it parses, the structure is what gets rendered -- the flat text
 * shows a verified claim and an unchecked one identically, which is the
 * one thing this product exists not to do. Where it does not parse (an
 * older row, a clarification, a routed reply), the prose is the honest
 * fallback rather than an error.
 */
export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const parsed = message.answer
    ? AnswerSchema.safeParse(message.answer)
    : null;

  if (!isUser && parsed?.success) {
    return (
      <article className="rounded-md border border-line bg-surface-card p-6">
        <AnswerView answer={parsed.data} />
      </article>
    );
  }

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[46rem] rounded-md px-4 py-3 text-sm whitespace-pre-wrap",
          isUser
            ? "bg-surface-tint text-ink"
            : "border border-line bg-surface-card leading-[1.7] text-ink-variant",
        )}
      >
        {message.content}
      </div>
    </div>
  );
}
