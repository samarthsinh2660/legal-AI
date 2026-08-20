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

Each research agent holds the Phase 2 tools unchanged (`search_statutes`,
`get_section`, `search_judgments`, `get_judgment`, `find_citations`,
`find_section_citations`, `find_judgment_sections`), and ends by compressing
its findings so the Supervisor receives summaries rather than every retrieved
document.

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
        Document node          only if documents attached
                |              (pass-through until Phase 4)
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

## 3. Shared Thread Context

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

## 4. Static, Dynamic and Active --- how each is actually reached

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

## 5. Verification --- and the failure nothing else catches

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

## 6. Evidence --- small by default, expand on demand

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

## 7. Milestones

| # | Deliverable |
|---|---|
| 6a | Harness first --- `evals/` datasets and evaluators, expanded question set |
| 6b | `ThreadContext` --- builder, serialization, revisions, invalidation, `case_id`, filters |
| 6c | Graph skeleton --- `langgraph.json`, state, build, all nodes as pass-throughs |
| 6d | Clarification gate |
| 6e | Tier-1 `Evidence` --- passage, location, court, citation through fan-in |
| 7a | Researcher subgraph --- Phase 2 tools, search loop, compress-with-provenance |
| 7b | Supervisor --- `ConductResearch` fan-out, reflect loop, caps, overflow handling |
| 8 | Verification --- groundedness, coverage stand-in, bounded re-research |

The harness lands **first**, not last. Without it every agent change is
guesswork --- the failure mode Phase 2 rejected when it measured away the
relevance floor and graph expansion.

Caps are configuration, enforced in code rather than prompt: **3** concurrent
research agents, **3** supervisor iterations, **8** tool calls per agent, **2**
re-research passes. The loop always terminates on the cap; it never relies on
the model choosing to stop.

Model is **Gemini**, with a rate-limit fallback model --- fan-out multiplies
calls and the free tier will throttle.

------------------------------------------------------------------------

## 8. Deliverable

> AI can perform legal research instead of merely performing search.

------------------------------------------------------------------------

## 9. Explicitly not in this phase

``` text
Document Agent internals       -> Phase 4  (node exists, body is a stub)
Case Agent                     -> Phase 4
Analyst / Draft internals      -> Phase 5  (nodes exist, bodies are stubs)
Verification Agent, full       -> Phase 6
Active knowledge write side    -> Phase 6
GraphRAG / precedent graph     -> Phase 7
Document and Case graphs       -> Phase 4-5; only the research graph now
Nested sub-sub-agents          -> not planned; one fan-out level only
```
