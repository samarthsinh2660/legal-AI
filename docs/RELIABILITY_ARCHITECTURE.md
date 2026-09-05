# Reliability architecture — the end state

**Status:** design. What ships today is the detached run and its polling;
the tables, the workers and the connection manager are not built.

The problem this settles: a research turn takes 30–130 seconds and costs
real model budget, and today almost anything that interrupts it loses the
work. This document describes the shape we build *once*, so each later
piece is additive rather than a rewrite.

---

## The one idea

**A run is a row, not a variable.**

Today a run is an `asyncio.Task` in one process's memory. Nothing outside
that process knows it exists, so nothing can watch it, resume it, stop it,
or notice it died. Every failure below is a symptom of that single fact.

Make the run a durable row and the rest follows: a watcher reads the row, a
worker claims the row, a reaper finds rows that stopped breathing, and the
row's own uniqueness rules enforce what would otherwise be application
races.

---

## What the design has to survive

Measured or reproduced on this system, not hypothetical:

| Event | Today |
|---|---|
| Browser closes mid-run | answer saved ✓ *(shipped — detached runs)* |
| Refresh / new tab mid-run | says "Still researching", answer arrives ✓ *(shipped)* |
| Waiting in another tab | polling continues in background ✓ *(shipped)* |
| Live progress after refresh | lost — a spinner, not the steps |
| Second tab, same thread | can start a parallel run; findings interleave |
| Server restart / deploy | run dies silently, question left unanswered |
| Worker hangs (not crashes) | indistinguishable from slow, forever |
| Reader leaves | full model budget still spent |
| Retry after crash | would duplicate the answer *and* the case findings |
| 100 requests at once | 100 tasks against 16 executor threads, no backpressure |
| 100 readers waiting | 33 polls/second at 3s each, growing with every reader |

---

## The architecture

```
                    ┌──────────────────────────────────┐
  Browser  ◄────────┤     CONNECTION MANAGER (API)     │
   SSE / WS         │                                  │
                    │  owns every client subscription  │
                    │  LISTENs for run changes         │
                    │  reconciles on the SSE heartbeat │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │            POSTGRES              │
                    │                                  │
                    │   runs        kind: research     │
                    │                   | draft        │
                    │   run_events  seq'd progress     │
                    │   messages    the answer         │
                    │   drafts      the rendered .docx │
                    │                                  │
                    │   NOTIFY run_changed ────────────┼──►  the manager
                    └───┬──────────────────────────┬───┘
                        │  claim WHERE kind = ...  │
                        │  FOR UPDATE SKIP LOCKED  │
          ┌──────────────────────────────────────────────────┐
          │                     WORKER                       │
          │           (one binary, any machine)              │
          │                                                  │
          │   claims a run, dispatches on kind:              │
          │                                                  │
          │     research → the graph                         │
          │     draft    → agents.drafter                │
          │                                                  │
          │   appends events · checkpoints · heartbeats      │
          │   result + done ─── one txn ───                  │
          └────────────────────────┬─────────────────────────┘
                                   │
                     ┌───────────▼───────────┐
                     │  REAPER — periodic    │
                     │  stale heartbeat →    │
                     │  requeue or fail      │
                     └───────────────────────┘
```

**Postgres is the queue.** Not Redis, and this is deliberate. A run lasts
30–130 seconds, so throughput is single-digit jobs per minute — nowhere
near a dedicated broker's purpose. Postgres is already here, already
backed up, and `SELECT … FOR UPDATE SKIP LOCKED` is a correct queue. Most
importantly it makes each worker's last step atomic: **the result and the
run's completion are written in one transaction**, which is what makes
exactly-once free rather than a distributed-systems problem.

It is also what makes a worker on a *different machine* free: it needs a
connection string and nothing else. No broker, no service discovery, no
shared filesystem.

Add Redis only if a measurement ever demands it. Nothing in the design
changes if we do — the worker's claim call is the only thing that moves.

---

## Realtime: SSE, reconciled on the heartbeat

