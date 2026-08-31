# Phase 8 --- Conversation

## Objective

> Can a user *talk* to it, instead of asking one question at a time?

Every question today is a cold start. `POST /research` has no memory of the
call before it, so "what about Bombay?" retrieves nothing and "is that still
good law?" re-researches from scratch.

Phase 8 makes it a conversation without making it worse at law.

------------------------------------------------------------------------

## 1. The finding that shapes this

Two results from the literature decide the design, and they point the same
way:

**Over 60% of follow-up messages contain unresolved references** --- "what
about Bombay", "does that bind me". Retrieval over that raw text returns
nothing. Every conversational-RAG paper converges on the same fix: rewrite
the follow-up into a standalone question *before* retrieving.

**Accuracy drops >30% when the relevant fact sits mid-context**
("lost in the middle", replicated across six model families). More history
is not more context --- it buries the current question.

So history goes to two places, in two different shapes:

```
history --> rewriter --> ONE standalone question --> retrieval
        --> last 2-3 turns verbatim -------------> the answer, for continuity
```

Sending a transcript to retrieval is the mistake this phase exists to avoid.

------------------------------------------------------------------------

## 2. What we already have

Most chat wrappers bolt these on later. We have them:

| Usually added | Here |
|---|---|
| Mem0 / Zep fact extraction | `case_findings` --- claims with evidence ids |
| A separate vector memory store | pgvector, same database |
| Session containers | `case_sessions` |
| Per-thread state | `ThreadContext`, built once, passed read-only |

`DraftAnswer` is structured, not prose: claims with evidence ids and four
verification slots. A follow-up can reference an established claim by id
rather than re-reading a paragraph.

**We are not adding Mem0 or Zep.** That would be a worse `case_findings`.

------------------------------------------------------------------------

## 3. Milestones

### M16 --- Message storage

`conversations` and `messages`, in the same Postgres.

`conversations.user_id` is **NOT NULL** and every query is scoped to it.
This is also the first table in the system with an owner, which closes for
chat the multi-tenancy hole still open on `cases`.

The assistant's structured answer is stored alongside its text, so a later
turn can cite what was established rather than re-derive it.

### M17 --- The rewriter

One cheap model call: recent turns plus the new message, out comes a
standalone question.

It must **fail open** --- on any error, fall back to the user's message
verbatim. A rewriter that breaks must degrade to today's behaviour, not to
no answer.

### M18 --- Retrieval skipping

"Which of those binds me?" is a question about the answer just given, not a
new research question. Running the fan-out for it costs 30 seconds and model
budget to re-find what is already on screen.

The classifier decides between answering from the conversation and running
research. **Unsure means research** --- answering from memory when the user
wanted fresh law is the worse error.

### M19 --- Context budget

```
system + ThreadContext        always
case_findings                 always (durable, already extracted)
last 2-3 turns                verbatim
older turns                   rolling summary
current question              last, never buried
```

### M20 --- `POST /chat`

The endpoint. Same envelope, same auth, same per-user AI budget as
`/research`.

Not streaming. SSE is the right eventual answer, but our latency is 30-60s
of fan-out rather than token-by-token generation, so the useful unit is a
progress event, not a token. Deferred until something needs it.

### M21 --- Multi-turn benchmark

`evals/datasets/conversation.json`: frozen multi-turn threads where the
follow-up is meaningless alone. Measures whether the rewriter resolves the
reference, and whether the right documents come back.

Without it, the rewriter is unmeasured and this phase repeats Phase 7's gap.

------------------------------------------------------------------------

## 4. Risks

**Stored prompt injection.** Chat history is user-controlled text replayed
into every later prompt in that thread. One poisoned message can steer every
future turn. Stored messages get the same treatment as retrieved documents:
data, never instructions.

**Verification must not weaken.** A conversational answer is still an answer.
The four claim slots, the citations and the disclaimer survive; a chat reply
that drops them is a regression, not a feature.

------------------------------------------------------------------------

## 5. Deliverable

> A thread a user can hold, where the follow-up resolves, the corpus is
> searched only when it is needed, and every claim is still checked.
