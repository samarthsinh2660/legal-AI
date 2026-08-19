# Phase 2 Milestone 4 Tool Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build stable, `Evidence`-wrapped tool contracts under `src/legal_ai/tools/` that wrap the already-proven retrieval logic from Phase 1 (statute/section semantic search, judgment fetch-verify-store, and the judgment/section citation graph), matching `docs/phases/PHASE_2_QUERY_RETRIEVAL.md` §2's consolidated, backed-only tool list.

**Architecture:** Three files, one per data family (`statutes.py`, `judgments.py`, `graph.py`), each a thin wrapper — no new fetching/verification logic, just Postgres/Neo4j reads plus `Evidence` construction. A small backward-compatible extension to the shared `Evidence` schema (`document_id`, `title`, `document_type`, all optional) makes results self-describing enough for a caller to do follow-up lookups.

**Tech Stack:** Python, psycopg (Postgres), neo4j driver, pydantic (`Evidence`/`CanonicalDocument`), pytest against real docker-compose Postgres/Neo4j (no mocks — matches this project's established test style).

## Global Constraints

- Every tool function returns `Evidence` or `list[Evidence]` — never a raw `CanonicalDocument`, dict, or string. (Spec: "Tool contracts.")
- No fabrication: zero matches is an empty list / `None`, never invented content. A real infrastructure failure (DB/Neo4j down) must propagate as an exception, not get swallowed into an empty result. (Spec: "Error handling.")
- `search_judgments` returns 0 or 1 `Evidence`, never a ranked multi-result list — document this explicitly in the docstring so callers don't assume `search_statutes`-style ranking. (Spec: "judgments.py.")
- Tests use the real docker-compose Postgres/Neo4j (`docker compose up -d` must be running), not mocks — matches `tests/test_static_store.py` / `tests/test_graphdb_ingest.py`. Test fixtures clean up rows/nodes with a `test:` document_id prefix after each test.
- Do not run `git commit` as part of executing this plan — this project's standing convention is that the user commits their own work. Stop after each task's tests pass; the user commits when ready.

---

### Task 1: Extend the `Evidence` schema

**Files:**
- Modify: `src/legal_ai/schemas/evidence.py`
- Test: `tests/test_evidence.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Evidence(content, document_id=None, title=None, document_type=None, provenance, location=None)` — all three new fields optional, default `None`. Tasks 2-4 rely on being able to pass `document_id`, `title`, and `document_type` when constructing `Evidence`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence.py`:

```python
def test_evidence_carries_optional_document_identity_fields():
    source = SourceRef(
        name="India Code",
        url="https://www.indiacode.nic.in/",
        source_type="primary",
    )
    provenance = Provenance(
        source=source,
        retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        licence="Government of India",
        attribution_required=False,
    )
    evidence = Evidence(
        content="Full section text here.",
        document_id="act:2158:sec-18",
        title="Return of amount and compensation.",
        document_type="section",
        provenance=provenance,
    )

    restored = Evidence.model_validate_json(evidence.model_dump_json())

    assert restored.document_id == "act:2158:sec-18"
    assert restored.title == "Return of amount and compensation."
    assert restored.document_type == "section"


def test_evidence_document_identity_fields_default_to_none():
    source = SourceRef(name="x", url="https://example.com", source_type="research")
    provenance = Provenance(
        source=source,
        retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        licence="x",
        attribution_required=False,
    )
    evidence = Evidence(content="text", provenance=provenance)

    assert evidence.document_id is None
    assert evidence.title is None
    assert evidence.document_type is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_evidence.py -v`
Expected: FAIL — `Evidence` has no field `document_id` (pydantic `ValidationError` or `TypeError` on construction).

- [ ] **Step 3: Extend `Evidence`**

In `src/legal_ai/schemas/evidence.py`, change:

```python
class Evidence(BaseModel):
    content: str
    provenance: Provenance
    location: Optional[Location] = None
```

to:

```python
class Evidence(BaseModel):
    content: str
    document_id: Optional[str] = None
    title: Optional[str] = None
    document_type: Optional[str] = None
    provenance: Provenance
    location: Optional[Location] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_evidence.py -v`
Expected: PASS (all 4 tests in the file, including the two pre-existing ones — this confirms the extension didn't break the existing round-trip test).

---

### Task 2: `src/legal_ai/tools/statutes.py`

**Files:**
- Create: `src/legal_ai/tools/__init__.py` (empty)
- Create: `src/legal_ai/tools/statutes.py`
- Test: `tests/test_tools_statutes.py`

**Interfaces:**
- Consumes: `Evidence` (Task 1); `find_similar(conn, query_embedding, limit)` and `get_document(conn, document_id)` from `legal_ai.knowledge.static.store`; `embed(text)` from `legal_ai.knowledge.static.embeddings`; `get_connection()`, `ensure_schema(conn)` from `legal_ai.knowledge.static.db`.
- Produces:
  - `search_statutes(query: str, limit: int = 5) -> list[Evidence]`
  - `get_statute(act_id: str) -> Evidence | None`
  - `get_section(act_id: str, section_number: str) -> Evidence | None`

  Tasks 3-4 don't depend on this module's internals, only that it exists as a sibling under `src/legal_ai/tools/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_statutes.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.statutes import get_section, get_statute, search_statutes


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _doc(doc_id: str, doc_type: str, title: str, text: str, act_id: str | None = None) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
        act_id=act_id,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_get_statute_returns_evidence_with_identity_fields(conn):
    act = _doc("test:act-1", "act", "Test Act, 2026", "An Act to test things.")
    upsert_document(conn, act, embedding=_sparse_vector((0, 1.0)))

    evidence = get_statute("test:act-1")

    assert evidence is not None
    assert evidence.document_id == "test:act-1"
    assert evidence.title == "Test Act, 2026"
    assert evidence.document_type == "act"
    assert evidence.content == "An Act to test things."


def test_get_statute_returns_none_for_missing_act():
    assert get_statute("test:does-not-exist") is None


def test_get_section_builds_compound_document_id(conn):
    section = _doc("test:act-1:sec-3", "section", "Section 3", "Prior registration.", act_id="test:act-1")
    upsert_document(conn, section, embedding=_sparse_vector((1, 1.0)))

    evidence = get_section("test:act-1", "3")

    assert evidence is not None
    assert evidence.document_id == "test:act-1:sec-3"
    assert evidence.content == "Prior registration."


def test_search_statutes_excludes_non_statute_document_types(conn):
    act = _doc("test:act-2", "act", "Searchable Act", "possession disputes remedy text")
    judgment = _doc("test:j-1", "judgment", "Some Judgment", "possession disputes remedy text")
    upsert_document(conn, act, embedding=_sparse_vector((2, 1.0)))
    upsert_document(conn, judgment, embedding=_sparse_vector((2, 1.0)))

    results = search_statutes("possession disputes remedy", limit=10)

    result_ids = {e.document_id for e in results}
    assert "test:act-2" in result_ids
    assert "test:j-1" not in result_ids
```

Note: this test does **not** take `conn` as an argument in `get_statute`/`search_statutes`/`get_section` calls — those functions open their own connection internally (matching how `dynamic_search.py`'s `_check_db` does it), so the fixture's `conn` is only used to seed data and clean up.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tools_statutes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.tools'`.

- [ ] **Step 3: Implement `statutes.py`**

Create `src/legal_ai/tools/__init__.py` (empty file).

Create `src/legal_ai/tools/statutes.py`:

```python
"""Query tools for Acts and Sections — Phase 2 Milestone 4.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.
Thin wrappers over the Phase 1 static store — no new fetching or
verification logic here, just Evidence construction.
"""

from __future__ import annotations

from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import find_similar, get_document
from legal_ai.schemas.evidence import Evidence

_STATUTE_TYPES = {"act", "section"}

# find_similar has no document_type filter, so over-fetch and filter in
# Python — cheap at this corpus size, and avoids changing a function
# several other callers already depend on for an unfiltered result.
_OVERFETCH_FACTOR = 5


def _to_evidence(doc: CanonicalDocument) -> Evidence:
    return Evidence(
        content=doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        provenance=doc.provenance,
    )


def search_statutes(query: str, limit: int = 5) -> list[Evidence]:
    conn = get_connection()
    try:
        candidates = find_similar(conn, embed(query), limit=limit * _OVERFETCH_FACTOR)
    finally:
        conn.close()

    matches = [doc for doc, _distance in candidates if doc.document_type in _STATUTE_TYPES]
    return [_to_evidence(doc) for doc in matches[:limit]]


def get_statute(act_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, act_id)
    finally:
        conn.close()
    return _to_evidence(doc) if doc is not None else None


def get_section(act_id: str, section_number: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, f"{act_id}:sec-{section_number}")
    finally:
        conn.close()
    return _to_evidence(doc) if doc is not None else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_tools_statutes.py -v`
Expected: PASS (all 4 tests).

---

### Task 3: `src/legal_ai/tools/judgments.py`

**Files:**
- Create: `src/legal_ai/tools/judgments.py`
- Test: `tests/test_tools_judgments.py`

**Interfaces:**
- Consumes: `Evidence` (Task 1); `search_judgment(query, year=None) -> JudgmentSearchResult` from `legal_ai.ingestion.judgments.dynamic_search` (`JudgmentSearchResult` has `.found: bool`, `.source: str`, `.document: CanonicalDocument | None`, `.verified: bool | None`); `store_judgment(document) -> bool` from `legal_ai.ingestion.judgments.store`; `get_document(conn, document_id)` from `legal_ai.knowledge.static.store`; `get_connection()` from `legal_ai.knowledge.static.db`.
- Produces:
  - `search_judgments(query: str, year: int | tuple[int, int] | None = None, store: bool = True) -> list[Evidence]`
  - `get_judgment(document_id: str) -> Evidence | None`

  Task 4 doesn't depend on this module.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_judgments.py`. This test avoids real network calls (no Bharat Courts / Indian Kanoon hits) by seeding a judgment directly into Postgres first, so `search_judgments` finds it via the DB short-circuit path in `dynamic_search._check_db` (title word-overlap, no network) — the same technique already proven live in this project (`scripts/search_judgment.py` re-run against an already-stored judgment).

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.judgments import get_judgment, search_judgments


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _judgment(doc_id: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="judgment",
        title=title,
        court="Test Court",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="Indian Kanoon", url="https://indiankanoon.org/doc/1/", source_type="research"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Public judicial record",
            attribution_required=True,
        ),
        ingested_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_get_judgment_returns_evidence(conn):
    judgment = _judgment("test:j-1", "Alpha Traders vs Beta Logistics", "Full judgment text about alpha traders.")
    upsert_document(conn, judgment, embedding=_sparse_vector((3, 1.0)))

    evidence = get_judgment("test:j-1")

    assert evidence is not None
    assert evidence.document_id == "test:j-1"
    assert evidence.document_type == "judgment"
    assert evidence.content == "Full judgment text about alpha traders."


def test_get_judgment_returns_none_for_missing_judgment():
    assert get_judgment("test:does-not-exist") is None


def test_search_judgments_finds_existing_db_match_without_storing_again(conn):
    judgment = _judgment(
        "test:j-2", "Gamma Housing Society vs Delta Builders", "Full judgment text about gamma housing society."
    )
    upsert_document(conn, judgment, embedding=_sparse_vector((4, 1.0)))

    results = search_judgments("Gamma Housing Society Delta Builders")

    assert len(results) == 1
    assert results[0].document_id == "test:j-2"
    assert results[0].content == "Full judgment text about gamma housing society."


def test_search_judgments_returns_empty_list_for_no_match(conn):
    # A query with no real source behind it and no DB match — this would
    # otherwise fall through to live network sources; searching for
    # nonsense text keeps this test offline in practice for CI, but if a
    # network call does happen, an empty/0 result is still the correct,
    # honest outcome (no fabrication).
    results = search_judgments("Zzqvxk Nonexistent Fabricated Case Ptyltd", year=1900)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tools_judgments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.tools.judgments'`.

- [ ] **Step 3: Implement `judgments.py`**

```python
"""Query tools for Supreme Court / High Court judgments — Phase 2 Milestone 4.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.
search_judgments wraps the same fetch-verify-store flow already proven in
scripts/search_judgment.py's CLI — it returns 0 or 1 Evidence, never a
ranked multi-result list, since the underlying flow only ever surfaces
one best candidate per source (DB word-overlap match, or first archive/
Indian Kanoon match). Do not treat this like search_statutes' ranked
semantic search.
"""

from __future__ import annotations

from legal_ai.ingestion.judgments.dynamic_search import search_judgment
from legal_ai.ingestion.judgments.store import store_judgment
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Evidence


def _to_evidence(doc: CanonicalDocument) -> Evidence:
    return Evidence(
        content=doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        provenance=doc.provenance,
    )


def search_judgments(
    query: str, year: int | tuple[int, int] | None = None, store: bool = True
) -> list[Evidence]:
    result = search_judgment(query, year=year)
    if not result.found or result.document is None:
        return []

    if store and result.source != "database" and result.verified:
        store_judgment(result.document)

    return [_to_evidence(result.document)]


def get_judgment(document_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, document_id)
    finally:
        conn.close()
    return _to_evidence(doc) if doc is not None else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_tools_judgments.py -v`
Expected: PASS (all 4 tests). Note: `test_search_judgments_returns_empty_list_for_no_match` may take longer than the others (it can fall through to a live network search) — this matches the existing behavior of `search_judgment` itself and is not a new cost introduced by this task.

---

### Task 4: `src/legal_ai/tools/graph.py`

**Files:**
- Create: `src/legal_ai/tools/graph.py`
- Test: `tests/test_tools_graph.py`

**Interfaces:**
- Consumes: `Evidence` (Task 1); `get_driver()` from `legal_ai.graphdb.client`; `write_act_section(driver, act, section)` and `write_judgment(driver, judgment, pg_conn=None)` from `legal_ai.graphdb.ingest`; `get_document(conn, document_id)` from `legal_ai.knowledge.static.store`; `get_connection()`, `ensure_schema(conn)` from `legal_ai.knowledge.static.db`; `upsert_document(conn, doc, embedding=None)` from `legal_ai.knowledge.static.store`.
- Produces:
  - `find_citations(judgment_id: str) -> list[Evidence]`
  - `find_section_citations(section_id: str) -> list[Evidence]`
  - `find_judgment_sections(judgment_id: str) -> list[Evidence]`

  This is the last task in the plan — nothing downstream depends on it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_graph.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.graph import find_citations, find_judgment_sections, find_section_citations


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _doc(doc_id: str, doc_type: str, title: str, text: str, act_id: str | None = None, court: str | None = None) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
        act_id=act_id,
        court=court,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="Test Source", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Test",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


@pytest.fixture
def driver():
    d = get_driver()
    yield d
    with d.session() as session:
        session.run("MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n")
    d.close()


def test_find_citations_returns_cited_judgment_as_evidence(conn, driver):
    citing_text = "This case follows (2019) 8 SCC 729 closely."
    cited = _doc("test:j-cited", "judgment", "Cited Case", "the cited judgment full text", court="Test Court")
    citing = _doc("test:j-citing", "judgment", "Citing Case", citing_text, court="Test Court")
    cited = cited.model_copy(update={"citation": "(2019) 8 SCC 729"})
    upsert_document(conn, cited, embedding=_sparse_vector((5, 1.0)))
    upsert_document(conn, citing, embedding=_sparse_vector((6, 1.0)))
    write_judgment(driver, cited)
    write_judgment(driver, citing)

    results = find_citations("test:j-citing")

    assert len(results) == 1
    assert results[0].document_id == "test:j-cited"
    assert results[0].content == "the cited judgment full text"


def test_find_citations_returns_empty_list_when_no_citations(conn, driver):
    judgment = _doc("test:j-lonely", "judgment", "Lonely Case", "no citations here", court="Test Court")
    upsert_document(conn, judgment, embedding=_sparse_vector((7, 1.0)))
    write_judgment(driver, judgment)

    assert find_citations("test:j-lonely") == []


def test_find_section_citations_and_find_judgment_sections_are_symmetric(conn, driver):
    act = _doc("test:act-3", "act", "Test Act, 2026", "An Act to test things.")
    section = _doc("test:act-3:sec-9", "section", "Section 9", "Section nine body text.", act_id="test:act-3")
    judgment_text = "The Authority under Section 9 of the Test Act, 2026 held..."
    judgment = _doc("test:j-sec", "judgment", "Section-Citing Case", judgment_text, court="Test Court")

    upsert_document(conn, act, embedding=_sparse_vector((8, 1.0)))
    upsert_document(conn, section, embedding=_sparse_vector((9, 1.0)))
    upsert_document(conn, judgment, embedding=_sparse_vector((10, 1.0)))
    write_act_section(driver, act, section)
    write_judgment(driver, judgment, pg_conn=conn)

    citing_judgments = find_section_citations("test:act-3:sec-9")
    assert len(citing_judgments) == 1
    assert citing_judgments[0].document_id == "test:j-sec"

    cited_sections = find_judgment_sections("test:j-sec")
    assert len(cited_sections) == 1
    assert cited_sections[0].document_id == "test:act-3:sec-9"
    assert cited_sections[0].content == "Section nine body text."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tools_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.tools.graph'`.

- [ ] **Step 3: Implement `graph.py`**

```python
"""Query tools over the judgment/statute citation graph — Phase 2 Milestone 4.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.
Every match here comes from Neo4j (document_id/title only), so each one
needs a Postgres round-trip via get_document to build Evidence.content
with real full text -- the graph never stores full text itself.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Evidence


def _to_evidence(doc: CanonicalDocument) -> Evidence:
    return Evidence(
        content=doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        provenance=doc.provenance,
    )


def _resolve_all(document_ids: list[str]) -> list[Evidence]:
    if not document_ids:
        return []
    conn = get_connection()
    try:
        docs = [get_document(conn, doc_id) for doc_id in document_ids]
    finally:
        conn.close()
    return [_to_evidence(doc) for doc in docs if doc is not None]


def find_citations(judgment_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:Judgment {document_id: $id})-[:CITES]->(b:Judgment)
                RETURN b.document_id AS document_id
                """,
                id=judgment_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_section_citations(section_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[:CITES_SECTION]->(s:Section {document_id: $id})
                RETURN j.document_id AS document_id
                """,
                id=section_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_judgment_sections(judgment_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment {document_id: $id})-[:CITES_SECTION]->(s:Section)
                RETURN s.document_id AS document_id
                """,
                id=judgment_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_tools_graph.py -v`
Expected: PASS (all 3 tests).

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — all pre-existing tests plus every test added in Tasks 1-4.

---

## Self-Review Notes

**Spec coverage:** every function named in the spec's "Tool contracts" section (`search_statutes`, `get_statute`, `get_section`, `search_judgments`, `get_judgment`, `find_citations`, `find_section_citations`, `find_judgment_sections`) has a task and a real implementation above. The `Evidence` schema extension (spec's "Evidence schema" section) is Task 1. The spec's explicitly out-of-scope items (`get_order`, `search_high_court`, `search_static_knowledge`, `graph_lookup`, Milestone 5 hybrid retrieval) have no task here, matching the spec.

**Type consistency:** `Evidence(content, document_id, title, document_type, provenance, location)` from Task 1 is used identically across Tasks 2-4's `_to_evidence` helpers. `search_judgment`/`store_judgment`/`JudgmentSearchResult` field names in Task 3 match `src/legal_ai/ingestion/judgments/dynamic_search.py` and `store.py` as they exist today (verified during spec research this session, not assumed).

**No placeholders:** every step has real code, not a description of code.
