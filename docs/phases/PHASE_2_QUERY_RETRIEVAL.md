# Phase 2 --- Query & Retrieval Layer

## Objective

Make the Phase 1 data foundation actually searchable.

> Given a question, can we reliably retrieve the correct legal
> documents/sections/cases?

**Still no multi-agent system.** This phase builds tools and a retrieval
pipeline, not agents that decide when to call them -- that's Phase 3.

------------------------------------------------------------------------

## 1. Retrieval Pipeline

``` text
User Query
    |
    v
Query Processor
    |
    v
Hybrid Retrieval
    +-- Keyword
    +-- Vector
    +-- Metadata
    +-- Graph
    |
    v
Reranker
    |
    v
Evidence
```

Matches the hybrid retrieval architecture in `AI_PROJECT_PROPOSAL.md` §8:
retrieval should consider semantic similarity, exact legal terminology,
Act/section, court, date, jurisdiction, citation, legal entities, and graph
relationships -- not vector search alone.

------------------------------------------------------------------------

## 2. Search Tools

The stable, agent-facing tool contracts -- built against the real schema
Milestone 0 confirmed, not the assumed structure from earlier drafts. Every
tool returns `Evidence` (`src/legal_ai/schemas/evidence.py`), never a raw
string.

``` text
search_india_code()
search_supreme_court()
search_gujarat_hc()
search_judgments()
search_sections()
graph_search()
```

For the two bulk sources (Supreme Court, Gujarat HC), these tools query
**our own ingested store** from Phase 1 -- not a live source. For India
Code and Bharat Courts, a tool may call the live source per query, since
that data is current/query-specific by nature. See
`DATA_LAYER_ARCHITECTURE.md` §6--8 for the static/dynamic distinction this
maps onto.

Fuller tool surface, matching `LEGAL_DATA_SOURCES.md` §27:

``` text
search_statutes(query, jurisdiction?)
get_statute(act_id)
get_section(act_id, section_id)

search_supreme_court(query, date_range?, judge?, citation?)
search_high_court(query, court?, date_range?, judge?)
get_judgment(document_id)
get_order(document_id)

find_citations(document_id)
find_precedent_relationships(document_id)

search_static_knowledge(query)
graph_lookup(entity_or_relationship)
```

------------------------------------------------------------------------

## 3. Milestones

### Milestone 4 (complete)

Court search tools -- the tool contracts above, implemented in
`src/legal_ai/tools/` and `src/legal_ai/sources/` per
`PROJECT_STRUCTURE.md` §6--7.

Built 2026-08-19, per
`docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md`
and `docs/superpowers/plans/2026-08-19-phase2-milestone4-tool-contracts.md`:
a consolidated, backed-only subset of the tool surface above --
`search_statutes`, `get_statute`, `get_section`
(`src/legal_ai/tools/statutes.py`); `search_judgments`, `get_judgment`
(`src/legal_ai/tools/judgments.py`); `find_citations`,
`find_section_citations`, `find_judgment_sections`
(`src/legal_ai/tools/graph.py`). Every tool returns `Evidence`
(`src/legal_ai/schemas/evidence.py`, extended with optional
`document_id`/`title`/`document_type` fields to make results
self-describing). `get_order`, `search_high_court` (as distinct from
`search_supreme_court`), `search_static_knowledge`, and `graph_lookup`
were deliberately left out -- no real backing logic exists for them yet
(`get_order` needs District Courts, deferred -- see Milestone 2's note in
`PHASE_1_DATA_FOUNDATION.md`). 11 tests, all passing, real Postgres/Neo4j
(no mocks).

### Milestone 5 (not started)

Hybrid legal retrieval -- keyword + vector + metadata + graph fan-in,
reranking, and evidence-building (`src/legal_ai/retrieval/` per
`PROJECT_STRUCTURE.md` §8). Sits on top of Milestone 4's tools rather than
replacing them.

------------------------------------------------------------------------

## 4. Deliverable

> Given a question, we can reliably retrieve the correct legal
> documents/sections/cases.

------------------------------------------------------------------------

## 5. Explicitly not in this phase

``` text
Supervisor / Research Agent    -> Phase 3
Document Agent / Case Agent    -> Phase 4
Analyst Agent / Draft Agent    -> Phase 5
Verification Agent             -> Phase 6
GraphRAG / precedent graph     -> Phase 7
```
