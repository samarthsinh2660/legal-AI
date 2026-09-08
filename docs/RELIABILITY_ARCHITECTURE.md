# Reliability architecture — the end state

**Status:** built and QA'd against containers, 2026-09-05/06. The tables,
the worker, the connection manager, the model servers, the reaper and
cancellation all exist. The one piece deliberately not built is the
checkpoint -- see the build order for why. See the build order at the
end for exactly which is which.

The problem this settles: a research turn takes 30–130 seconds and costs
real model budget, and almost anything that interrupted it used to lose the
work. This document describes the shape built *once*, so each later piece
is additive rather than a rewrite.

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

Measured or reproduced on this system, not hypothetical. ✓ marks what a
QA pass has since confirmed against the running stack.

| Event | Was | Now |
|---|---|---|
| Browser closes mid-run | answer lost | answer stored ✓ |
| Refresh / new tab mid-run | a spinner and a guess | attaches and replays ✓ |
| Live progress after refresh | lost | replayed from `Last-Event-ID` ✓ |
| Second tab, same thread | a parallel run; findings interleave | 409 `run_in_progress` ✓ |
| Deploy / graceful restart | run dies silently | worker drains, answer stored ✓ |
| Thread deleted mid-run | FK violation per step, run paid for anyway | stops between nodes ✓ |
| Worker killed outright | row stranded | swept back onto the queue ✓ |
| Reader leaves | full model budget still spent | cancellable; stops at the next node ✓ |
| Retry after a crash | would duplicate the answer and the case findings | exactly one worker finishes ✓ |
| 100 requests at once | 100 tasks, 16 executor threads, no backpressure | they queue ✓ |
| 100 readers waiting | 33 polls/second, growing with every reader | one stream each, then silence ✓ |

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

### How many workers are worth running, and in what shape

One, today. Not because the queue cannot take more -- `--scale worker=3`
works and no run was ever claimed twice -- but because all of them share
one free-tier model key. Measured over 45 minutes of QA on 2026-09-06,
three workers took 62 rate-limited responses between them (20, 22, 20).

A third worker buys a third more *requests* against the same quota, not a
third more answers. The number to raise first is the key's.

**So sizing the worker count on free memory would size it on the one
resource that is not scarce.** The signal that would actually mean
something is queue depth against model-quota headroom -- and with one key
and one reader, neither is worth automating yet.

**When the quota does move, move the models out before adding workers.**
A worker is 163 MB of its own work carrying 1290 MB of model stack, so the
second worker is expensive for the wrong reason -- see the model-server
section below, where that is measured line by line.

Threads are the cheaper way to add a second worker *while the models stay
in-process*: measured, four concurrent threads peaked at 1720 MB against
~5344 MB for four processes, because threads share a loaded model and
processes do not. But that is a workaround for a cost that should not
exist, and it buys a shared crash domain and a harder drain. Behind a
model server the question disappears -- plain processes, 163 MB each.

It is also why "how many workers fit in the available RAM" has no useful
answer: the number swings by 10x on process-or-thread and by 9x on
where the models live, so it is a question about architecture, not memory.

That is a change to `Worker.run_forever`, not to the queue: claiming is
already `FOR UPDATE SKIP LOCKED`, which is safe from any number of
claimants in any number of processes. The costs are the usual ones -- one
thread crashing takes the process, and the SIGTERM drain has to wait for N
jobs instead of one -- and neither is worth paying until something other
than the model key is the limit.

What the queue buys before any of that: a deploy that drains rather than
drops, a restart that loses nothing, and a second worker that is a flag
rather than a project.

### The browser never sees a worker

```
  browser  ──►  API  ──►  Postgres  ◄──  worker
```

One arrow into the API, and the worker on the far side of the database.
The browser's only endpoints are the API's; `/runs/{id}/stream` is an API
route reading `run_events`, not a connection to whatever is producing them.

This is not a convention to remember. It is what makes the rest true:

- A worker with no inbound port cannot be reached, so it can run anywhere,
  and a leaked reader token buys nothing on it.
