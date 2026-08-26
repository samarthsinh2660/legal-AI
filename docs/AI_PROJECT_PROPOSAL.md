# AI-First Indian Legal Intelligence Platform

## 1. Vision

Build an AI-first legal intelligence platform for Indian law that can
research legal questions, understand case documents, reason over
statutes and precedents, and produce grounded answers with verifiable
citations.

The project is intentionally **AI-first**. UI, product backend,
authentication, billing, and other application concerns are outside the
current scope.

The core principle is:

> The AI should reason over legal evidence rather than invent legal
> knowledge.

------------------------------------------------------------------------

## 2. Core Architecture

The AI system is divided into three knowledge/research flows:

1.  **Static Knowledge** --- trusted, pre-built legal knowledge that is
    useful across cases.
2.  **Dynamic Research** --- query-time research over current/relevant
    legal sources.
3.  **Active Knowledge** --- evidence and feedback accumulated from
    system usage and progressively validated into the knowledge base.

These three flows feed an **Analyst Agent**, followed by a **Draft
Agent** and a **Verification Agent**.

``` text
                         USER QUERY
                              |
                              v
                       SUPERVISOR AGENT
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
      STATIC              DYNAMIC              ACTIVE
    RESEARCHER           RESEARCHER           RESEARCHER
          |                   |                   |
          |                   |                   v
          |                   |            Candidate Knowledge
          |                   |                   |
          |                   |             Validation
          |                   |                   |
          +-------------------+-------------------+
                              |
                              v
                       ANALYST AGENT
                              |
                    +---------+---------+
                    |                   |
                    v                   v
              CASE ANALYSIS       KNOWLEDGE UPDATE
                    |                   |
                    +---------+---------+
                              |
                              v
                         DRAFT AGENT
                              |
                              v
                    VERIFICATION AGENT
                              |
                              v
                        FINAL ANSWER
```

------------------------------------------------------------------------

## 3. Static Knowledge

Static knowledge is the trusted foundation of the system.

Initial sources:

-   Constitution of India
-   India Code legislation
-   Acts and sections
-   Rules and regulations
-   High-confidence Supreme Court judgments
-   Important High Court judgments
-   Legal entities and relationships
-   Verified precedent/citation relationships

This knowledge is pre-processed into:

-   Structured legal documents
-   Vector indexes
-   A legal knowledge graph
-   Citation and provenance metadata

The static layer should change through controlled ingestion and
validation rather than arbitrary user feedback.

------------------------------------------------------------------------

## 4. Dynamic Research

Dynamic research handles information that is relevant to the current
question but is not necessarily already present in the static knowledge
graph.

The Dynamic Researcher can call tools such as:

``` text
search_legislation()
search_supreme_court()
search_high_court()
search_district_court()
search_judgments()
get_judgment()
find_citations()
```

Potential sources include:

-   Official court repositories
-   India Code
-   Court search infrastructure
-   Bharat Courts
-   Indian Kanoon where permitted
-   Other verified legal sources

The dynamic layer is responsible for finding the best evidence for the
current query.

------------------------------------------------------------------------

## 5. Active Knowledge

The active layer is the system's learning/evidence loop.

Examples of signals:

-   Frequently retrieved judgments
-   Repeatedly useful citations
-   User corrections
-   User feedback
-   Repeated legal relationships
-   Frequently co-occurring sections and judgments
-   Verification outcomes
-   Successful research paths

However:

> User feedback must never automatically become authoritative legal
> knowledge.

Instead:

``` text
User / Agent Interaction
        |
        v
Observed Evidence
        |
        v
Candidate Knowledge
        |
        v
Validation
        |
        v
Confidence / Provenance
        |
   +----+----+
   |         |
Approved   Rejected
   |
   v
Knowledge Graph
```

The active layer therefore improves the system over time without
compromising the authority of the static layer.

------------------------------------------------------------------------

## 6. Shared Thread Context

Every sub-agent needs the same baseline understanding of the matter before
it can do useful work: what jurisdiction applies, what the user actually
asked, which documents are in play, what has already been established.

Rebuilding that understanding inside each agent is wasteful and unsafe. The
same question gets re-analyzed several times, each agent may reach a
slightly different reading of the facts, and token cost multiplies with the
number of agents.

Instead, the context is built **once per research thread** and passed to
every agent that the Supervisor spawns.

### Principle

