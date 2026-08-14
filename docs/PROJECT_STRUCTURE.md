# Project Structure — Indian Legal AI

The repository layout for the AI system described in
[`AI_PROJECT_PROPOSAL.md`](./AI_PROJECT_PROPOSAL.md), built on
**LangGraph** (agent orchestration), **LangChain** (model, tool and retriever
abstractions) and **LangSmith** (tracing, datasets and evaluation).

The structure exists to enforce the architecture, not just to hold files.
Three boundaries matter more than anything else:

1.  **Agents never know where data comes from.** They call internal tools;
    adapters decide whether that is India Code, Bharat Courts, a Parquet
    archive or Indian Kanoon.
2.  **The three data layers stay separate.** Static, dynamic and active are
    different packages with different authority, and nothing silently
    promotes between them.
3.  **Provenance travels with the data.** Every retrieval returns an
    `Evidence` object carrying its source; nothing is passed around as a bare
    string.

---

## 1. Top-level layout

Layout conventions follow
[`langchain-ai/open_deep_research`](https://github.com/langchain-ai/open_deep_research)
— a `src/<package>/` layout, a root `langgraph.json` declaring the graph
entrypoints, and per-module `state.py` / `configuration.py` / `prompts.py`
separation. Our tree is larger because that project has one research graph
while this one carries three data layers, a knowledge graph, ingestion
pipelines and a verification stage.

``` text
legal-ai/
├── README.md
├── pyproject.toml               # deps, tooling, package config
├── langgraph.json               # graph entrypoints, python version, auth
├── .env.example                 # keys: LANGSMITH, model providers, DB URLs
├── Makefile                     # ingest / serve / eval / test shortcuts
├── docker-compose.yml           # postgres+pgvector, neo4j, opensearch
│
├── docs/                        # architecture & research (this folder)
├── design/                      # brand, design system, UI prototype
│
├── src/
│   └── legal_ai/                # the installable package
│       ├── config/
│       ├── context/             # §6 shared thread context
│       ├── schemas/             # pydantic contracts shared by everything
│       ├── graph/               # LangGraph orchestration
│       ├── agents/              # agent definitions + prompts
│       ├── tools/               # the stable internal tool contracts
│       ├── sources/             # adapters behind those tools
│       ├── retrieval/           # hybrid search + reranking
│       ├── knowledge/           # static / dynamic / active layers
│       ├── graphdb/             # legal knowledge graph
│       ├── ingestion/           # corpus pipelines
│       ├── verification/        # citation & claim checking
│       ├── observability/       # LangSmith tracing, cost, logging
│       ├── security/            # auth.py — referenced by langgraph.json
│       └── api/                 # FastAPI service (thin)
│
├── data/                        # gitignored — local corpora & indexes
├── evals/                       # LangSmith datasets & evaluators
├── notebooks/                   # exploration only, never imported
├── scripts/                     # one-off operational scripts
│   └── recon/                   # Milestone 0 data-source probes — see §18
└── tests/
```

---

## 2. `context/` — the shared thread context

Implements §6 of the architecture. Built once per research thread, passed
read-only to every agent.

``` text
context/
├── __init__.py
├── models.py            # ThreadContext, QueryContext, JurisdictionContext,
│                        # CaseContext, DocumentRef, EstablishedFinding
├── builder.py           # build_thread_context(query, case?, documents?)
├── revisions.py         # versioning: new revision per promotion
├── invalidation.py      # which cached findings die when a field changes
└── serialization.py     # compact rendering for agent prompts
```

`serialization.py` matters more than it looks: the context is injected into
every sub-agent prompt, so it needs a compact, stable text form. A verbose
context multiplies token cost by the number of agents.

---

## 3. `schemas/` — shared contracts

Pydantic models that every layer speaks. Defined once, imported everywhere,
never duplicated per-agent.

``` text
schemas/
├── evidence.py          # Evidence, Provenance, SourceRef, Location
├── legal.py             # Act, Section, Judgment, Court, Citation, Party
├── relationships.py     # cites / follows / distinguishes / overrules /
│                        # interpreted_by / refers_to / amended_by
├── research.py          # ResearchRequest, ResearchFinding, ResearchPlan
├── analysis.py          # LegalIssue, CaseAnalysis, Argument, Timeline
├── answer.py            # DraftAnswer — the exact structure the UI renders
└── verification.py      # Claim, VerificationResult, ConfidenceBreakdown
```

`answer.py` is the contract between the Draft Agent and the research screen
in [`../design/UX_FLOWS.md`](../design/UX_FLOWS.md): lede, applicable law, key
elements, key judgments, what-needs-verification, citations, disclaimer. The
UI does not free-render prose.

`evidence.py` implements the provenance contract from
[`LEGAL_DATA_SOURCES.md`](./LEGAL_DATA_SOURCES.md) §28 — source name, URL,
document id, court, date, citation, paragraph, retrieved_at, source_type.

---

## 4. `graph/` — LangGraph orchestration

The state machine. Nodes are thin; the real work lives in `agents/`.

The root `langgraph.json` names the entrypoints so the graph can be served by
LangGraph Studio/Platform without a bespoke runner:

``` json
{
  "graphs": {
    "Legal Research": "./src/legal_ai/graph/build.py:research_graph",
    "Document Analysis": "./src/legal_ai/graph/build.py:document_graph",
    "Case Analysis": "./src/legal_ai/graph/build.py:case_graph"
  },
  "python_version": "3.11",
  "env": "./.env",
  "dependencies": ["."],
  "auth": { "path": "./src/legal_ai/security/auth.py:auth" }
}
```

Three graphs rather than one: a standalone research thread, a document
analysis run, and a case-scoped analysis that reads the whole matter. All
three share the same nodes and the same `ThreadContext`.

``` text
graph/
├── state.py             # ResearchState (TypedDict) — the graph's channel
├── build.py             # assemble & compile the StateGraph
├── nodes/
│   ├── query_analyzer.py
│   ├── context_builder.py       # produces ThreadContext
│   ├── supervisor.py            # routes to researchers, decides depth
│   ├── static_research.py
│   ├── dynamic_research.py
│   ├── active_research.py
│   ├── document.py
│   ├── analyst.py
│   ├── draft.py
│   └── verification.py
├── edges.py             # conditional routing, including the
│                        # verification → re-research loop
├── checkpoint.py        # persistence so a thread survives restarts
└── subgraphs/
    ├── research_fanout.py       # parallel static/dynamic/active
    └── verify_loop.py           # bounded re-research on unsupported claims
```

`state.py` holds the `ThreadContext` plus accumulated findings. The parallel
researchers write to separate reducer-merged channels so a fan-out does not
race.

`verify_loop.py` needs a hard iteration cap. "Research again on unsupported
claim" is correct behaviour; unbounded, it is an infinite spend.

---

## 5. `agents/` — agent definitions

``` text
agents/
├── base.py              # shared construction: model, context injection,
│                        # tool binding, structured output, retries
├── supervisor.py
├── researchers/
│   ├── static.py
│   ├── dynamic.py
│   └── active.py
├── document.py
├── case.py
├── analyst.py
├── draft.py
├── verification.py
└── prompts/
    ├── system/          # one .md per agent — version-controlled, reviewable
    ├── fragments/       # shared blocks: disclaimer rules, citation format,
    │                    # "never invent a citation", jurisdiction handling
    └── registry.py      # load + hash prompts so traces record which version ran
```

Prompts live as reviewable Markdown, not inline strings. `registry.py` hashes
them so a LangSmith trace records exactly which prompt version produced a
result — without that, an eval regression is untraceable.

`base.py` is where the §6 rule is enforced in code: an agent cannot be
constructed without a `ThreadContext`.

---

## 6. `tools/` — the stable internal contract

The tool names the agents see. These must not change when a data source is
swapped.

``` text
tools/
├── registry.py          # name → implementation binding
├── statutes.py          # search_statutes, get_statute, get_section
├── judgments.py         # search_supreme_court, search_high_court,
│                        # search_district_court, get_judgment, get_order
├── citations.py         # find_citations, find_precedent_relationships
├── knowledge.py         # search_static_knowledge, graph_lookup
├── documents.py         # tools over user-uploaded files
└── guardrails.py        # per-thread budget, rate limits, source allow-lists
```

Matches the tool contracts in `LEGAL_DATA_SOURCES.md` §27. Every tool returns
`Evidence`, never a raw string.

**Not to be confused with `scripts/recon/`** (§18) — the one-time probe
scripts used to validate source access before any of `tools/` was written.
A probe answers "what does this source look like?" once, by hand; a tool
answers "get me this data" on every agent call. Different code, different
lifetime, different location, on purpose.

---

## 7. `sources/` — adapters

Where the tools actually go. Swappable without touching an agent or prompt.

``` text
sources/
├── base.py              # LegalSource protocol + provenance enforcement
├── india_code.py
├── supreme_court.py     # official SCR/SCI search
├── ecourts.py           # eCourts services
├── bharat_courts.py     # SDK wrapper: SC + 25 HCs + district courts
├── indian_kanoon.py     # API — attribution requirements enforced here
├── archives/
│   ├── vanga_sc.py      # bulk Supreme Court corpus
│   └── vanga_hc.py      # bulk High Court corpus
├── cache.py             # respectful caching; TTL by source volatility
└── licensing.py         # per-source terms, attribution, redistribution flags
```

`licensing.py` is load-bearing, not paperwork. Indian Kanoon's terms require
prominent attribution; ILDC is CC-BY-NC and cannot back a commercial answer.
The adapter layer is the only place that knows this, and it stamps each
`Evidence` accordingly so downstream code can enforce it.

---

## 8. `retrieval/` — hybrid search

``` text
retrieval/
├── hybrid.py            # orchestrates the fan-in below
├── keyword.py           # BM25 — exact legal terminology
├── vector.py            # embeddings — semantic similarity
├── metadata.py          # act, section, court, date, judge, jurisdiction
├── graph_search.py      # relationship traversal
├── rerank.py            # cross-encoder
├── evidence_builder.py  # results → Evidence with provenance intact
├── chunking/
│   ├── statute.py       # split on section/subsection/proviso, never mid-clause
│   └── judgment.py      # preserve paragraph numbers — citations depend on them
└── embeddings.py        # provider abstraction (benchmark InLegalBERT vs general)
```

Judgment chunking must preserve paragraph numbers. The Verification Agent
cites "paragraph 42"; if chunking loses that, verification cannot work.

---

## 9. `knowledge/` — the three layers

``` text
knowledge/
├── static/
│   ├── store.py         # canonical document store
│   ├── index.py         # vector + keyword indexes
│   └── versioning.py    # trusted but versioned
├── dynamic/
│   ├── session.py       # query-scoped, short-lived results
│   └── freshness.py     # staleness rules per source
└── active/
    ├── observations.py  # signals: repeated citations, successful paths
    ├── candidates.py    # candidate knowledge, never authoritative
    ├── validation.py    # validation agent + confidence scoring
    ├── promotion.py     # gated candidate → static promotion
    └── feedback.py      # user feedback as signal only
```

`promotion.py` enforces the architecture's critical rule: frequency is not
correctness. Promotion requires validation and evidence, never usage counts
alone, and never happens automatically.

---

## 10. `graphdb/` — legal knowledge graph

``` text
graphdb/
├── client.py
├── schema.py            # entities & relationships (study NyOn first)
├── ingest.py            # write extracted triples
├── queries.py           # precedent chains, interpretation lookup
├── extraction/
│   ├── entities.py      # acts, sections, judgments, courts, judges, parties
│   ├── citations.py     # citation parsing — Indian citation formats
│   └── relations.py     # follows / distinguishes / overrules
└── validation.py        # LLM-extracted relations require verification
```

Every LLM-extracted relationship enters with extraction confidence and must
be verified before it is treated as fact.

---

## 11. `ingestion/` — corpus pipelines

``` text
ingestion/
├── pipeline.py          # shared: fetch → parse → normalize → extract → index
├── india_code/
├── supreme_court/
├── high_courts/         # Gujarat first
├── parsers/
│   ├── pdf.py
│   ├── judgment.py      # headnote, bench, paras, disposition
│   └── statute.py       # chapter, section, proviso, explanation, schedule
├── normalize.py         # citation formats, court names, dates, party names
├── dedupe.py            # the same judgment appears in several corpora
└── manifest.py          # what was ingested, when, from where, under what licence
```

---

## 12. `verification/`

``` text
verification/
├── claim_extractor.py   # split a draft into checkable claims
├── citation_checker.py  # does the case exist? is the citation right?
├── paragraph_checker.py # does the cited paragraph support the claim?
├── precedent_status.py  # overruled? distinguished? still good law?
├── temporal.py          # was this in force at the relevant time?
├── jurisdiction.py      # binding, persuasive, or irrelevant here?
└── report.py            # VerificationResult → the UI's Verified badge
```

Maps one-to-one onto what the Verification Agent must detect in
`PHASE_6_VERIFICATION_ACTIVE_LEARNING.md` §1, and produces exactly the
verification state the UI renders.

---

## 13. `observability/` — LangSmith

``` text
observability/
├── tracing.py           # LangSmith setup, run tree, thread grouping
├── metadata.py          # tag runs: thread_id, jurisdiction, prompt hashes,
│                        # context revision, source mix
├── cost.py              # tokens & tool calls per thread
└── feedback.py          # push UI feedback back onto the originating run
```

Traces are grouped by `thread_id` so an entire multi-agent research thread
reads as one tree rather than nine disconnected runs.

---

## 14. `evals/` — LangSmith datasets & evaluators

``` text
evals/
├── datasets/
│   ├── retrieval/       # question → which authorities should be retrieved
│   ├── citation/        # answer → are all citations real and correct?
│   ├── hallucination/   # questions with no good answer — must decline
│   ├── reasoning/       # end-to-end legal reasoning
│   └── documents/       # document → expected extraction
├── evaluators/
│   ├── citation_accuracy.py
│   ├── hallucination.py       # the single most important metric
│   ├── retrieval_recall.py
│   ├── groundedness.py        # is every claim supported by cited evidence?
│   └── structure.py           # does the answer match the DraftAnswer contract?
├── benchmarks/          # ILDC, NyayaAnumana — evaluation only, never production
└── run.py
```

Research datasets stay here. They are for measuring the system, never for
answering a user's question — the licensing and authority reasons are set out
in `LEGAL_DATA_SOURCES.md` §25.

---

## 15. `api/` — service layer

Deliberately thin. Business logic lives in the graph.

``` text
api/
├── main.py
├── routes/
│   ├── research.py      # start thread, stream progress, follow-up
│   ├── documents.py     # upload, analysis status
│   ├── cases.py
│   ├── knowledge.py     # statute browser, graph queries
│   └── feedback.py
├── streaming.py         # stream LangGraph node events → the UI's
│                        # "Research progress" step list
└── deps.py
```

`streaming.py` is what makes the research-progress panel real rather than
theatre: each graph node emits an event, and the UI shows the step that
actually ran.

---

## 16. Boundaries to hold

``` text
agents/     →  may import  →  tools/, context/, schemas/
tools/      →  may import  →  sources/, retrieval/, knowledge/, schemas/
sources/    →  may import  →  schemas/ only
retrieval/  →  may import  →  knowledge/, graphdb/, schemas/
api/        →  may import  →  graph/, schemas/

agents/     →  MUST NOT import  →  sources/   (that is the whole point)
sources/    →  MUST NOT import  →  agents/, tools/
```

If an agent ever imports `sources/`, the abstraction has been broken and
swapping a data provider becomes a prompt-rewriting exercise.

---

## 18. `scripts/recon/` — data-source probes (Milestone 0, complete)

Not part of the runtime package. Five standalone, one-time scripts that
sampled each Phase 1 source before any ingestion or tool code was written —
see `PHASE_1_DATA_FOUNDATION.md` §2 Milestone 0 and
`docs/DATA_RECON_FINDINGS.md` for what they found.

``` text
scripts/
└── recon/
    ├── common.py                      # ProbeReport schema, polite_get(),
    │                                  # save_sample() — shared by every probe
    ├── probe_supreme_court_bulk.py
    ├── probe_gujarat_hc_bulk.py
    ├── probe_india_code.py
    ├── probe_official_scr_search.py
    ├── probe_bharat_courts.py
    └── aggregate.py                   # renders docs/DATA_RECON_FINDINGS.md
```

Each probe imports `get_licence()` from `legal_ai.sources.licensing` (§7)
and returns a `ProbeReport`, not `Evidence` — `Evidence` is what a *tool*
returns to an agent at query time; a `ProbeReport` is what a *probe* returns
to a human, once, during recon. Do not extend a probe into a tool in place;
Phase 2's tools (Milestone 4) are new code written against the confirmed
schema, in `tools/` and `sources/`, following the boundaries in §16.

---

## 19. Build order

Follows the 7-phase roadmap in `AI_PROJECT_PROPOSAL.md` §11. Each phase has
its own plan doc; milestone numbers run continuously across all seven.

``` text
scripts/recon/                         →  Phase 1, Milestone 0  (complete)
schemas/                               →  contracts first, everything depends on them
ingestion/  +  knowledge/static/       →  Phase 1, Milestones 1–3
sources/    +  tools/                  →  Phase 2, Milestone 4
retrieval/                             →  Phase 2, Milestone 5
context/                               →  Phase 3, Milestone 6  (before any agent)
agents/researchers/  +  graph/         →  Phase 3, Milestones 7–8
agents/document, case                  →  Phase 4, Milestones 9–10
agents/analyst, draft                  →  Phase 5, Milestones 11–12
verification/  +  knowledge/active/    →  Phase 6, Milestones 13–14
evals/                                 →  Phase 7, Milestone 15
api/                                   →  once the graph is stable
```

`context/` lands before the agents because, by §6, no agent can be
constructed without a thread context to initialize from. `schemas/evidence.py`
and `sources/licensing.py` were already created in Milestone 0, ahead of
schedule, because the probes needed them too — see §18.