SSE for live progress, `run_events` for durable state and replay. No client
polling: a browser that asks "anything new?" every three seconds is 0.33
requests/second per reader, each a JWT verification, a pool checkout and a
query, and a hundred waiting readers is ~33/second of "not yet" that also
spends their own rate-limit budget. One connection costs one request and
then nothing.

```
  worker  ── UPDATE runs … ; INSERT run_events ; NOTIFY run_changed ──► PG
                                                                        │
  ┌─────────────────────────────────────────────────────────────────────┴──┐
  │  CONNECTION MANAGER                                                    │
  │                                                                        │
  │   LISTEN run_changed        ← push, ~instant                           │
  │   heartbeat every 25s       ← required anyway; carries reconciliation  │
  └──────────────────────────────┬─────────────────────────────────────────┘
                                 │  SSE
                                 ▼
                              Browser
                     reconnects itself · Last-Event-ID
                     replays from run_events
```

### Why a heartbeat, and why it does the reconciling

Two facts settle this, and neither is a matter of taste.

**`NOTIFY` is not durable.** Notifications reach only sessions listening at
that moment; nothing is stored for a listener that is disconnected or
restarting, and there is no replay. The documented pattern is to let
`NOTIFY` wake the application and then read the truth from the table. So a
notification dropped while the manager reconnects is gone, and without
something to reconcile against, a reader waits on a healthy connection for
an event that is never coming.

**An SSE stream needs a heartbeat regardless.** AWS ALB, GCLB and nginx all
idle out a quiet connection at about 60 seconds, so a stream with long gaps
between events -- which a 30-130 second research turn is -- must emit
`: ping` on a shorter interval or the proxy closes it. Practice puts that
around 30 seconds.

The heartbeat is therefore not an addition. It is required by the
transport, and a heartbeat that also reads `runs` for the streams it is
serving costs one indexed query and closes the dropped-notification hole.
The manager reads once for every run it is watching, not once per viewer,
so the cost is flat in the number of readers.

That is the whole reconciliation: push for latency, heartbeat for truth,
`run_events` for replay. There is no polling in it.

### The one client-side fallback

Not for reconnects -- SSE reconnects itself and `Last-Event-ID` replays
what was missed against `run_events`.

For the case the transport cannot self-heal: **a stream that is open and
delivering nothing**, because a proxy is buffering it rather than passing
it through. The browser sees a healthy connection, so it never reconnects,
and nothing the server does reaches it. Not hypothetical -- the stream
route already sets `X-Accel-Buffering: no` because a proxy did this.

So: if the stream does not reach `open`, or delivers nothing while the run
is still `running` past a threshold, that one thread falls back and says
so. A detected degradation on one reader, not a default for all of them.

