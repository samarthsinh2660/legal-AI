# Phase 2 Milestone 5 — Hybrid Retrieval: Core Fan-In Engine — Design

**Status:** Approved by user 2026-08-19.

## Scope

Milestone 5 as specified in `docs/PROJECT_STRUCTURE.md` §8 covers more than
one implementation cycle's worth of work: the fan-in engine, an embeddings
provider abstraction (with InLegalBERT benchmarking), a chunking pipeline,
and a cross-encoder reranker. Per the user's decision to build the full
architecture, it is **decomposed into four sub-projects**, each with its own
spec → plan → implementation cycle:

1. **Core fan-in engine** — this document.
2. Embeddings provider abstraction + InLegalBERT benchmarking (`embeddings.py`).
3. Chunking pipeline (`chunking/statute.py`, `chunking/judgment.py`).
4. Cross-encoder reranking (`rerank.py`).

Order is dependency-driven: everything else either feeds into (2) or builds
on top of (1). Reranking cannot be built before there is a fan-in whose
output it reranks.

**This spec covers sub-project 1 only.**

## Why this ordering, grounded in the real corpus

Measured 2026-08-19 against the live database (36,467 documents):

| document_type | count | min chars | avg chars | max chars |
|---|---|---|---|---|
| act | 860 | 169 | 7,284 | 169,224 |
| section | 35,601 | 0 | 1,032 | 40,078 |
| judgment | 6 | 3,652 | 33,918 | 122,197 |

Two facts this establishes:

- **Chunking is genuinely needed for judgments** (avg 34k chars, max 122k):
  compressing a 122k-character judgment into a single 384-dimension vector
  loses most of its content, so vector recall on judgments is weak today.
  Sections (avg ~1k chars) are fine unchunked. This justifies sub-project 3
  rather than assuming it away — but it is a separate cycle, because
  chunking changes what gets stored and indexed, and is better designed
  against a working fan-in than in the abstract.
- **The table currently has no index except the primary key.** Vector
  search is a sequential scan over 36k rows today, and no full-text index
  exists at all. Both are addressed here.

## Architecture

Four independent signal sources fan in, are fused by rank, optionally
expanded through the knowledge graph, and are assembled into `Evidence`:

``` text
                        query + optional filters
                                   |
        +----------------+---------+---------+----------------+
        |                |                   |                |
        v                v                   v                |
    keyword.py       vector.py         metadata.py            |
  (Postgres FTS)   (pgvector cosine)  (exact structured       |
        |                |             lookup)                |
        +----------------+---------+---------+----------------+
                                   |
                                   v
                        Reciprocal Rank Fusion
                                   |
                                   v
                       graph_search.py (expand seeds
                       one hop via CONTAINS / CITES /
                       CITES_SECTION, then re-fuse)
                                   |
                                   v
                        evidence_builder.py
                                   |
                                   v
                            list[Evidence]
```

### `metadata.py` — filters *and* a real signal

Serves two distinct purposes, which is why it is one module:

1. **`MetadataFilters`** — a dataclass (`document_type`, `court`, `act_id`,
   `decision_date_from`, `decision_date_to`) that compiles to a SQL `WHERE`
   fragment plus parameters. Consumed by `keyword.py` and `vector.py` so
   filtering happens in the database, not in Python after the fact.
2. **`search_metadata(query, ...)`** — a genuine third signal: exact,
   structured lookup. A query like "Section 18 of RERA" should resolve
   *exactly* to `act:2158:sec-18`, which is neither a keyword match nor a
   fuzzy vector match. This reuses the already-built and already-tested
   `extract_section_references()` (`ingestion/statute_citations.py`) and
   `find_act_by_name()` (`knowledge/static/store.py`) rather than writing
   new parsing logic.

### `keyword.py` — Postgres FTS, named honestly

`PROJECT_STRUCTURE.md` §8 says "BM25". True BM25 requires either an
external engine (Elasticsearch/OpenSearch) or the ParadeDB `pg_search`
extension. Native Postgres full-text search ranks with `ts_rank_cd`, which
is TF-IDF-family, **not** BM25.

Decision (user-approved): use native Postgres FTS and **call it keyword
search, not BM25**, in code, docstrings, and documentation. Rationale: no
new infrastructure, and having exact-terminology keyword search at all
matters far more here than the specific ranking formula. Mislabelling it
BM25 would be the kind of inaccuracy this project has consistently avoided
elsewhere.

Implementation: a `STORED` generated `tsvector` column over
`title || ' ' || full_text`, a GIN index on it, `websearch_to_tsquery` for
parsing user input (handles quoted phrases and `or`/`-` naturally), and
`ts_rank_cd` for ranking.