> A sub-agent is never initialized cold. It receives the thread context,
> plus only the task-specific instruction that distinguishes it from its
> siblings.

### Flow

``` text
                     USER QUERY
                          |
                          v
                  THREAD CONTEXT BUILDER
                          |
              (build once, reuse for the
               whole research thread)
                          |
                          v
                  ThreadContext object
                          |
        +-----------------+-----------------+
        |                 |                 |
        v                 v                 v
     STATIC            DYNAMIC            ACTIVE
   RESEARCHER        RESEARCHER        RESEARCHER
        |                 |                 |
        +-----------------+-----------------+
                          |
                          v
                  ANALYST / DRAFT /
                    VERIFICATION
                (same context object)
```

### What the thread context holds

``` text
thread_id
created_at

query
  original_text
  normalized_question
  legal_issues[]
  legal_domain
  question_type          (research / document / case / drafting)

jurisdiction
  country
  state
  courts[]
  applicable_from        (temporal validity cutoff)

case
  case_id                (null for a one-off question)
  parties[]
  timeline_summary
  established_facts[]
  assumptions[]
  open_questions[]

documents[]
  document_id
  title
  type
  extracted_summary

established_findings[]   (facts + authorities already accepted
                          earlier in this same thread)

constraints
  language
  answer_depth           (quick / standard / deep)
  allowed_sources[]
  attribution_required[]

budget
  max_tool_calls
  max_tokens
  deadline
```

### Rules

1.  The context is **built once** per thread, not per agent.
2.  Sub-agents receive it **read-only**. They cannot mutate shared state
    directly.
3.  A sub-agent returns findings; only the Supervisor or Analyst may
    promote a finding into `established_findings`.
4.  Follow-up questions in the same thread **reuse and extend** the existing
    context rather than rebuilding it.
5.  Anything promoted into `established_findings` keeps its provenance, so
    the Verification Agent can still trace it back to a source.
6.  The context is versioned. Each promotion produces a new revision, which
    makes a research thread reproducible and auditable after the fact.
7.  If the user changes jurisdiction, uploads a new document, or corrects a
    fact, the context is **revised** — and any cached findings that depended
    on the changed field are invalidated.

### Why this matters

``` text
Without shared context          With shared context
---------------------           -------------------
each agent re-derives           derived once
the question

inconsistent readings           one canonical reading
of the same facts

N x context tokens              1 x context tokens

no audit trail of what          versioned, reproducible
the agent "knew"                thread state
```

This is what makes multi-agent research consistent rather than merely
parallel.

------------------------------------------------------------------------

## 7. Agents

### Supervisor Agent

Understands the query and decides which research flows and sub-agents
are required.

It also owns the shared thread context (§6): it builds the context once,
passes it to every sub-agent it spawns, and is the only component — along
with the Analyst — permitted to promote a returned finding into
`established_findings`.

### Static Research Agent

Queries the trusted legal knowledge graph and static indexes.

### Dynamic Research Agent

Performs live/query-specific legal research.

### Active Research Agent

Retrieves validated historical observations, feedback-derived
candidates, and learned research patterns.

### Document Agent

Understands uploaded legal documents.

Responsibilities:

-   Extract facts
-   Extract dates
-   Identify parties
-   Identify clauses
-   Identify sections
-   Identify legal issues
-   Detect contradictions
-   Produce structured document evidence

### Case Agent / Analyst

Combines case documents with research results.

Responsibilities:

-   Build case timeline
-   Identify issues
-   Compare arguments
-   Connect facts to law
-   Analyze precedents
-   Identify missing information
-   Build a structured legal analysis

### Draft Agent

Converts verified analysis into the requested response format.

### Verification Agent

Checks:

-   Citations
-   Legal claims
-   Source existence
-   Relevant paragraphs
-   Precedent relationships
-   Temporal validity
-   Jurisdiction
-   Conflicting authorities

Unsupported claims should trigger additional research rather than being
presented confidently.

------------------------------------------------------------------------

## 8. Retrieval Architecture

The system should use hybrid retrieval rather than relying only on
embeddings.

``` text
                       QUERY
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Keyword     Vector      Metadata
           Search     Search       Search
             |           |           |
             +-----------+-----------+
                         |
                         v
                    Graph Search
                         |
                         v
                      Reranker
                         |
                         v
                  Evidence Builder
```

Retrieval should consider:

