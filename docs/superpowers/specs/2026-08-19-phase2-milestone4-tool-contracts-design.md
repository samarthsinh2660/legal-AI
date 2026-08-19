# Phase 2 Milestone 4 — Search Tool Contracts — Design

**Status:** Approved by user, spec written 2026-08-19.

## Decision

Builds the stable, `Evidence`-wrapped tool contracts `docs/phases/PHASE_2_QUERY_RETRIEVAL.md`
§2 calls for — **a consolidated, backed-only set**, not the full "fuller tool
surface" list verbatim. That doc actually names two different, partially
conflicting tool surfaces in the same section; several entries in the
"fuller" one (`get_order`, `search_static_knowledge`, `graph_lookup`,
`search_high_court` as distinct from `search_supreme_court`) have no real
backing logic today, and one (`get_order`) needs District Courts, which
was just deliberately deferred (see
`docs/superpowers/specs/2026-08-17-dynamic-judgment-search-design.md`'s
"District Courts" section). Building stubs for those now would mean
inventing behavior with nothing real behind it — this project's discipline
throughout has been to build only what real, verified data supports.

No new data-fetching logic here. Every tool wraps something that's already
been built and proven earlier in this project: `find_similar`/`get_document`
(India Code), `dynamic_search.search_judgment` + `store.store_judgment`
(SC/HC), and the `CITES_SECTION`/`CITES` graph queries (currently living
only as inline Cypher in CLI scripts, one of which — `CITES`/`find_citations`
— only exists on the `harness-test` branch today and needs rebuilding fresh
on `main`).

## Tool contracts

Three modules under `src/legal_ai/tools/`, matching the file-per-responsibility
pattern the project already uses (`ingestion/judgments/dynamic_search.py`
vs `store.py`, etc.):

### `src/legal_ai/tools/statutes.py`

```python
def search_statutes(query: str, limit: int = 5) -> list[Evidence]
def get_statute(act_id: str) -> Evidence | None
def get_section(act_id: str, section_number: str) -> Evidence | None
```

- `search_statutes`: `find_similar` over documents where `document_type`
  in `{"act", "section"}`, ranked by distance (existing behavior of
  `find_similar` — no new ranking logic).
- `get_statute`/`get_section`: `get_document(act_id)` /
  `get_document(f"{act_id}:sec-{section_number}")`.

### `src/legal_ai/tools/judgments.py`

```python
def search_judgments(query: str, year: int | tuple[int, int] | None = None, store: bool = True) -> list[Evidence]
def get_judgment(document_id: str) -> Evidence | None
```

- `search_judgments` wraps `dynamic_search.search_judgment(query, year)`,
  then `store.store_judgment(doc)` when `store=True` and the result is a
  fresh (non-DB) verified find — exactly what `scripts/search_judgment.py`'s
  CLI already does. Returns **0 or 1** `Evidence`, never a ranked list —
  the underlying fetch/verify/store flow only ever surfaces one best
  candidate per source (first archive match, first Kanoon match), so
  claiming a ranked multi-result search here would misrepresent what's
  actually happening. This is documented in the function's docstring, not
  just this spec, so a future caller can't assume `search_statutes`-style
  ranking.
- `get_judgment`: `get_document(document_id)`.

### `src/legal_ai/tools/graph.py`

```python
def find_citations(judgment_id: str) -> list[Evidence]
def find_section_citations(section_id: str) -> list[Evidence]
def find_judgment_sections(judgment_id: str) -> list[Evidence]
```

- `find_citations`: judgments a judgment cites (`CITES` edges) — this
  Cypher query currently only exists on the `harness-test` branch
  (`scripts/legal_search.py`'s `cmd_citations`); rebuilt fresh here on
  `main`, sourced from a real Postgres `get_document` lookup per matched
  `document_id` (the graph only stores `document_id`/`title`/`citation`,
  not full text — each match needs a Postgres round-trip to build a real
  `Evidence.content`).
- `find_section_citations`: judgments citing a given Section
  (`CITES_SECTION` edges) — same logic as `section_case_lookup.py`'s
  `judgments-for`, wrapped as `Evidence`.
- `find_judgment_sections`: Sections a given judgment cites — same logic
  as `section_case_lookup.py`'s `sections-in`, wrapped as `Evidence`.
  Unresolved (`dangling_section_citations`) references are **not**
  included as `Evidence` (there's no real document behind them) — exposed
  instead as a documented empty-content caveat in the docstring, matching
  this project's non-fabrication discipline.

## Evidence schema — one small, justified extension

Checked: `Evidence` (`src/legal_ai/schemas/evidence.py`) is currently
constructed nowhere in production code — only in its own test
(`tests/test_evidence.py`). It's safe to extend without breaking anything.

As written today it only carries `content` + `provenance` + `location` —
no `document_id`, `title`, or `document_type`. That's insufficient for the
stated purpose: a caller doing `search_statutes("possession disputes")`
needs to know *which* document each result came from, to follow up with
`get_section` or to display something more useful than raw text. Adding:

```python
class Evidence(BaseModel):
    content: str
    document_id: Optional[str] = None
    title: Optional[str] = None
    document_type: Optional[str] = None
    provenance: Provenance
    location: Optional[Location] = None
```

All new fields optional, so the existing test and schema round-trip
behavior are unaffected. `content` for `get_*`/`search_judgments` results
is the document's full text; for `search_statutes` it's also full text for
now (no snippet/highlighting logic exists yet — that's real Milestone 5
hybrid-retrieval territory, not this milestone).

## Error handling

No fabrication, ever — matches every other piece of this project:

- Zero matches → empty list (`search_*`) or `None` (`get_*`, `find_*` for
  a specific edge that doesn't resolve). Never an exception for "not
  found," since that's an expected, normal outcome for these tools.
- A real upstream failure (DB down, Neo4j down, Bharat Courts archive
  timeout) → let the exception propagate. Swallowing it into an empty
  list would make a real infrastructure failure indistinguishable from a
  genuine "no results," which is exactly the kind of ambiguity
  `bharat-courts` issues #25/#26 (filed this session) showed the danger
  of.

## Testing

Unit tests per module (`tests/test_tools_statutes.py`,
`test_tools_judgments.py`, `test_tools_graph.py`), following this
project's existing test style (`tests/test_static_store.py`,
`tests/test_graphdb_ingest.py`) — real Postgres/Neo4j via the docker-compose
services, not mocks (matches this project's established practice: prior
session work explicitly avoided mocking the DB layer). Each test seeds one
or two real-shaped documents, calls the tool function, and asserts on the
returned `Evidence`.

## Out of scope for this doc

- `get_order`, `search_high_court` (separate from `search_supreme_court`),
  `search_static_knowledge`, `graph_lookup` — no real backing logic exists
  yet; revisit if/when District Courts is unblocked or a real query needs
  them.
- Milestone 5 (hybrid keyword+vector+metadata+graph retrieval, reranking,
  snippet extraction) — this milestone's tools are direct wraps of
  existing single-signal lookups, not a fan-in retrieval pipeline.
- Re-running the real-estate harness questions against these new tools
  (explicitly planned as the next step after this ships, per user).
