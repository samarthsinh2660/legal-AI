# Pramāṇa AI — Indian Legal Intelligence

An AI-first legal research platform for Indian law. It researches legal
questions, reads case documents, reasons over statutes and precedents, and
produces grounded answers with verifiable citations.

**Pramāṇa** (प्रमाण) is Sanskrit for *evidence* or *valid means of knowledge* —
the question of how you are entitled to claim you know something. That is the
discipline the whole system enforces:

> The AI reasons over legal evidence rather than inventing legal knowledge.

---

## The problem

A general-purpose model asked an Indian legal question will produce fluent,
confident text containing invented case names, misquoted sections, and
authorities that were overruled a decade ago. For legal work that is worse
than useless.

The response here is architectural rather than prompt-level: retrieve from
primary sources, keep provenance attached to every piece of evidence, and
verify each generated claim against its cited source before a user ever sees
it. Anything unsupported triggers more research instead of a confident guess.

---

## How it works

Three knowledge layers with different authority, feeding a multi-agent
research pipeline.

``` text
                         USER QUERY
                              |
                              v
                       SUPERVISOR AGENT
                              |
                    THREAD CONTEXT (built once)
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
       STATIC              DYNAMIC              ACTIVE
     RESEARCHER          RESEARCHER          RESEARCHER
    trusted corpus      live court /        usage-derived
    + knowledge graph   statute search      candidates
          |                   |                   |
          +-------------------+-------------------+
                              |
                              v
                        ANALYST AGENT
                              |
                              v
                         DRAFT AGENT
                              |
                              v
                     VERIFICATION AGENT
                    (claims + citations)
                              |
                              v
                     GROUNDED ANSWER
```

| Layer | Purpose | Authority |
|---|---|---|
| **Static** | Curated, versioned foundation — Constitution, India Code, settled Supreme Court authority | High |
| **Dynamic** | Retrieved live for the current question from court and legislation sources | Depends on the source |
| **Active** | Learned from usage — repeated citations, successful research paths, user feedback | **Never authoritative until validated** |

The third layer is the one most systems get wrong. A citation is not correct
because it is popular; promotion from candidate to trusted knowledge requires
validation and evidence, never usage counts.

### Shared thread context

Every sub-agent is initialized from a single `ThreadContext` — the normalized
question, jurisdiction, case facts, active documents and findings already
established in this thread. It is built **once** and passed read-only, so
agents never re-derive the same understanding, never disagree about the
facts, and never multiply context tokens by the number of agents.

---

## Research vs. Case

The two primary objects in the product:

``` text
RESEARCH   "What does Indian law say about X?"
           One question. Can stand alone.

CASE       "What does Indian law mean for THIS matter,
            given these documents, facts, history and research?"
           A persistent workspace. Contains many research sessions.
```

``` text
Case: Patel v. Shah
  ├── Research: "Can adverse possession apply?"
  ├── Research: "What proves ownership?"
  ├── Research: "Relevant Gujarat HC judgments"
  └── Research: "Limitation period"
```

Attaching a thread to a case seeds its context with that matter's parties,
timeline and established findings — which is what lets the Case Agent answer
questions the Research Agent cannot: *"Which facts in our documents support
the ownership claim?"*

---

## Repository layout

``` text
legal-AI/
├── src/legal_ai/   the system
│   ├── agents/     supervisor, analyst, draft, verifier, treatment, conflict
│   ├── retrieval/  hybrid search, reranking, authority ranking, good-law
│   ├── ingestion/  scrapers, parsers, citation and bench extraction
│   ├── knowledge/  the canonical Postgres store, chunks, embeddings
│   ├── graphdb/    Neo4j: CONTAINS, CITES, CITES_SECTION, DECIDED_BY
│   ├── graph/      the LangGraph pipeline that wires the agents together
│   └── verification/  the groundedness funnel
├── tests/          715 tests, foldered to mirror src/legal_ai/
│   └── common/     tests of the seams BETWEEN domains, not within one
├── evals/          measurement harnesses and their frozen datasets
├── scripts/        ingest, backfill and rebuild passes over the corpus
├── docs/           architecture, data strategy, source catalogue, phase plans
└── design/         brand, design system, and the interactive UI prototype
```

Tests sit beside the package they cover. A test lands in `tests/common/`
only when its assertions are about how two subsystems agree — the graph
holding together, an answer body staying identical across verification
modes — rather than testing one subsystem with another as scaffolding. Each
names the domains it spans in its first lines.

### What is actually in the corpus

``` text
statute sections   35,601        judgments        12,337
acts                  860        chunks (embedded) 332,025

graph edges   CONTAINS 35,603   DECIDED_BY 12,320
              CITES_SECTION 6,349   CITES 2,705
```

`CITES` is judgment-to-judgment precedent. It is small for a structural
reason, not a bug: only Supreme Court judgments carry a citation of their
own in the archives, so High Court judgments cannot be cited by anything.
See `PHASE_7_ADVANCED_GRAPHRAG.md` §2.

### `docs/` — architecture

| Document | What it covers |
|---|---|
| [`AI_PROJECT_PROPOSAL.md`](./docs/AI_PROJECT_PROPOSAL.md) | Core architecture: the three layers, shared thread context (§6), every agent, retrieval, knowledge graph, roadmap, guiding principles |
| [`DATA_LAYER_ARCHITECTURE.md`](./docs/DATA_LAYER_ARCHITECTURE.md) | Static / dynamic / active in depth — pipelines, provenance, confidence model, promotion rules |
| [`LEGAL_DATA_SOURCES.md`](./docs/LEGAL_DATA_SOURCES.md) | Every candidate Indian legal data source, its licensing, and the tool contracts that abstract them |
| [`PROJECT_STRUCTURE.md`](./docs/PROJECT_STRUCTURE.md) | The code layout: LangGraph / LangChain / LangSmith, module boundaries, build order |