### `vector.py`

Wraps the existing `embed()` + pgvector cosine distance already proven in
`find_similar`, adding `MetadataFilters` support. `find_similar` itself is
left untouched — several callers depend on its current unfiltered
behaviour.

### `graph_search.py` — expansion, not standalone search

Takes the fused top-K document ids as **seeds** and expands one hop over
the existing, already-tested edges: `CONTAINS` (Act→Section),
`CITES` (Judgment→Judgment), `CITES_SECTION` (Judgment→Section), plus the
inverse of each. A document reached from more distinct seeds ranks higher.

This is deliberately expansion rather than a standalone signal: the graph
has no text to match a raw query against, so it can only meaningfully
answer "what else is connected to what we already found."

### Fusion: Reciprocal Rank Fusion

The three signals produce mutually incomparable scores — cosine *distance*
(lower is better), `ts_rank_cd` (higher is better, unbounded), and exact
match (boolean). Normalising these against each other would be fragile and
arbitrary.

RRF fuses by **rank** instead: `score(d) = Σ 1 / (k + rank_i(d))` over each
signal *i* that returned *d*, with `k = 60` (the standard constant from the
original RRF paper). A document found by several signals outranks one found
by a single signal, with no score normalisation needed.

### `evidence_builder.py`

Converts `CanonicalDocument` → `Evidence` with provenance intact, reusing
the `_to_evidence` shape already used in `tools/statutes.py`,
`tools/judgments.py`, and `tools/graph.py`. Those three private copies are
consolidated here and imported back, removing the existing triplication —
a targeted cleanup of code this milestone directly builds on, not
unrelated refactoring.

Result order carries the ranking. No score field is added to `Evidence`:
the returned list is already ordered, and adding an unused field now would
be speculative. (Sub-project 4, reranking, may revisit this if it needs to
surface scores; that is its decision to make, not this one's.)

## Schema changes

Both additive and idempotent, in `knowledge/static/db.py`'s `ensure_schema`:

1. `ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector
   GENERATED ALWAYS AS (to_tsvector('english', coalesce(title,'') || ' ' ||
   coalesce(full_text,''))) STORED;` plus
   `CREATE INDEX IF NOT EXISTS ... USING GIN (search_vector);`
2. `CREATE INDEX IF NOT EXISTS documents_embedding_hnsw ON documents USING
   hnsw (embedding vector_cosine_ops);`

The HNSW index requires a fixed-dimension column, but `embedding` is
currently declared as bare `VECTOR`. Verified 2026-08-19 that **every**
non-null embedding in the live database is exactly 384 dimensions (one row
has a NULL embedding — the single known empty-text section), so
`ALTER TABLE documents ALTER COLUMN embedding TYPE vector(384)` is safe.
The implementation plan re-checks this at run time and skips the index
rather than failing if the precondition does not hold, so a future
differently-dimensioned corpus degrades to today's sequential scan instead
of erroring.

## Error handling

Consistent with the rest of the project:

- No results from a signal → that signal contributes nothing to the fusion;
  it is not an error, and the other signals still produce a result.
- No results from any signal → empty list. Never fabricated.
- A real infrastructure failure (Postgres or Neo4j unreachable) propagates
  as an exception rather than being swallowed into an empty list — the
  same reasoning applied in Milestone 4, and the exact failure mode that
  `bharat-courts` issues #25/#26 demonstrated the danger of.

## Testing

Real Postgres and Neo4j via docker-compose, no mocks, matching the
established style of `tests/test_tools_*.py` and `tests/test_static_store.py`.
Fixtures seed `test:`-prefixed rows and clean them up afterwards.

Note for test authors, learned the hard way in Milestone 4: the live
database contains the full ~36k-document real corpus, so a test asserting
that a seeded fixture appears in ranked results must make that fixture
genuinely rank — seed it with a real `embed()` of distinctive text rather
than a synthetic sparse vector, which will not rank against real data.

Per signal: that it returns real matches, respects `MetadataFilters`, and
returns empty (not an error) when nothing matches. For fusion: that a
document found by two signals outranks one found by a single signal. For
graph expansion: that a connected document is pulled in from a seed.

## Out of scope for this spec

- Sub-projects 2, 3, and 4 (embeddings abstraction, chunking, reranking).
- `search_related_judgments` — the multi-result live judgment search
  deferred from Milestone 4. It fetches *new* documents from external
  sources; this engine ranks documents *already stored*. Related but
  genuinely separate, and best designed after the fan-in exists.
- Any agent, query interface, or answer generation (Phase 3+).