- Any API instance can serve any run, because the state is in the table and
  not in the process working on it. Verified by restarting the API mid-run:
  the run finished regardless, and the replacement process -- which had
  never seen the run start -- replayed all sixteen of its events.
- A worker can be redeployed, scaled or moved mid-run without a client
  noticing anything but a gap in the steps.

Guarded by `tests/worker/test_boundaries.py`: nothing under `src/worker/`
may import a web framework, the worker stage declares no `EXPOSE`, and no
frontend source names a host of its own.

---

## What the images actually weigh

Measured, because the intuition is wrong. Splitting the graph into a worker
is not what made the API smaller — the graph's own packages are about
170 MB. The API's weight was CUDA, on a machine with no GPU.

Inside the built image's site-packages, before and after (2026-09-06):

```
                    before    after
  nvidia/           2724 MB       0     CUDA driver libraries
  torch/            1127 MB   769 MB    CPU wheel instead of the CUDA one
  pyarrow/           156 MB       0     nothing in src/ imports it; it came
                                        in transitively and stopped when
                                        bharat-courts dropped it at 0.4.0
  transformers/      113 MB   113 MB
  scipy/ + sklearn/  158 MB   158 MB
  langgraph/           4 MB       0     worker image only
  ─────────────────────────────────
  site-packages     5501 MB  1445 MB
  image             5.77 GB  1.53 GB
```

The worker is 1.64 GB: the same base, plus langgraph and the two packages
its live-discovery fallback reaches.

For scale: fastapi and psycopg together are **4 MB**. Everything else in
that image is the model stack, and the API pulls it in for one reason —
`/search` embeds and reranks the query in-process.

Two changes got the 73%, and neither is the worker split:

- **CPU-only torch.** `--index-url https://download.pytorch.org/whl/cpu`,
  one build argument. `nvidia/` disappears and the torch wheel itself drops
  by a third.
- **Dependency extras.** `[project.dependencies]` is what the API needs;
  `worker` adds langgraph, `ingest` adds pyarrow, beautifulsoup4 and the
  court archives client — and `ingest` is in neither image, because those
  jobs are run by hand against the database.

The remaining 1.0 GB is torch, transformers, scipy and sklearn. It leaves
with Phase 3 and not before.

### If the box has a GPU

The Dockerfile takes `TORCH_INDEX`, defaulting to the CPU wheels:

```bash
docker build --target worker \
  --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121 -t worker:gpu .
```

Then give the container the device (`--gpus all`, or compose's
`deploy.resources.reservations.devices`). No code changes:
sentence-transformers uses CUDA when torch reports it, and falls back when
it does not — so the same source runs on both, and the image is what
differs.

That image is ~4 GB again, which is the trade: pay it on the machine where
the GPU earns it, and keep the CPU image everywhere else. Which is the
argument for Phase 3 — one GPU image serving every worker, rather than a
GPU image *per* worker.

---

## The models are a service, not a library

Every worker that runs retrieval loads the embedder and the cross-encoder
itself. Measured line by line, in one process (2026-09-06):

```
  bare python                                     11 MB
  + psycopg, pydantic, the queue, the stores      40 MB
  + the research graph, compiled                  77 MB
  + live discovery                               163 MB
  ────────────────────────────────────────────────────
  a worker that calls a model SERVICE            163 MB

  + torch                                        605 MB   (+442)
  + sentence-transformers                        847 MB   (+242)
  + the embedder, loaded                        1352 MB   (+505)
  + the cross-encoder, loaded                   1453 MB   (+101)
  ────────────────────────────────────────────────────
  a worker that loads them itself (today)       1453 MB
```

**A worker is 163 MB of work and 1290 MB of model stack** — and 684 MB of
that 1290 is torch and sentence-transformers themselves, not weights. Every
extra worker process pays all of it again for an identical copy.

The fix is to load them once, behind HTTP. **Built and measured
2026-09-06:**

```
                 ┌──────────────────────┐
                 │  embedder    1.20 GB │   TEI, one model per container
                 │  reranker    0.84 GB │   loaded once, GPU if present
                 └──────────┬───────────┘
                            │  HTTP
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
      worker 1          worker 2          worker 3       148 MB each
```