-   Semantic similarity
-   Exact legal terminology
-   Act and section
-   Court
-   Date
-   Jurisdiction
-   Case citation
-   Legal entities
-   Graph relationships

------------------------------------------------------------------------

## 9. Knowledge Graph

The graph should represent legal entities and relationships such as:

``` text
Act -> contains -> Section
Section -> interpreted_by -> Judgment
Judgment -> cites -> Judgment
Judgment -> follows -> Judgment
Judgment -> distinguishes -> Judgment
Judgment -> overrules -> Judgment
Judgment -> refers_to -> Section
Act -> amended_by -> Amendment
Section -> cross_references -> Section
```

The initial graph is global for the AI system.

Per-user knowledge graphs are intentionally deferred because they add
unnecessary complexity at this stage.

------------------------------------------------------------------------

## 10. Legal Reasoning Example

User:

> Someone is occupying my land without permission. How can I prove
> ownership and what legal options may be available?

The system should:

``` text
Question
  |
  v
Identify jurisdiction + facts + legal issues
  |
  +--> Static: ownership / property law
  |
  +--> Dynamic: recent relevant judgments
  |
  +--> Active: historically useful research patterns
  |
  v
Analyst
  |
  +--> ownership evidence
  +--> possession issues
  +--> relevant statutes
  +--> limitation/procedure
  +--> relevant precedents
  |
  v
Draft
  |
  v
Verification
  |
  v
Grounded answer + citations
```

The system should distinguish legal information from individualized
legal advice and clearly identify assumptions or missing facts.

------------------------------------------------------------------------

## 11. Development Roadmap

Seven phases, each with one job and one deliverable. Earlier drafts of this
roadmap bundled everything -- data, retrieval, agents, drafting,
verification -- into one oversized "Phase 1." That made the phase
undefined and un-shippable on its own. Each phase below now has its own
plan document, and produces working, testable output before the next one
starts.

``` text
PHASE 1   Data Foundation
    |
PHASE 2   Query & Retrieval
    |
PHASE 3   Research Agent System
    |
PHASE 4   Document + Case Intelligence
    |
PHASE 5   Legal Analysis + Drafting
    |
PHASE 6   Verification + Currency
    |
PHASE 7   Advanced GraphRAG & Intelligence
```

| Phase | Plan doc | Main question | Deliverable |
|---|---|---|---|
| 1. Data Foundation | `PHASE_1_DATA_FOUNDATION.md` | Do we have reliable legal knowledge? | A clean, searchable, versioned Indian legal data foundation |
| 2. Query & Retrieval | `PHASE_2_QUERY_RETRIEVAL.md` | Can we find the right knowledge? | Given a question, we reliably retrieve the correct documents/sections/cases |
| 3. Research Agents | `PHASE_3_RESEARCH_AGENTS.md` | Can AI research intelligently? | AI performs legal research, not just search |
| 4. Case Intelligence | `PHASE_4_CASE_DOCUMENT_INTELLIGENCE.md` | Can AI understand *this user's case*? | AI understands both Indian law and the user's particular case |
| 5. Analysis/Drafting | `PHASE_5_ANALYSIS_DRAFTING.md` | Can AI reason over the evidence? | Evidence + case facts become structured legal analysis |
| 6. Verification/Currency | `PHASE_6_VERIFICATION_ACTIVE_LEARNING.md` | Can we make it trustworthy, and keep it trustworthy as the law changes? | Claims checked against what the cited section says, not just that it exists; amendments surfaced against what cites them |
| 7. GraphRAG/Advanced | `PHASE_7_ADVANCED_GRAPHRAG.md` | Can we make the whole system significantly smarter? | A measurably smarter, benchmarked system, on a foundation already proven trustworthy |

Team assignment falls out of this cleanly: Phase 1 is data engineering, not
agent work. Phase 2 is retrieval. Phase 3 onward is agents. No phase
requires the next one to exist to be considered done.

------------------------------------------------------------------------

## 12. Guiding Principles

1.  Primary legal sources are preferred.
2.  Every important legal claim should have evidence.
3.  The LLM is not the source of truth.
4.  Static knowledge is trusted but versioned.
5.  Dynamic research handles current/query-specific information.
6.  Active knowledge is learned but must be validated.
7.  User feedback never directly overrides authoritative law.
8.  Per-user knowledge graphs are deferred.
9.  Retrieval quality comes before complex agent orchestration.
10. Verification is a first-class component, not an afterthought.