Sources: [PostgreSQL LISTEN](https://www.postgresql.org/docs/current/sql-listen.html) ·
[LISTEN/NOTIFY is best-effort signalling](https://nerdleveltech.com/postgres-listen-notify-job-queue) ·
[SSE heartbeats and proxy idle timeouts](https://tigerabrodi.blog/server-sent-events-a-practical-guide-for-the-real-world)

### What triggers a job

A job starts because a request arrived, not because anything polls for
work. The API's only role is to write the row and return:

```
  POST /threads/{id}/messages          POST /threads/{id}/drafts
            │                                    │
            └────────────┬───────────────────────┘
                         ▼
         INSERT runs(kind, status='queued')  ; NOTIFY run_queued
                         │                              │
                         │                    idle workers wake
                         ▼                              ▼
              request returns a run_id      claim FOR UPDATE SKIP LOCKED
```

`NOTIFY run_queued` is what makes a worker start in milliseconds rather
than on its next poll of the table. It is an optimisation, not a
mechanism: a worker that missed the notification picks the row up on its
next sweep, so a dropped notification costs latency and never a job. The
same reasoning as the reader's side, one layer down.

---

## A worker on another machine

The queue is a table, so a worker joins by connecting to it:

```
  DATABASE_URL        the queue, the corpus and the results
  GEMINI_API_KEY      the model
  NEO4J_URI           authority ranking, research runs only
```

No broker, no service discovery, no shared filesystem, **no inbound port** —
a worker is never called, it claims. So it can sit behind NAT on a machine
nothing can reach. The one prerequisite: Postgres listens on the compose
network today, so a remote worker needs a published port or a private
network.

**One worker binary, not one per kind.** Drafting is a model call and a
file write — the same shape as any other agent in the pipeline, and not
worth its own process, its own deployment or its own on-call. The worker
claims a run and dispatches on `kind`:

```python
if run.kind == "research":
    run_graph(inputs)                 # legal_ai/graph
else:
    drafter.draft(matter, conversation, law, authorities)
```

`kind` stays on the row because it costs one column and it is what lets a
box claim only what it can serve — the day one machine has the models and
another does not, that is a launch flag, not a rewrite:

```sql
SELECT … FROM runs WHERE status = 'queued' AND kind = ANY(%s)
ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
```

Splitting the binary is a decision to defer until a measurement asks for
it. What makes it cheap to defer is that the split is a WHERE clause.

---

## The models are a service, not a library

Every worker that runs retrieval loads the embedder and the cross-encoder
itself — **1.2 GB measured**, per process. Two workers is two copies of
identical weights, which is what caps the box at two.

The fix is to load them once, behind HTTP:

```
                 ┌──────────────────────┐
                 │   INFERENCE SERVER   │   models loaded ONCE
                 │  mpnet + reranker    │   ~1.4 GB, GPU if present
                 └──────────┬───────────┘
                            │  HTTP
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
      worker 1          worker 2          worker 3     ~250 MB each
```

The arithmetic, from the measured numbers:

| Workers | Now (1.2 GB each) | With a model server |
|---|---|---|
| 1 | 1.2 GB | 1.65 GB |
| 2 | 2.4 GB | 1.9 GB |
| 3 | 3.6 GB | 2.15 GB |
| 8 | 9.6 GB | 3.65 GB |

**Break-even is two workers.** At one it costs memory and buys nothing, so
this is worth doing when a second worker is, and not before.

### TGI or TEI

The distinction matters for what to deploy. **TGI** — Text *Generation*
Inference — serves LLMs. We run no local LLM: generation goes to Gemini
over HTTP already, so TGI has nothing to do here.

What we run locally is an embedder and a cross-encoder, which is **TEI** —
Text *Embeddings* Inference. That is the container to reach for.

**One rule that cannot be broken:** the embedder stays
`all-mpnet-base-v2`. Every vector in the corpus was produced by it, so a
different model means re-embedding 36,887 sections and 13,130 judgments
before search works at all.

### On the GTX 1050

Both models fit — mpnet is ~420 MB of weights, the reranker ~130 MB, well
inside 2–4 GB of VRAM. Two things to check before committing to it:

**TEI's GPU images target compute capability 7.5 and above** (Turing and
newer). A 1050 is Pascal, 6.1. So the stock TEI GPU image likely will not
run on that card; a thin service wrapping `sentence-transformers` with
`.to("cuda")` will, because PyTorch supports Pascal. Worth testing the TEI
image first, and falling back to the wrapper rather than buying a card.

**And what the GPU actually buys, against the measured turn:**

```
plan_research   64.8s   ← model API, ~40s of it free-tier backoff
analyst         24.6s   ← model API
rerank          14.8s   ← CPU: this is the part a GPU helps
vector           9.9s   ← embedding + query
```

A GPU addresses the 14.8 s. Even at 4× it saves ~11 s of a ~119 s turn.
The 40 s of rate-limit backoff is a bigger win and costs nothing but a paid
key. Do the GPU because it unblocks running several workers on one box —
not because it makes a turn feel faster.

---

## The schema

```sql
runs (
  run_id           uuid primary key,
  thread_id        text not null,
  user_id          text not null,
  kind             text not null default 'research',  -- research | draft
  idempotency_key  text,               -- client-supplied, stops double-submit

  status           text not null,      -- queued|running|done|failed|cancelled
  attempts         int  not null default 0,
  current_step     text,               -- 'research', 'drafting', ...

  checkpoint       jsonb,              -- LangGraph state, for mid-graph resume
  heartbeat_at     timestamptz,
  created_at, started_at, finished_at timestamptz,
  error            text
)

run_events (
  run_id     uuid,
  seq        int,                      -- monotonic per run; the SSE event id
  kind       text,                     -- step | done | error
  payload    jsonb,
  created_at timestamptz,
  primary key (run_id, seq)
)

drafts (
  draft_id       uuid primary key,
  run_id         uuid unique,          -- one draft per run: this IS the idempotency
  thread_id      text not null,
  document_type  text not null,        -- what the model named it; empty until it decides
  structure      jsonb not null,       -- what the model returned; the file renders it
  filename       text not null,        -- what the download is called
  docx           bytea,
  created_at     timestamptz
)
```

`kind` is the whole of the drafting feature's queue support. A worker
claims only the kinds it handles, so a second kind of work is a second
value in one column rather than a second system.

Two indexes carry most of the guarantees:

```sql
-- One live run per thread, per kind. A draft may be prepared while a
-- question is still researching; two drafts of one thread at once is a
-- race worth refusing.
create unique index one_live_run_per_thread on runs (thread_id, kind)
  where status in ('queued', 'running');

-- A resubmitted request attaches to the existing run instead of
-- starting a second one.
create unique index run_idempotency on runs (thread_id, idempotency_key)
  where idempotency_key is not null;
```

**What is not persisted:** the lede's word-by-word chunks. They are
animation, and on reconnect the answer is already whole. Persisting ~7
step events per run keeps the table trivial.

---

## How each failure is handled

### Normal ask

```
Browser          API                 Postgres            Worker
   │  POST ───────►│                    │                   │
   │               │ INSERT run(queued) │                   │
   │               │ INSERT user msg    │                   │
   │  ◄── run_id ──│                    │                   │
   │  SSE open ────►│                   │◄── claim ─────────│
   │               │                    │   step 1 ─────────│
   │  ◄─ step 1 ───│◄── tail ───────────│                   │
   │  ◄─ step 2 ───│◄───────────────────│   step 2 ─────────│
   │               │                    │◄─ answer + done ──│  (one txn)
   │  ◄─ done ─────│◄───────────────────│                   │
```

### Refresh, new tab, second device

```
Browser reopens
   │
   ├─ GET /threads/abc  →  messages[] + run{run_id, status, current_step}
   │
   └─ if running:  GET /runs/{run_id}/stream   Last-Event-ID: 3
                        │
                        ├─ SELECT * FROM run_events WHERE seq > 3   → replay
                        └─ then tail → live
```

Any number of watchers, on any worker, at any time. They all read the same
table, so nothing is special about the tab that started the run.

### Server restart mid-run

The worker dies. Its row still says `running`, with a `heartbeat_at` that
stops advancing. The reaper sees a stale heartbeat and either requeues the
run (attempts < max) or fails it with a reason. With `checkpoint` set, the
requeued run resumes at the node it reached rather than re-paying for
planning and retrieval.

### Reader leaves, or presses cancel

Set `status = 'cancelled'`. The worker checks between nodes and stops. That
is why cancellation lands here and could never land in the current design:
Python cannot interrupt the blocking call, but it *can* decline to start
the next node.

### Retry after a crash

The answer write is `INSERT … WHERE NOT EXISTS (answer for this run_id)`,
in the same transaction that marks the run done. A retry that gets as far
as writing twice writes once. This matters most for `_remember()` —
duplicated case findings are wrong data, not a cosmetic bug.

### Overload

Work waits in the `runs` table, not in RAM. Queue depth is a `SELECT
count(*)`, which is also what lets the UI say "3rd in line, about 4
minutes" instead of showing a spinner indistinguishable from a hang.

---

## The drafting job

A button beside the composer. It turns the conversation that just happened
into a document the reader downloads. **Shipped**, on the detached run
rather than on the queue; moving it onto `kind='draft'` is a change of
where it executes, not of what it does.

```
  [ 📄 Legal document ]  in the composer
            │
            │  POST /threads/{id}/drafts       ← nothing is chosen
            ▼
     run starts, returns at once
            │
  ┌─────────────────────────────────────────────────────────────┐
  │  1. read the whole thread: every question, every answer,    │
  │     and the claims that survived verification with their    │
  │     evidence ids                                            │
  │                                                             │
  │  2. one model call returns STRUCTURE — the model chooses    │
  │     what document this conversation calls for and lays it   │
  │     out in sections                                         │
  │                                                             │
  │  3. deterministic checks, then python-docx renders it       │
  └─────────────────────────────────────────────────────────────┘
            │
            ▼
     INSERT drafts(docx) + mark the run done     ← one txn
            │
            ▼
     the download card appears in the thread
```

### No document types

There was a registry of them — a s.138 demand notice with its own prompt,
its own Word template and a rule deciding which conversations it fitted.
It answered *"no document fits this thread"* to almost every question
anyone asked, because Indian practice has hundreds of documents and the
registry had one.

So the model chooses. It reads what was asked and what was settled, names
the document in `title`, and returns sections — headings with numbered
paragraphs under them, which is what every legal document is. Measured on
two threads with the same prompt: an abstract question of law produced
`OPINION ON THE ESSENTIAL INGREDIENTS OF CRIMINAL CONSPIRACY` under
QUESTION / OPINION / CONCLUSION, and a client's cheque matter produced
`LEGAL NOTICE UNDER SECTION 138…` under FACTS / THE POSITION IN LAW /
DEMAND.

The Word templates went with the registry. They were binaries git never
tracked, so the first deploy shipped the whole feature and had nothing to
render with — and a template per instrument is a promise to write one for
every document anyone asks for. One renderer draws all of them, because
the headings come from the draft.

### Where each part comes from

| Part | Source | How |
|---|---|---|
| **Which document** | what the conversation asked for | model |
| **Facts** | the matter and the thread | stored data |
| **Law** | provisions the thread's own answers rested on | retrieval |
| **Citations** | resolved from corpus metadata | deterministic |
| **Prose** | the sentences between them | model |

**A draft may cite only what the conversation established.** The
authorities are the union of the `evidence_ids` on claims already stored in
that thread, so a citation the conversation never relied on cannot reach
the document, and `drafting.validate` refuses one that tries. A thread that
settled no law is refused before the model is called.

**Why the split is not optional.** Drafting inverts the honesty stance the
rest of the system is built on. A research answer says what the law
provides and admits what it could not check. A draft is a document someone
may sign and send, so an invented section number is a
professional-liability event rather than a bad answer.

### What the research settled (2026-09-05)

Six searches into Indian drafting practice. Two findings changed the design
rather than merely informing the prompt:

**1. A sum must match its instrument exactly.** *Kaveri Plastics v Mahdoom
Bawa* (SC, 2025): the amount demanded must equal the cheque's face value,
and a ₹1 discrepancy invalidates the notice and the prosecution with it. So
figures are quoted exactly as the conversation gave them or not written at
all, and where a sum must match an instrument the draft raises a
`needs_input` item to check it against the instrument itself — the
conversation is not the instrument.

**2. The document is the advocate's, not ours.** Practice requires their
own letterhead with a Bar Council enrolment number, their signature and
seal, and service by registered post AD. We hold none of that. So we
produce a draft an advocate finishes, our name sits in a footer rather than
a letterhead, and everything unresolved is collected on a final page headed
DRAFTING NOTES — DELETE BEFORE SENDING.

### .docx, not PDF

A PDF is a finished document; this is a draft. The advocate puts it on
their letterhead, adds their enrolment number, settles the facts and signs.
Word is the format of the drafting stage precisely because it can be
edited — handing a lawyer a PDF hands them something to retype.

Built directly with `python-docx`. `docxtpl` and a template file were tried
and removed the same day: the template was a frozen output of code we
already had, and the binary it left in git was the thing that broke the
first deploy.

### What the reader sees

```
  ┌──────────────────────────────────────────────────────┐
  │  Ask a follow-up…                                    │
  │  [Verified] [Quick]     [📄 Legal document]      [→] │
  └──────────────────────────────────────────────────────┘
                          │ click
                          ▼
  ⟳  Preparing your document. This keeps running whether
     or not the page is open.

                          │ done
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │  📄  legal_opinion.docx                              │
  │      DOCX · draft — review and put on your           │
  │      letterhead before sending                       │
  │  ──────────────────────────────────────────────────  │
  │  Resolve before sending                              │
  │  • the s.142 limitation period may already be at risk│
  │  You still need to supply                            │
  │  • Advocate's name, enrolment number and letterhead  │
  └──────────────────────────────────────────────────────┘
```

Drafts and messages are merged by `created_at` into one list, so a document
drafted mid-thread sits where it was asked for rather than below every
later answer.

### Where it lives

The drafter is an agent, so it sits with the others and its parts sit with
their own kind:

    legal_ai/agents/drafter.py          the agent: prompt, draft, checks, render
    legal_ai/schemas/draft.py           the structure it returns
    legal_ai/knowledge/static/citation.py   an id rendered as a citation
    api/drafts/source.py                reading a thread into a draft's input

`agents/draft.py` already means "assemble the answer", which is why this
one is `drafter.py` -- two unrelated senses of one word would be worse
than a slightly awkward name.

**It is not a node in the research graph.** A document is not part of
answering a question, so a node would draft one on every turn nobody asked
for. It is an agent the orchestration calls when a reader presses the
button, and it is silent otherwise.

---

## Build order — each phase additive

**Phase 1 — the tables, executed in-process.**
Add `runs` and `run_events`. The existing detached task writes to them.
No worker process yet.
*Gets:* reconnect and replay, honest "still working" state, one-run-per-thread,
double-submit protection.
*Note:* the detached-run change this depends on is already written and
awaiting commit.

**Phase 2 — move execution to a worker, and the frontend to SSE.**
The API stops running graphs; it only enqueues and watches. Workers claim
with `SKIP LOCKED`. The connection manager takes delivery over, with
`LISTEN/NOTIFY` in front of the polling that already works, and the
frontend opens a stream instead of polling every three seconds.
*Gets:* survives restart and deploy, cancellation, backpressure, horizontal
scale, and a request cost per waiting reader that stops growing with the
number of them.

**Phase 3 — the models behind HTTP.**
The embedder and the cross-encoder move into one inference service, so a
worker is ~250 MB rather than 1.2 GB. Worth doing when a second worker is
— break-even is two.
*Gets:* more than two workers on one box, and a GPU that serves all of
them rather than one.

**Phase 4 — checkpoint and reaper.**
Persist graph state per step; heartbeat and sweep.
*Gets:* mid-run resume (stop paying twice), zombie detection, graceful drain.

Nothing in one phase is rewritten by the next. The schema above is the whole
contract, and it is the reason this is worth designing before building.

---

## What this deliberately does not solve

- **Speed.** A turn is ~119s, of which ~90s is two model calls and roughly
  40s of that is free-tier rate-limit backoff. That is a separate axis and
  a bigger user-facing win; see the timings in the session notes.
- **Model non-determinism.** The same question can produce a different
  answer on two runs. Reliability infrastructure cannot fix that and should
  not pretend to.
- **Whether a draft is any good.** This guarantees a draft is reproducible,
  attributable, and never invents a citation. It does not guarantee a lawyer
  would sign it. That needs its own eval set, the way retrieval has one.
- **Auth expiring mid-run.** A 2-minute run outliving a session leaves the
  answer saved but the reconnect unauthorised. Small, real, separate.