A worker went from **1453 MB to 148 MB** resident, measured after a real
turn, and imports no torch at all. Startup went with it:

    models loaded in 20.3s          -> models ready in 0.1s (served over HTTP)

The servers are two containers, not one: TEI serves a single model each.
Their combined 2.04 GB is with the buffers sized down. TEI defaults to
16384 batch tokens and 512 concurrent requests and pre-allocates for them,
and the client never sends more than 32 texts at once, so the defaults were
paying for traffic that does not exist:

    reranker, default buffers    1.32 GB    6.11s over 50 passages
    reranker, sized to traffic   0.88 GB    5.07s

Smaller *and* faster, which is not the usual direction -- fewer, fuller
batches beat more, emptier ones.

**On CPU this is not a speed win, and was never going to be:**

    reranking 50 passages, in-process PyTorch    4.73s
    reranking 50 passages, TEI over HTTP         5.07s
    reranking 50 passages, TEI on an RTX 3050    0.61s

Seven percent slower per rerank, so about 0.7s on a turn that reranks
twice. That is the price of the memory, and it is refunded many times over
the moment the servers get a GPU -- which is the whole point of putting
them somewhere a GPU can be.

| Workers | In-process (1.45 GB each) | Served (2.04 GB once, +148 MB each) |
|---|---|---|
| 1 | 1.45 GB | 2.19 GB |
| 2 | 2.91 GB | 2.34 GB |
| 3 | 4.36 GB | 2.48 GB |
| 8 | 11.6 GB | 3.23 GB |

**Break-even is two workers**, which is what the estimate said before any
of it was built. At one it costs 0.7 GB and buys nothing.

### Why it was safe to do at all

Every vector in the corpus came from `all-mpnet-base-v2`. A server that
embedded even slightly differently would mean re-embedding 35,601 sections
and 332,025 chunks before search worked again, so this was checked before
anything was written:

    embeddings   worst cosine 0.999999955, worst |diff| 1.57e-07
    reranking    ordering and top-10 identical

Float32 rounding, not disagreement. The reranker's *scores* do differ --
TEI returns a sigmoid where the local CrossEncoder returns the raw logit,
so -6.2726 becomes 0.0019 -- which is harmless only because the sole
caller keeps the order and discards the score. `tests/inference/` holds
both checks, skipped when no server is running.

### The switch

`LEGAL_AI_EMBED_URL` and `LEGAL_AI_RERANK_URL`. Set, the model is called;
unset, it is loaded in-process exactly as before. Nothing else changed:
`embed()` and `rerank()` keep their signatures, so retrieval, the evals and
the re-embed scripts are all unaware.

A configured server that is down raises rather than falling back to a local
load. A worker sized for 148 MB that quietly loads 1.3 GB instead trades a
loud failure for an OOM kill later, on another machine, with nothing
pointing back here.

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

Built, in `src/api/runs/repository.py`:

```sql
runs (
  run_id        text primary key,
  thread_id     text not null references threads on delete cascade,
  user_id       text not null,
  kind          text not null default 'research',  -- research | draft
  status        text not null,      -- queued|running|done|failed|cancelled
  current_step  text,               -- 'research', 'analyst', ...
  payload       jsonb not null,     -- the job's whole input
  error         text,
  created_at, started_at, finished_at timestamptz
)

run_events (
  run_id     text references runs on delete cascade,
  seq        int,                   -- monotonic per run; the SSE event id
  kind       text,                  -- step | answer_chunk | done | error
  payload    jsonb,
  created_at timestamptz,
  primary key (run_id, seq)
)
```

`payload` is what makes a worker on another machine possible: it reads the
row and nothing from the request, so there is no shared memory, no session
and no filesystem between the two.

`attempts` and `heartbeat_at` are what the reaper reads: a row whose
heartbeat has stopped is a row nobody owns, and one past `MAX_ATTEMPTS` is
the job's fault rather than the worker's.

The drafts table predates this and is unchanged:

