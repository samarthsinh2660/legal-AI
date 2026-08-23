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
| 6.4 | Document Agent --- extract structure from an upload into the context | **done** |
| 6.5 | Clarification gate | **done** |
| 6.6 | Tier-1 `Evidence` --- matched passage, location, court, citation | **done** |
| 7.1 | Researcher subgraph --- plan, execute, validate, compress | **done**, measured below |
| 7.2 | Supervisor --- decompose, fan-out, merge | **done**, measurement pending |
| 8 | Verification --- groundedness, coverage, bounded re-research | **done** |

**The agent and the "rewrite-only" path are the same code.** At one angle
the agent runs `plan_research` then `hybrid_search(query, limit)` -- the
identical call the rewrite baseline in `evals.run --rewrite` makes. They
were never two designs to choose between; the agent is that path plus
decomposition when a question raises several legal angles, plus document
context, plus a summary when the findings are long. Same one model call.

**Multi-angle is still unmeasured.** All 50 lookup questions have one
correct answer in one Act, so decomposition can only add noise there and
never shows a benefit. `evals/datasets/multi_angle.json` exists for that --
10 questions whose answer is a *set* of provisions across Acts, scored by
coverage rather than rank -- but it has not produced a valid run: attempts
hit quota exhaustion, a stopped database, and rate limiting in turn.

    .venv/bin/python -m evals.run_multi_angle

Whether decomposition earns its cost is therefore **unknown**, and should be
stated as unknown rather than assumed either way.

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

Rewriting the question into statutory vocabulary before searching raises
that to somewhere in **0.47 - 0.67** depending on the run. The lower bound
of that range still beats plain retrieval, which is the finding that
survives; the spread is measurement noise, not a difference between
configurations. See §8a.

Fusing the original query with the rewrite was tried and appeared worse
(0.584), but that was a single run and is inside the noise -- treat it as
untested rather than settled.

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

## 8a. Measured results

**Read the variance section first. It changes how every number below should
be read.**

### The benchmark is noisy

The search query is written by a model, so the same configuration scores
differently every run. Measured 2026-08-23 on identical code:

| run | MRR | recall@1 | recall@5 |
|---|---|---|---|
| rewrite path, first run | 0.670 | 56% | 86% |
| rewrite path, re-run | 0.516 | 40% | 68% |

**Roughly +/-0.15 MRR of run-to-run spread.** Any comparison of two
configurations from single runs is meaningless unless they differ by more
than that.

### And the cause is not sampling -- it is which model answered

`generate()` walks an eight-model chain, falling through on a 429. Under
sustained load `gemini-flash-latest` rate-limits almost immediately, so the
chain slides to the bottom and stays there. A run on 2026-08-24 reported:

    models used: {'gemini-3.5-flash-lite': 93, 'gemini-3.6-flash': 2,
                  'gemini-3.5-flash': 2, 'gemini-3-flash-preview': 2,
                  'gemini-flash-latest': 1}

**93 of 100 calls went to the weakest model in the chain**, and one to the
strongest. That is not one measurement -- earlier and later questions were
answered by different models and the score blends them. It also means every
figure in this section was produced mostly on `flash-lite`, so none of them
show what the system does on the model it was meant to run on.

`MODEL_USAGE` in `legal_ai.llm.client` now records this and the eval runners
print a MIXED MODELS warning, so a confounded run is visible instead of
silent.

This was learned expensively. Six configurations were measured across one
day, differences of 0.03 to 0.10 were treated as findings, and three
"regressions" were recorded that the variance fully explains. The bar itself
-- "0.670" -- was measured once and never re-checked.

**Before comparing configurations: pin one model, run each several times,
and compare the spread.**

### What is actually supported

| configuration | MRR | notes |
|---|---|---|
| plain retrieval, no model | **0.467** | deterministic, so this number is solid |
| rewrite path | 0.516 - 0.670 | two runs, mixed models |
| research agent | 0.470 - 0.570 | several runs, mixed models |

- **The rewrite helps.** Every model-using run beats deterministic plain
  retrieval, including the worst of them. That comparison survives both the
  noise and the model confound, and it is the one firm result of the phase.
- **The agent versus the rewrite-only path was never a real question.** They
  are the same code at one angle -- `plan_research`, then
  `hybrid_search(query, limit)`. Nothing distinguishes them to measure.
- **Every other comparison from this phase is void**, being single runs on
  mixed models with differences smaller than the spread.

The agent is kept because it is a superset: the same single model call and
the same statutory rewrite, plus decomposition when a question raises
several legal angles, plus document context, plus a summary when the
findings are long. It gives more for the same cost.

### One finding that is not noise

**`search_statutes` was using bare vector search** -- no keyword fusion, no
reranking, no chunks -- while every comparison was against the full
`hybrid_search` pipeline. That is a code defect, not a measurement, and
fixing it is why the tool now goes through `hybrid_search`. Its effect on
the benchmark cannot be separated from the noise, but the bug was real.

### Why a rewrite helps at all

The corpus holds statutes, written in drafting language. People describe
grievances in ordinary language. Neither contains the other's words:

    builder                -> promoter
    did not hand over      -> fails to give possession
    get my money back      -> return of amount

Keyword search cannot bridge it: RERA s.18 never uses the word "builder", so
there is no overlap to score. Vector search should and does not reliably:
`all-mpnet-base-v2` is trained on general English, where builder and
promoter are loosely related, while in Indian statutory usage they are the
same legal role. Against 35,601 competing sections, loosely related is not
enough.

The rewrite fixes it at the query, which is the only place it can be fixed.
The proper fix is a legal-domain embedding model; InLegalBERT was tried in
Phase 2 and measured 3.4x worse.

### Cost

One model call per question, whatever the angle count -- angles and their
statutory queries come back together. A second call summarises, and only
when the findings are too long to hand over as they are.

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
