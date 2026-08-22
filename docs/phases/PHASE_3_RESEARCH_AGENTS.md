# Phase 3 --- Research Agent System

## Objective

> Can AI perform legal research, instead of merely performing search?

Phase 2 built tools that return evidence for a query. Phase 3 introduces the
system that decides *what* to search, *when* to search again, judges whether
what came back is enough, and returns a grounded answer.

Design detail, and the reasoning behind every decision below, lives in
[`../superpowers/specs/2026-08-20-phase3-research-agent-design.md`](../superpowers/specs/2026-08-20-phase3-research-agent-design.md).

------------------------------------------------------------------------

## 1. Agent Architecture

Built on **LangGraph**, following the layout conventions of
[`langchain-ai/open_deep_research`](https://github.com/langchain-ai/open_deep_research).

``` text
                    Supervisor
                        |
          decomposes into N angles, capped
                        |
      +-----------+-----+-----+-----------+
      |           |           |           |
      v           v           v           v
  Research    Research    Research    Research      (parallel, N <= 3)
   Agent 1     Agent 2     Agent 3      ...
      |           |           |           |
      +-----------+-----+-----+-----------+
                        |
                  each COMPRESSES
                  before returning
                        |
                    Supervisor
                 reflect: enough?
```

The Supervisor makes exactly **two** judgments:

1. how many angles to research
2. go again, or stop

Everything else in the pipeline is fixed. There is no split-versus-single
mode: the Supervisor holds one `ConductResearch` tool, and how many times it
calls it *is* the answer. **Calling it once is the single-agent case, and
that is the expected common case** --- a simple lookup must not spawn three
agents.

### The LLM never calls a tool

Control flow belongs to the orchestrator; the LLM handles ambiguity. Each
research agent invokes a model at exactly **two** bounded points per round,
and each produces *data*, not actions:

``` text
Orchestrator     decides the research stage runs
      |
Agent call 1     BOUNDED REASONING -- emits a structured plan
      |          [{tool: search_statutes, query: "..."}, ...]
      |
Orchestrator     EXECUTES the plan
      |
Tool             Phase 2 contracts, unchanged
      |
Validator        deterministic gate -- id resolves, provenance present,
      |          passage non-empty, Evidence id survives compression
      |
State update     only validated Evidence enters state
      |
Agent call 2     BOUNDED REASONING -- "sufficient" or "still missing X"
      |
Orchestrator     loop or stop; the cap lives in code, not the prompt
```

A ReAct loop -- the model choosing which of seven tools to call, up to N
times -- was rejected. A cap bounds the damage without changing who drives.
Plan-then-execute is testable with a canned plan and no model, its cost is
knowable before it is spent, and it makes two model calls per angle instead
of up to eight, which is what keeps the free tier viable.

It loses in-flight adaptation. The outer loop, capped at 3 rounds, gives two
chances to adapt -- enough for the failure actually measured, where retrieval
finds the right Act and the wrong section and the fix is to call
`get_section` on the Act it already found.

Each agent ends by compressing its validated findings, so the Supervisor
receives summaries rather than every retrieved document.

### Why not one agent per data layer

An earlier draft of this phase gave Static, Dynamic and Active their own
agents. That does not survive contact with what Phase 2 built:

- **Static** is `hybrid_search` over the stored corpus --- a query.
- **Dynamic** is a fallthrough *inside* `search_judgments`, which checks the
  database and fetches live on a miss. No agent chooses it.
- **Active** reads what Phase 6 validation approved, and Phase 6 does not
  exist yet.

Static / dynamic / active remains the **data-layer authority taxonomy** it is
in `PROJECT_STRUCTURE.md` §9, governing what may be promoted into
authoritative knowledge. It is not an axis to spawn agents on.

The axis that does justify parallel agents is the **sub-question**: for a
builder-delay matter, the RERA remedy, the consumer forum, and limitation are
genuinely different research problems.

------------------------------------------------------------------------

## 2. The Pipeline

Fixed stages, with agency confined to the research stage. The path is the
same every run, which is what makes it measurable.

``` text
        user question  (+ documents, + case)
                |
        DOCUMENT AGENT         only if documents attached; returns
                |              STRUCTURE into the context, never raw text
                v
        Context Builder        ThreadContext -- built ONCE, read-only
                |              case_id optional; sets court + date filters
                v
        Clarification?         asks ONLY on a blocking gap
                |
                v
        [ RESEARCH STAGE ]     Supervisor + N agents, capped
                |
                v
        Analyst                structured claims, each carrying an
                |              Evidence id  (Phase 5)
                v
        Verification           groundedness + coverage
                |              unsupported -> re-research, cap 2
                v
        Draft                  DraftAnswer -- the UI contract  (Phase 5)
                |
                v
              user
```

The **full skeleton is built in this phase**, with Document, Analyst and
Draft as thin pass-through nodes carrying real schemas. Phases 4--5 fill
their bodies without reshaping the graph.

------------------------------------------------------------------------

## 3. Document Agent --- it builds the context, so it lands here

A thread that carries an uploaded document cannot be researched until the
document is understood. `ThreadContext` is defined to hold case facts,
parties, dates and documents; something has to *produce* those, and that is
the Document Agent. It therefore runs **before** the Context Builder, not in
a later phase.

``` text
   PDF / DOCX  (a petition may run to 300 pages)
        |
        v
  DOCUMENT AGENT          spends its OWN context window on the raw file
        |
        +--> parties
        +--> dates
        +--> clauses
        +--> sections cited
        +--> issues
        |
        v
  STRUCTURE ONLY  ------> ThreadContext
  (never raw text)
        |
        v
  CONTEXT BUILDER --> CLARIFICATION --> RESEARCH
```

**Why it must be a separate agent and not a tool call inside the
researcher.** A 300-page petition does not fit in the researcher's window,
and it should not: the researcher needs *what the document says*, not the
document. The Document Agent burns its own window on the raw file and
returns structure. That is the identical isolation pattern used for research
fan-out --- one agent per large input, compressed before it crosses a
boundary.

**Scope split with Phase 4.** Phase 3 builds what the context needs:
extraction of parties, dates, clauses, cited sections and issues into
`ThreadContext`. Phase 4 builds the deeper document intelligence --- clause
analysis, contradiction detection, and the Documents screen in
`design/UX_FLOWS.md`.

**Known gap:** `CHUNKABLE_TYPES` is currently `("section", "judgment")`. An
uploaded petition is a new document type and will not chunk until it is
registered.

------------------------------------------------------------------------

## 4. Shared Thread Context

Implements `AI_PROJECT_PROPOSAL.md` §6. Built once per thread, passed
read-only to every node. Three additions in this phase:

**Clarification gate.** Research does not start while a missing fact would
make it wrong. Blocking gaps are enumerated, not guessed: **state** (RERA is
state-wise, rent and stamp law vary), the **relevant date**, and
**forum/stage** where the remedy depends on it. Everything else is assumed,
and the assumption is stated in the answer.

**Case attachment, at any time.** Per `design/UX_FLOWS.md`, a thread may
belong to no case --- a student researching a doctrine never needs one. An
unattached thread offers *Attach to case*; on attaching, its context is
seeded with that case's parties, timeline and established findings.
`case_id` is optional and never required at thread creation.

**Filters the context populates.** Phase 2 shipped `MetadataFilters` with
`court` and `decision_date_*` and nothing fills them. The Context Builder
does: jurisdiction so a Gujarat matter weights Gujarat High Court, and the
relevant date so the law as it stood then is what gets retrieved.

------------------------------------------------------------------------

## 5. Static, Dynamic and Active --- how each is actually reached

``` text
STATIC    hybrid_search over the stored corpus.
          Constitution, India Code, Acts, Sections, Rules,
          Supreme Court and Gujarat High Court judgments,
          verified citations.

DYNAMIC   A fallthrough inside search_judgments: database first,
          live fetch on a miss. Sources confirmed in Milestone 0
          (DATA_RECON_FINDINGS.md) -- Bharat Courts, India Code,
          Indian Kanoon where permitted.

          A verified live fetch is STORED: upserted, embedded,
          chunked, and written into the graph. The corpus grows by
          being used. This is not a layer violation -- a judgment
          from an official source is source_type="primary".
          Fetching is not inferring.

          Staleness is a property of the QUESTION, not of a search.
          The Context Builder sets needs_current_law once, when the
          user asks for the current position or whether something is
          still good law, and the tools then skip the cache.

ACTIVE    An unconditional node in the verification stage, not a
          researcher. Read side only; Phase 6 owns the write side.
```

------------------------------------------------------------------------

## 6. Verification --- and the failure nothing else catches

Two failure modes, only one of which was previously covered:

| Failure | Description | Caught by |
|---|---|---|
| Hallucination | claims something the evidence does not support | groundedness check |
| **Miss** | never retrieved the relevant law at all | **coverage check** |

Verification only inspects what was said; nothing inspects what was *not*
said. That is what the Active layer answers --- *threads like this relied on
Section X, which this run never retrieved.* It must run **after** research;
run before, it anchors the agent onto old paths and replays old answers.

Groundedness runs first and uses **no LLM**: does every claim carry an
Evidence id, does that document exist, does the cited paragraph exist. It
cannot itself hallucinate, which is why it goes first.

Until Phase 6 supplies coverage data, the same slot runs a deterministic
stand-in over existing graph edges.

On exhausting the re-research cap with claims still unsupported: **answer,
with the unsupported claims flagged** in the "what may need further
verification" field the UX already defines. Never a silent drop --- a user
cannot tell a short answer from an incomplete one.

------------------------------------------------------------------------

## 7. Evidence --- small by default, expand on demand

Three tiers, of which two already exist:

``` text
TIER 1   matched passage + location + court + citation
         returned by every search                        <- built here

TIER 2   full document text
         agent calls get_section / get_judgment          <- already built

TIER 3   the source PDF
         user clicks Open in the source panel            <- already built
```

An agent expanding a passage is the same action as a user clicking "show
more", and needs no new tools. Returning passages rather than whole documents
also keeps compression honest: four results are four passages, not four
40,000-character judgments.

**Compressed findings must carry their Evidence ids.** A summary that drops
them makes every downstream claim ungroundable, and verification then fails
*open* --- passing because there is nothing left to check. This is the
highest-risk detail in the phase.

------------------------------------------------------------------------

## 8. Milestones

| # | Deliverable | Status |
|---|---|---|
| 6.1 | Harness --- `evals/` datasets, evaluators, 50 questions | **done** |
| 6.2 | `ThreadContext` --- builder, revisions, invalidation, `case_id`, filters | **done** |
| 6.3 | Graph skeleton --- `langgraph.json`, state, nodes, caps | **done** |
| 6.4 | **Document Agent** --- extract structure from an upload into the context | to do |
| 6.5 | Clarification gate | to do |
| 6.6 | Tier-1 `Evidence` --- matched passage, location, court, citation | to do |
| 7.1 | Researcher subgraph --- plan, execute, validate, compress | to do |
| 7.2 | Supervisor --- fan-out, reflect loop, caps, overflow | to do |
| 8 | Verification --- groundedness, coverage, bounded re-research | to do |

Milestone numbering is project-wide, not per-phase: Phase 1 ran milestones
0--3, Phase 2 ran 4--5, so Phase 3 begins at 6.

The harness lands **first**, not last. Without it every agent change is
guesswork --- the failure mode Phase 2 rejected when it measured away the
relevance floor and graph expansion.

Caps are configuration, enforced in code rather than prompt: **3** concurrent
research agents, **3** supervisor iterations, **8** plan steps per round, **2**
re-research passes. The loop always terminates on the cap; it never relies on
the model choosing to stop.

Model is **Gemini** (`gemini-flash-latest` or `gemini-3.5-flash`; the 2.0 and
2.5 flash names now return 404), with a fallback model for rate limits.

`503 UNAVAILABLE` is transient and should be retried with backoff. `429
RESOURCE_EXHAUSTED` is the daily cap and must **never** be retried --- doing
so destroys the remaining budget. Distinguishing them is a requirement on the
client wrapper, learned by exhausting a day's quota on 2026-08-20 by treating
a 429 as a 503.

**Baseline to beat.** Milestone 6.1 measured Phase 2 retrieval alone at MRR
0.467, recall@1 32%, recall@5 64% on 50 questions.

A single LLM call then raised that to **MRR 0.670, recall@1 56%, recall@5
86%** by rewriting the question into statutory vocabulary before searching --
more than the whole reranking mechanism contributes. Fusing the original
query with the rewrite was tried and measured *worse* (0.584): the rewrite is
a better query, not a second opinion to blend.

**So 7.1 must beat 0.670, not 0.467.** A full plan-execute-validate loop that
cannot beat one rewrite call is not worth its cost, and the honest response
would be to ship the rewrite alone.

**Where rewriting lives: the planner, not retrieval.** It is tempting to put
the rewrite inside `hybrid_search`, since that is where the gain shows up.
It does not belong there. Rewriting is ambiguity resolution --- deciding what
a person actually means in legal terms --- which is the LLM's job.
`hybrid_search` is a *tool*, and tools stay deterministic: putting a model
call inside it would make every search cost quota and a second of latency,
would stop retrieval being testable without an API key, and would leave two
places rewriting once the planner also does it.

So **Phase 2 is unchanged.** The finding becomes a requirement on the
planner prompt --- emit queries in statutory vocabulary, not the user's ---
which is why it de-risks 7.1 rather than adding work to it.

------------------------------------------------------------------------

## 9. Deliverable

> AI can perform legal research instead of merely performing search.

------------------------------------------------------------------------

## 10. Explicitly not in this phase

``` text
Document clause analysis       -> Phase 4  (extraction into context is 6.4)
Contradiction detection        -> Phase 4
Documents screen               -> Phase 4
Case Agent                     -> Phase 4
Analyst / Draft internals      -> Phase 5  (nodes exist, bodies are stubs)
Verification Agent, full       -> Phase 6
Active knowledge write side    -> Phase 6
GraphRAG / precedent graph     -> Phase 7
Document and Case graphs       -> Phase 4-5; only the research graph now
Nested sub-sub-agents          -> not planned; one fan-out level only
```