```sql

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

Two partial indexes carry the hot paths:

```sql
-- "Is anything running on this thread", asked on every thread load.
create index runs_thread_live_idx on runs (thread_id)
  where status in ('queued', 'running');

-- The claim query, which every idle worker runs on every sweep.
create index runs_queued_idx on runs (kind, created_at)
  where status = 'queued';
```

One run per thread is enforced in the controller against the first of
those, not by a unique index: the refusal has to reach the reader as a 409
with something to read, and a constraint violation arrives as an exception
with a DSN in it.

**What the table carries:** every event, the lede's word-by-word chunks
included. They were left out while producer and reader shared a process and
an `asyncio.Queue`; with the producer in a worker, the table is the only
wire between them. About twenty rows per run, deleted with the thread.

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

A planned stop is already handled: SIGTERM asks the worker to finish the
job in hand and then exit, so a deploy costs a drain and nothing else.
Verified live 2026-09-05 -- the run was mid-graph, the worker took 24 more
seconds, stored the answer and left.

An unplanned death is handled too. The row says `running` with a
`heartbeat_at` that stops advancing; every idle worker sweeps for rows whose
heartbeat is older than `STALE_AFTER_SECONDS` (600s, comfortably past the
graph's own 300s ceiling) and either requeues the run or, past three
attempts, fails it with a reason and a terminal event.

The requeued run resumes from the evidence the dead attempt found, so it
re-pays for the analysis but not the search -- measured at 0.9s against
~30s. The reaper can only guess: a worker deep in a model call and a worker that
died look identical. So a run is occasionally requeued while its first
worker is still alive, and both finish. `complete()` is the guard --
`UPDATE ... WHERE status = 'running'`, in the same transaction as the answer
write, so exactly one of them stores anything. Two assistant messages would
be the visible half; duplicated case findings the real damage.

### Reader leaves, or presses cancel

`POST /runs/{id}/cancel` sets `status = 'cancelled'`; the worker sees it at
its next node and stops. A queued run never costs a model call at all; a
running one stops at the next boundary, because Python cannot interrupt the
call it is inside but *can* decline to start another.

The thread screen has a **Stop** control in the progress pane. It reads
"Stopping…" until the run's own stream reports the end, because asking to
stop is not stopping: the worker finishes the node it is inside first.

### Retry after a crash

The run is requeued and worked again from the start. What makes that safe
is that finishing is a race exactly one worker wins: `complete()` moves the
row from `running` to `done` and returns whether this caller was the one
that did, in the same transaction as the message write. A straggler that
was declared dead and comes back finishes nothing.

### Overload

Work waits in the `runs` table, not in RAM -- one worker takes one job at a
time and the rest stay queued. Queue depth is a `SELECT count(*)`, which is
also what would let the UI say "3rd in line, about 4 minutes" instead of a
spinner indistinguishable from a hang. Nothing shows it yet; the number is
there when a screen wants it.

---

## The drafting job

A button beside the composer. It turns the conversation that just happened
into a document the reader downloads. **Shipped**, and on the queue as
`kind='draft'` since 2026-09-05 -- the same claim, the same worker, the
same `runs` row; only the handler differs.

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
    worker/drafting.py                  the job: read the thread, draft, store

`agents/draft.py` already means "assemble the answer", which is why the
agent is `drafter.py` -- two unrelated senses of one word would be worse
than a slightly awkward name.

**It is not a node in the research graph.** A document is not part of
answering a question, so a node would draft one on every turn nobody asked
for. It is an agent the worker calls when a reader presses the button, and
it is silent otherwise.

---

## Build order — each phase additive

**Phase 1 — the tables. DONE (2026-09-05).**
`runs` and `run_events`, `GET /runs/{id}` and `GET /runs/{id}/stream` with
`Last-Event-ID` replay, `active_run` on the thread.
*Got:* reconnect and replay, an honest "still working" state -- a row says
whether a turn is running or died, where a five-minute clock used to guess.

**Phase 2 — execution in a worker, delivery over SSE. DONE (2026-09-05).**
`src/worker/` claims jobs with `FOR UPDATE SKIP LOCKED` and dispatches on
`kind`; the API only enqueues. `NOTIFY run_queued` wakes an idle worker,
`NOTIFY run_changed` wakes the connection manager, and both are latency
alone -- the worker's sweep and the stream's heartbeat are what guarantee
delivery. The frontend opens one stream instead of polling every three
seconds, and asking and reopening are now the same code path.
*Got:* survives restart and deploy, one run per thread, horizontal scale
(`--scale worker=N`, no coordination), and a request cost per waiting
reader that no longer grows with the number of them.
*Not yet:* cancellation, and a reaper for a worker that dies without
draining. Both Phase 4; the between-nodes check the worker already makes
for a deleted run is the seam cancellation will use.
*Verified:* 41 HTTP cases and 8 process-failure cases against containers,
2026-09-06. Five bugs found and fixed in the pass -- see the QA record for
that date.

**Phase 3 — the models behind HTTP. DONE (2026-09-06).**
Two TEI containers, one per model. `LEGAL_AI_EMBED_URL` and
`LEGAL_AI_RERANK_URL` switch `embed()` and `rerank()` from loading to
calling; unset, they load in-process as before.
*Got:* a worker of **148 MB** rather than 1453, startup of 0.1s rather than
20.3s, and one place to put a GPU. Verified interchangeable with the local
models first -- worst cosine 0.999999955 -- so the corpus did not need
re-embedding.
*Not yet:* the GPU itself. `nvidia-container-toolkit` is not installed on
this host, and the CUDA TEI image is a tag swap plus a device reservation
once it is. Measured on this machine's RTX 3050: reranking 50 passages,
5.12s on CPU against 0.61s on GPU, identical ranking.

**Phase 4 — checkpoint, cancellation and reaper. DONE (2026-09-06).**
A heartbeat written between nodes, a sweep on every idle worker, a cancel
the worker honours at the same seam, a completion exactly one worker can
win, and a checkpoint of the evidence a dead attempt found.
*Got:* a killed worker's run comes back instead of stranding a reader
forever; a reader who leaves stops paying; a requeued run cannot answer
twice, and does not buy the search again.

Verified live: a worker killed mid-run, its heartbeat aged, and the run
swept back onto the queue. The second attempt logged `resuming with 10
findings` and finished in **0.9s** rather than ~30s -- the research node
never ran.

**Only `findings` is carried.** It is where the time is (about 7s of
planning and 11s of retrieval) and the only part of the graph channel that
round-trips *provably*: Evidence is a pydantic model, so `model_dump` and
`model_validate` are exact, and a test asserts the round trip including
provenance. `ThreadContext` is a frozen dataclass and costs 1.3s to
rebuild, so it is rebuilt rather than serialised.

The restore is all-or-nothing. Anything unreadable is discarded whole and
the run searches afresh, because half a list would put an answer's
citations on evidence that was never properly rebuilt -- the silent
degradation everything else here exists to prevent. And it applies only on
the first round: the loop back from verification is asking for evidence the
first pass did not find, and skipping that would answer the same question
with the same gaps.

Nothing in one phase is rewritten by the next. The schema above is the whole
contract, and it is the reason this was worth designing before building.

---

## What this deliberately does not solve

- **Speed.** A warm turn is 18-40s: roughly 7s planning, 11s retrieval and
  7s analysing. Retrieval is the largest share and 97% of it is the CPU
  cross-encoder, which a GPU behind the model servers would take from ~5s
  to 0.61s. The rest is two model calls on a free-tier key, and that same
  quota is what caps throughput -- see the worker-count section.
- **Model non-determinism.** The same question can produce a different
  answer on two runs. Reliability infrastructure cannot fix that and should
  not pretend to.
- **Whether a draft is any good.** This guarantees a draft is reproducible,
  attributable, and never invents a citation. It does not guarantee a lawyer
  would sign it. That needs its own eval set, the way retrieval has one.
- **Auth expiring mid-run.** A 2-minute run outliving a session leaves the
  answer saved but the reconnect unauthorised. Small, real, separate.
