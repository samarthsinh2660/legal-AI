"use client";

import { Loader2, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/molecules/empty-state";
import { PageLoader } from "@/components/molecules/loading";
import { useDrafts } from "../hooks";
import { useResearchThread } from "../hooks/useResearchThread";
import type { Verification } from "../types";
import { DraftButton } from "./draft-button";
import { DraftCard } from "./draft-card";
import { MessageBubble } from "./message-bubble";
import { ProgressSteps } from "./progress-steps";
import { ThreadCaseBanner } from "./thread-case-banner";
import { VerificationToggle } from "./verification-toggle";

/**
 * Organism: the thread itself.
 *
 * `initialQuestion` is the question typed on the home page, handed over in
 * the URL. Home creates the thread and navigates immediately rather than
 * waiting for the answer, so the user watches the work here instead of
 * watching nothing there.
 */
export function ResearchThread({
  threadId,
  initialQuestion,
  initialMode,
}: {
  threadId: string;
  initialQuestion?: string;
  /** The mode the question was asked in on the dashboard, carried through
   *  the URL so the first turn runs the way the reader chose. */
  initialMode?: Verification;
}) {
  const {
    messages,
    isLoading,
    loadError,
    awaitingAnswer,
    draft,
    setDraft,
    verification,
    setVerification,
    steps,
    streamingLede,
    isSending,
    sendError,
    send,
  } = useResearchThread(threadId);

  // Documents drafted from this conversation. Its own hook because a draft
  // outlives the turn that prompted it -- it is still there when the thread
  // is reopened tomorrow.
  const { drafts, preparing, startDraft, startError } = useDrafts(threadId);

  // Fire the handed-over question once, then take it out of the URL.
  //
  // The ref alone was not enough. It guards one mount, and `?ask=` stayed
  // in the address bar for good -- so a reload, a back-navigation or a
  // fast-refresh mounted this again and asked the same question a second
  // and third time. The thread had already answered it, so the replay came
  // back in under a second and the reader saw their one question three
  // times over. Observed on thread 6aff1ac2, 2026-09-03.
  //
  // `replace`, not `push`: the asked-with-a-question URL must not become a
  // back-button destination that re-asks on arrival.
  const router = useRouter();
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current || !initialQuestion || isLoading) return;
    asked.current = true;
    if (initialMode) setVerification(initialMode);
    router.replace(`/research/${threadId}`, { scroll: false });
    void send(initialQuestion, initialMode);
  }, [initialQuestion, initialMode, isLoading, send, setVerification, router, threadId]);

  const foot = useRef<HTMLDivElement>(null);
  useEffect(() => {
    foot.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, steps.length]);

  if (isLoading) return <PageLoader />;
  if (loadError) {
    return <EmptyState message="Could not load this thread." />;
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-4xl flex-col gap-4">
      <ThreadCaseBanner threadId={threadId} />

      <div className="flex-1 space-y-4">
        {messages.length === 0 && !isSending && (
          <EmptyState message="Ask your first question below." />
        )}
        {messages.map((message) => (
          <MessageBubble key={message.message_id} message={message} />
        ))}
        {drafts.map((drafted) => (
          <DraftCard key={drafted.draft_id} draft={drafted} />
        ))}
        {startError && <p className="text-sm text-danger">{startError}</p>}
        {isSending && <ProgressSteps steps={steps} />}
        {/* The question is stored before research runs, so a reopened
            thread can end on a question with no reply yet. The run is
            detached from the request and stores its answer either way, so
            while one is still in flight this waits for it and polls; past
            the ceiling it says the run did not finish instead. */}
        {!isSending &&
          messages.length > 0 &&
          messages[messages.length - 1].role === "user" &&
          (awaitingAnswer ? (
            <p className="flex items-center gap-2 text-sm text-ink-muted">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Still researching. This keeps running whether or not the page is
              open &mdash; the answer will appear here.
            </p>
          ) : (
            <p className="text-sm text-ink-muted">
              This didn&apos;t finish. Ask it again below.
            </p>
          ))}
        {/* The lede, revealed as it streams in. Same typography as
            AnswerView's own lede paragraph, so the swap to the finished
            message -- once the query invalidation lands it -- is not a
            visible jump. Everything else (claims, sources, badges) still
            arrives at once with the final message; only the one paragraph
            a reader reads first benefits from streaming. See
            docs/SPEED_2026_09_03.md #1. */}
        {isSending && streamingLede && (
          <article className="rounded-md border border-line bg-surface-card p-6">
            <p className="text-lg leading-[1.7] text-ink">{streamingLede}</p>
          </article>
        )}
        {sendError && <p className="text-sm text-danger">{sendError}</p>}
        <div ref={foot} />
      </div>

      {/* The composer holds the mode switch, the way every other chat box
          keeps its controls with the box rather than in a settings pane. */}
      <div className="sticky bottom-0 border-t border-line bg-surface pt-4">
        <div className="rounded-md border border-line bg-surface-card p-3 shadow-1 transition-colors duration-[120ms] ease-out focus-within:border-primary">
          <Textarea
            aria-label="Ask a follow-up"
            placeholder="Ask a follow-up…"
            rows={2}
            value={draft}
            disabled={isSending}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(draft);
              }
            }}
            className="resize-none border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          <div className="mt-3 flex items-center gap-3">
            <VerificationToggle
              value={verification}
              onChange={setVerification}
              disabled={isSending}
            />
            <DraftButton
              onSelect={() => void startDraft()}
              disabled={isSending || preparing || messages.length === 0}
            />
            <Button
              size="icon"
              className="ml-auto"
              disabled={isSending || !draft.trim()}
              onClick={() => void send(draft)}
            >
              <Send className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
