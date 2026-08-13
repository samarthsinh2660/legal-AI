# Pramāṇa AI — Indian Legal Intelligence

An AI-first legal research platform for Indian law. It researches legal
questions, reads case documents, reasons over statutes and precedents, and
produces grounded answers with verifiable citations.

**Pramāṇa** (प्रमाण) is Sanskrit for *evidence* or *valid means of knowledge* —
the question of how you are entitled to claim you know something. That is the
discipline the whole system enforces:

> The AI reasons over legal evidence rather than inventing legal knowledge.

Status: **design and architecture**. The specification and UI prototype are
complete; implementation has not started.

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
├── docs/       architecture, data strategy, source catalogue, code layout
└── design/     brand, design system, and the interactive UI prototype
```

### `docs/` — architecture

| Document | What it covers |
|---|---|
| [`AI_PROJECT_PROPOSAL.md`](./docs/AI_PROJECT_PROPOSAL.md) | Core architecture: the three layers, shared thread context (§6), every agent, retrieval, knowledge graph, roadmap, guiding principles |
| [`DATA_LAYER_ARCHITECTURE.md`](./docs/DATA_LAYER_ARCHITECTURE.md) | Static / dynamic / active in depth — pipelines, provenance, confidence model, promotion rules |
| [`LEGAL_DATA_SOURCES.md`](./docs/LEGAL_DATA_SOURCES.md) | Every candidate Indian legal data source, its licensing, and the tool contracts that abstract them |
| [`PHASE_1_AI_RESEARCH_PLAN.md`](./docs/PHASE_1_AI_RESEARCH_PLAN.md) | Phase 1 scope, agent responsibilities, 11 milestones, success criteria |
| [`PROJECT_STRUCTURE.md`](./docs/PROJECT_STRUCTURE.md) | The code layout: LangGraph / LangChain / LangSmith, module boundaries, build order |

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

| Phase | Focus |
|---|---|
| **1** | Legal research and case analysis — the trustworthy pipeline |
| 2 | Knowledge graph expansion and GraphRAG |
| 3 | Multi-agent research with parallel and iterative loops |
| 4 | Legal drafting — notices, petitions, research memos |
| 5 | Active learning and validated knowledge promotion |
| 6 | Advanced reasoning: conflicting precedent, temporal validity, benchmarks |

Phase 1 succeeds when the system can take a real Indian legal question and
identify the domain, find the relevant legislation and judgments, explain why
each authority matters, preserve provenance, cite accurately, **detect
insufficient evidence**, and avoid unsupported claims — repeatably.

The goal is not the most autonomous agent. It is a trustworthy legal research
pipeline that later phases can safely make more agentic.

---

## Disclaimer

This is a research and engineering project. Nothing it produces is legal
advice, and every worked example in the documentation and prototype is
illustrative. Verify against the primary source and consult a qualified
advocate before acting on anything.