**Phase plans** — each phase has one job, one deliverable, its own doc (see `AI_PROJECT_PROPOSAL.md` §11 for the full roadmap table):

| Phase | Doc | Deliverable | State |
|---|---|---|---|
| 1. Data Foundation | [`PHASE_1_DATA_FOUNDATION.md`](./docs/phases/PHASE_1_DATA_FOUNDATION.md) | A clean, searchable, versioned Indian legal data foundation | done |
| 2. Query & Retrieval | [`PHASE_2_QUERY_RETRIEVAL.md`](./docs/phases/PHASE_2_QUERY_RETRIEVAL.md) | Reliable retrieval of the correct documents/sections/cases | done |
| 3. Research Agents | [`PHASE_3_RESEARCH_AGENTS.md`](./docs/phases/PHASE_3_RESEARCH_AGENTS.md) | AI performs legal research, not just search | done |
| 4. Case Intelligence | [`PHASE_4_CASE_DOCUMENT_INTELLIGENCE.md`](./docs/phases/PHASE_4_CASE_DOCUMENT_INTELLIGENCE.md) | AI understands the user's own case, not just the law | done |
| 5. Analysis/Drafting | [`PHASE_5_ANALYSIS_DRAFTING.md`](./docs/phases/PHASE_5_ANALYSIS_DRAFTING.md) | Evidence + case facts become structured legal analysis | done |
| 6. Verification/Active | [`PHASE_6_VERIFICATION_ACTIVE_LEARNING.md`](./docs/phases/PHASE_6_VERIFICATION_ACTIVE_LEARNING.md) | Every claim checked; usage never becomes law on its own | done, M14 currency skipped |
| 7. GraphRAG/Advanced | [`PHASE_7_ADVANCED_GRAPHRAG.md`](./docs/phases/PHASE_7_ADVANCED_GRAPHRAG.md) | A measurably smarter system, on a proven-trustworthy base | built; M15 benchmark open |

### `design/` — product

| Document | What it covers |
|---|---|
| [`pramana-ui.html`](./design/pramana-ui.html) | **The interactive prototype.** Open it in a browser — self-contained, no build, no network |
| [`BRAND.md`](./design/BRAND.md) | Name, mark, personality, voice, disclaimer posture |
| [`DESIGN_SYSTEM.md`](./design/DESIGN_SYSTEM.md) | Colour, typography, spacing, elevation, components |
| [`UX_FLOWS.md`](./design/UX_FLOWS.md) | Information architecture and every screen |

```bash
xdg-open design/pramana-ui.html   # Linux
open design/pramana-ui.html       # macOS
```

Eleven screens: landing, dashboard, research workspace, document analysis,
cases index, case workspace, judgment search, legislation browser, knowledge
graph, saved, history — plus a live design-system reference.

---

## Data sources

Authority and technical convenience are kept separate:

| Tier | Sources | Role |
|---|---|---|
| **Primary** | India Code, Supreme Court, High Courts, eCourts | The legal authority |
| **Programmatic** | Bharat Courts, open AWS court archives, Indian Kanoon API | Access and bulk infrastructure — not new authority |
| **Research** | ILDC, NyayaAnumana, InLegalBERT, IMLJD | Benchmarking and evaluation only |

Licensing is enforced in code, not documentation: the source adapter layer
stamps each piece of evidence with its terms, so an attribution requirement
or a non-commercial restriction travels with the data.

---

## Guiding principles

1. Primary legal sources are preferred.
2. Every important legal claim should have evidence.
3. **The LLM is not the source of truth.**
4. Static knowledge is trusted but versioned.
5. Dynamic research handles current, query-specific information.
6. Active knowledge is learned but must be validated.
7. **User feedback never directly overrides authoritative law.**
8. Per-user knowledge graphs are deferred.
9. Retrieval quality comes before complex agent orchestration.
10. **Verification is a first-class component, not an afterthought.**

---

## Roadmap

Seven phases, each with one job and one deliverable — see the table in
`AI_PROJECT_PROPOSAL.md` §11, or the phase-doc table above. **All seven are
implemented and merged.**

### What is measured

Numbers, not impressions. Each is reproducible from `evals/`.

| What | Result | Harness |
|---|---|---|
| Claim verification, exact verdict | 0.92–0.94 over 50 frozen claims | `evals.run_verification` |
| Treatment classification | 0.92 agreement with the law reporter, 150 cases | `evals.run_treatment` |
| Retrieval | MRR 0.333, recall@10 68% over 50 questions | `evals.run` |
| Bench extraction | 97% of Supreme Court judgments parsed | — |

### What is honestly not done

- **Milestone 15**, the end-to-end research benchmark, is not started.
- **Authority ranking is unscored.** It returns the right landmarks by
  inspection, but no judgment-retrieval eval set exists.
- **No overruling has ever been found**, so `is_still_good_law` has never
  returned its warning on real data. It reports *"no negative treatment
  among the N judgments citing it that we hold"* — a statement about this
  corpus, never a clearance.
- **Currency (M14) was deliberately skipped.** Nothing re-scrapes, so an
  amended section is served as current with no notice.
- **Conflict detection is built but blind**, pending High Court depth.

The goal is not the most autonomous agent. It is a trustworthy legal research
pipeline that later phases can safely make more agentic.

---

## Disclaimer

This is a research and engineering project. Nothing it produces is legal
advice, and every worked example in the documentation and prototype is
illustrative. Verify against the primary source and consult a qualified
advocate before acting on anything.
