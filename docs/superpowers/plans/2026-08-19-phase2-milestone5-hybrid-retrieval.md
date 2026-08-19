# Hybrid Retrieval Core Fan-In Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core hybrid retrieval fan-in engine in `src/legal_ai/retrieval/` — keyword, vector, and metadata signals fused by Reciprocal Rank Fusion, expanded through the knowledge graph, and assembled into `Evidence`.

**Architecture:** Each signal is an independent function returning `list[tuple[document_id, score]]` — deliberately *not* full documents, so fusion operates on cheap ids and only the surviving top-K get their full text fetched once at the end. `hybrid.py` orchestrates: run signals → RRF-fuse by rank → expand via graph → re-fuse → build `Evidence`.

**Tech Stack:** Python, psycopg (Postgres 16 + pgvector), Postgres native full-text search (`tsvector`/GIN/`ts_rank_cd`), neo4j driver, pydantic, pytest against real docker-compose services.

## Global Constraints

- Every signal function returns `list[tuple[str, float]]` — `(document_id, score)`, ordered best-first. Only `evidence_builder` and `hybrid_search` deal in full documents.
- Signal functions take an already-open `conn` (and/or `driver`) as their first parameter. Only `hybrid_search` opens and closes connections, so one query uses one connection, not four.
- Call it **keyword search, never BM25**, in code, docstrings, and docs. Native Postgres FTS ranks with `ts_rank_cd` (TF-IDF-family), which is not BM25. (Spec: "keyword.py — Postgres FTS, named honestly.")
- No fabrication: zero matches is an empty list, never invented content. A real infrastructure failure (Postgres/Neo4j unreachable) propagates as an exception rather than being swallowed into an empty list.
- `retrieval/` must **not** import from `tools/`. `tools/` imports `to_evidence` from `retrieval/evidence_builder.py` (Task 6); a `retrieval/ → tools/` import would create a circular import. `graph_search.py` therefore writes its own Cypher rather than importing `tools/graph.py`.
- Tests use the real docker-compose Postgres/Neo4j (`docker-compose up -d` must be running), never mocks. Fixtures seed `test:`-prefixed rows/nodes and clean them up afterwards.
- **Test-authoring lesson from Milestone 4:** the live database holds the full ~36k-document real corpus. A test asserting a seeded fixture appears in *ranked* results must make it genuinely rank — seed with a real `embed()` of distinctive nonsense text (e.g. `"zzqvxk flibbertigibbet"`), never a synthetic sparse vector.
- Do not run `git commit` — this project's standing convention is that the user commits their own work. Stop after each task's tests pass.

---

### Task 1: Retrieval schema — tsvector column, GIN index, HNSW index

**Files:**
- Modify: `src/legal_ai/knowledge/static/db.py`
- Test: `tests/test_retrieval_schema.py`

**Interfaces:**
- Consumes: `get_connection()`, `ensure_schema()`, `EMBEDDING_DIM` (all existing in `db.py`).
- Produces: `ensure_retrieval_schema(conn: psycopg.Connection) -> dict[str, bool]` with keys `"search_vector_column"`, `"keyword_index"`, `"vector_index"`. Tasks 3 and 4 depend on the `search_vector` column and its GIN index existing.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_schema.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_retrieval_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(doc_id: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="act",
        title=title,
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


def test_ensure_retrieval_schema_creates_column_and_indexes(conn):
    result = ensure_retrieval_schema(conn)

    assert result["search_vector_column"] is True
    assert result["keyword_index"] is True

    with conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'documents'")
        index_names = {row[0] for row in cur.fetchall()}
    assert "documents_search_vector_gin" in index_names


def test_ensure_retrieval_schema_is_idempotent(conn):
    ensure_retrieval_schema(conn)
    second = ensure_retrieval_schema(conn)

    assert second["search_vector_column"] is True
    assert second["keyword_index"] is True


def test_search_vector_column_is_populated_for_new_rows(conn):
    ensure_retrieval_schema(conn)
    upsert_document(conn, _doc("test:fts-1", "Ordinary Title", "zzqvxk flibbertigibbet provision"))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT search_vector @@ websearch_to_tsquery('english', 'flibbertigibbet')
            FROM documents WHERE document_id = 'test:fts-1'
            """
        )
        matched = cur.fetchone()[0]
    assert matched is True


def test_search_vector_column_indexes_the_title_too(conn):
    ensure_retrieval_schema(conn)
    upsert_document(conn, _doc("test:fts-2", "Zzqvxk Distinctive Heading", "ordinary body text"))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT search_vector @@ websearch_to_tsquery('english', 'Zzqvxk')
            FROM documents WHERE document_id = 'test:fts-2'
            """
        )
        matched = cur.fetchone()[0]
    assert matched is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_retrieval_schema' from 'legal_ai.knowledge.static.db'`.

- [ ] **Step 3: Implement `ensure_retrieval_schema`**

Append to `src/legal_ai/knowledge/static/db.py`:

```python
def ensure_retrieval_schema(conn: psycopg.Connection) -> dict[str, bool]:
    """Additive, idempotent indexes for hybrid retrieval (Phase 2 Milestone 5).

    Separate from ensure_schema() because these are retrieval concerns, not
    the canonical document contract -- Phase 1 ingestion works without them.

    Returns which structures are in place. "vector_index" can legitimately
    come back False: an HNSW index needs a fixed-dimension vector column,
    and if the corpus ever holds mixed embedding dimensions the index is
    skipped rather than raising, degrading to the sequential scan that was
    the behaviour before this function existed.
    """
    conn.execute(
        """
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(title, '') || ' ' || coalesce(full_text, ''))
        ) STORED
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS documents_search_vector_gin
        ON documents USING GIN (search_vector)
        """
    )
    conn.commit()

    vector_index = _ensure_vector_index(conn)
    return {
        "search_vector_column": True,
        "keyword_index": True,
        "vector_index": vector_index,
    }


def _ensure_vector_index(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_indexes WHERE tablename = 'documents' "
            "AND indexname = 'documents_embedding_hnsw'"
        )
        if cur.fetchone() is not None:
            return True

        # pgvector encodes a vector column's declared dimension in atttypmod;
        # a bare VECTOR (no dimension) is -1, and HNSW cannot index that.
        cur.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'documents'::regclass AND attname = 'embedding'"
        )
        typmod = cur.fetchone()[0]

        if typmod < 0:
            cur.execute(
                "SELECT DISTINCT vector_dims(embedding) FROM documents WHERE embedding IS NOT NULL"
            )
            dims = [row[0] for row in cur.fetchall()]
            if dims not in ([EMBEDDING_DIM], []):
                return False
            cur.execute(
                f"ALTER TABLE documents ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})"
            )

    conn.commit()
    conn.execute(
        "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )
    conn.commit()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_schema.py -v`
Expected: PASS (4 tests). The first run adds a generated column and builds two indexes over ~36k real rows — expect it to take up to a minute. Later runs are fast.

- [ ] **Step 5: Confirm the indexes really exist**

Run:
```bash
docker exec legal-ai-postgres psql -U legal_ai -d legal_ai -c "\di"
```
Expected: `documents_search_vector_gin` and `documents_embedding_hnsw` both listed alongside `documents_pkey`.

---

### Task 2: `metadata.py` — filters and exact structured lookup

**Files:**
- Create: `src/legal_ai/retrieval/__init__.py` (empty)
- Create: `src/legal_ai/retrieval/metadata.py`
- Test: `tests/test_retrieval_metadata.py`

**Interfaces:**
- Consumes: `extract_section_references(text) -> list[SectionReference]` (from `legal_ai.ingestion.statute_citations`; each has `.section_number` and `.act_name`); `find_act_by_name(conn, act_name) -> str | None` and `get_document(conn, document_id)` (from `legal_ai.knowledge.static.store`).
- Produces:
  - `MetadataFilters` — frozen dataclass with fields `document_type: str | None`, `court: str | None`, `act_id: str | None`, `decision_date_from: date | None`, `decision_date_to: date | None`, and method `to_sql() -> tuple[str, list]` returning a SQL fragment beginning with `" AND "` (or `""`) plus its parameters.
  - `search_metadata(conn, query: str, limit: int = 10, filters: MetadataFilters | None = None) -> list[tuple[str, float]]`

  Tasks 3, 4 and 7 use `MetadataFilters`; Task 7 uses `search_metadata`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_metadata.py`:

```python
from datetime import date, datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.metadata import MetadataFilters, search_metadata
from legal_ai.schemas.evidence import Provenance, SourceRef


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


def test_empty_filters_produce_no_sql():
    fragment, params = MetadataFilters().to_sql()
    assert fragment == ""
    assert params == []


def test_filters_compile_to_sql_fragment_and_params():
    fragment, params = MetadataFilters(document_type="section", court="Supreme Court of India").to_sql()
    assert "document_type = %s" in fragment
    assert "court = %s" in fragment
    assert fragment.startswith(" AND ")
    assert params == ["section", "Supreme Court of India"]


def test_date_range_filters_compile_to_sql():
    fragment, params = MetadataFilters(
        decision_date_from=date(2020, 1, 1), decision_date_to=date(2021, 12, 31)
    ).to_sql()
    assert "decision_date >= %s" in fragment
    assert "decision_date <= %s" in fragment
    assert params == [date(2020, 1, 1), date(2021, 12, 31)]


def test_search_metadata_resolves_a_real_statutory_reference(conn):
    # Section 18 of RERA is real, already-ingested data (act:2158:sec-18).
    results = search_metadata(
        conn, "What does Section 18 of the Real Estate (Regulation and Development) Act, 2016 say?"
    )

    assert ("act:2158:sec-18", 1.0) in results


def test_search_metadata_returns_empty_for_a_query_with_no_statutory_reference(conn):
    assert search_metadata(conn, "what are my rights when a builder delays possession") == []


def test_search_metadata_respects_document_type_filter(conn):
    results = search_metadata(
        conn,
        "Section 18 of the Real Estate (Regulation and Development) Act, 2016",
        filters=MetadataFilters(document_type="judgment"),
    )
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.retrieval'`.

- [ ] **Step 3: Implement `metadata.py`**

Create `src/legal_ai/retrieval/__init__.py` (empty file).

Create `src/legal_ai/retrieval/metadata.py`:

```python
"""Structured metadata: shared SQL filters, plus exact-lookup as a signal.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

Two responsibilities, deliberately in one module because they are the same
concern seen from two sides: MetadataFilters constrains *other* signals in
SQL, and search_metadata is itself a signal -- an exact structured lookup
that resolves "Section 18 of the ... Act, 2016" straight to a document id,
which neither fuzzy vector similarity nor keyword matching does reliably.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg

from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.knowledge.static.store import find_act_by_name, get_document

# An exact structured match is either right or absent -- there is no
# meaningful gradation, so every hit scores the same. Rank, not score, is
# what the fusion in hybrid.py actually consumes.
EXACT_MATCH_SCORE = 1.0


@dataclass(frozen=True)
class MetadataFilters:
    document_type: str | None = None
    court: str | None = None
    act_id: str | None = None
    decision_date_from: date | None = None
    decision_date_to: date | None = None

    def to_sql(self) -> tuple[str, list]:
        """SQL fragment (starting with ' AND ', or empty) plus its params.

        Filtering happens in the database rather than in Python afterwards,
        so a signal's LIMIT applies to rows that already passed the filter.
        """
        clauses: list[str] = []
        params: list = []

        if self.document_type is not None:
            clauses.append("document_type = %s")
            params.append(self.document_type)
        if self.court is not None:
            clauses.append("court = %s")
            params.append(self.court)
        if self.act_id is not None:
            clauses.append("act_id = %s")
            params.append(self.act_id)
        if self.decision_date_from is not None:
            clauses.append("decision_date >= %s")
            params.append(self.decision_date_from)
        if self.decision_date_to is not None:
            clauses.append("decision_date <= %s")
            params.append(self.decision_date_to)

        if not clauses:
            return "", []
        return " AND " + " AND ".join(clauses), params


def _passes_filters(doc, filters: MetadataFilters | None) -> bool:
    if filters is None:
        return True
    if filters.document_type is not None and doc.document_type != filters.document_type:
        return False
    if filters.court is not None and doc.court != filters.court:
        return False
    if filters.act_id is not None and doc.act_id != filters.act_id:
        return False
    if filters.decision_date_from is not None and (
        doc.decision_date is None or doc.decision_date < filters.decision_date_from
    ):
        return False
    if filters.decision_date_to is not None and (
        doc.decision_date is None or doc.decision_date > filters.decision_date_to
    ):
        return False
    return True


def search_metadata(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
) -> list[tuple[str, float]]:
    """Resolve statutory references in `query` to exact document ids.

    Returns [] when the query contains no recognisable statutory reference
    -- that is the normal case for a plain natural-language question, not a
    failure, and the other signals carry the query instead.
    """
    results: list[tuple[str, float]] = []
    seen: set[str] = set()

    for reference in extract_section_references(query):
        act_id = find_act_by_name(conn, reference.act_name)
        if act_id is None:
            continue
        document_id = f"{act_id}:sec-{reference.section_number}"
        if document_id in seen:
            continue
        doc = get_document(conn, document_id)
        if doc is None or not _passes_filters(doc, filters):
            continue
        seen.add(document_id)
        results.append((document_id, EXACT_MATCH_SCORE))
        if len(results) >= limit:
            break

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_metadata.py -v`
Expected: PASS (6 tests).

---

### Task 3: `keyword.py` — Postgres full-text search

**Files:**
- Create: `src/legal_ai/retrieval/keyword.py`
- Test: `tests/test_retrieval_keyword.py`

**Interfaces:**
- Consumes: `MetadataFilters` (Task 2, `.to_sql() -> tuple[str, list]`); the `search_vector` column and GIN index (Task 1).
- Produces: `search_keyword(conn, query: str, limit: int = 10, filters: MetadataFilters | None = None) -> list[tuple[str, float]]`. Used by Task 7.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_keyword.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_retrieval_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.keyword import search_keyword
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.schemas.evidence import Provenance, SourceRef

# Deliberately nonsense: guarantees these fixtures are the only matches in
# a database that also holds the full ~36k-document real corpus.
DISTINCTIVE = "zzqvxk flibbertigibbet"


def _doc(doc_id: str, doc_type: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
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
    ensure_retrieval_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_search_keyword_finds_a_document_by_its_body_text(conn):
    upsert_document(conn, _doc("test:kw-1", "act", "Ordinary Title", f"{DISTINCTIVE} provision here"))

    results = search_keyword(conn, DISTINCTIVE)

    assert [doc_id for doc_id, _score in results] == ["test:kw-1"]
    assert results[0][1] > 0


def test_search_keyword_returns_empty_for_no_match(conn):
    assert search_keyword(conn, "quhwjxbz nonexistentterm") == []


def test_search_keyword_respects_document_type_filter(conn):
    upsert_document(conn, _doc("test:kw-act", "act", "Ordinary Title", f"{DISTINCTIVE} provision"))
    upsert_document(conn, _doc("test:kw-judg", "judgment", "Ordinary Title", f"{DISTINCTIVE} provision"))

    results = search_keyword(conn, DISTINCTIVE, filters=MetadataFilters(document_type="judgment"))

    assert [doc_id for doc_id, _score in results] == ["test:kw-judg"]


def test_search_keyword_respects_limit(conn):
    for index in range(3):
        upsert_document(conn, _doc(f"test:kw-lim-{index}", "act", "Ordinary Title", f"{DISTINCTIVE} text"))

    results = search_keyword(conn, DISTINCTIVE, limit=2)

    assert len(results) == 2


def test_search_keyword_handles_a_multi_word_natural_language_query(conn):
    upsert_document(
        conn, _doc("test:kw-nl", "act", "Ordinary Title", f"{DISTINCTIVE} possession and compensation")
    )

    results = search_keyword(conn, f"{DISTINCTIVE} compensation")

    assert "test:kw-nl" in [doc_id for doc_id, _score in results]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_keyword.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.retrieval.keyword'`.

- [ ] **Step 3: Implement `keyword.py`**

Create `src/legal_ai/retrieval/keyword.py`:

```python
"""Keyword search over the canonical store -- exact legal terminology.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

This is Postgres native full-text search ranked with ts_rank_cd, which is
TF-IDF-family -- deliberately NOT called BM25 anywhere, because it is not
BM25. Real BM25 would need an external engine or the ParadeDB pg_search
extension; that trade was made explicitly in the design, and having exact
keyword matching at all matters far more here than the ranking formula.

websearch_to_tsquery (rather than plainto_tsquery) parses user input the
way a search box does: quoted phrases and negation with '-' work, and
malformed input degrades gracefully instead of raising.
"""

from __future__ import annotations

import psycopg

from legal_ai.retrieval.metadata import MetadataFilters


def search_keyword(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
) -> list[tuple[str, float]]:
    filter_sql, filter_params = (filters or MetadataFilters()).to_sql()

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT document_id,
                   ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS rank
            FROM documents
            WHERE search_vector @@ websearch_to_tsquery('english', %s){filter_sql}
            ORDER BY rank DESC, document_id ASC
            LIMIT %s
            """,
            [query, query, *filter_params, limit],
        )
        rows = cur.fetchall()

    return [(document_id, float(rank)) for document_id, rank in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_keyword.py -v`
Expected: PASS (5 tests).

---

### Task 4: `vector.py` — semantic similarity with filters

**Files:**
- Create: `src/legal_ai/retrieval/vector.py`
- Test: `tests/test_retrieval_vector.py`

**Interfaces:**
- Consumes: `MetadataFilters` (Task 2); `embed(text) -> list[float]` from `legal_ai.knowledge.static.embeddings`.
- Produces: `search_vector(conn, query: str, limit: int = 10, filters: MetadataFilters | None = None) -> list[tuple[str, float]]`, where the score is **cosine distance — lower is better**, matching the existing `find_similar`. Used by Task 7.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_vector.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.retrieval.vector import search_vector
from legal_ai.schemas.evidence import Provenance, SourceRef

# Real embeddings of this exact text put the fixtures at distance ~0, which
# is the only reliable way to rank against the full real corpus also in
# this database (a synthetic sparse vector will not -- Milestone 4 lesson).
DISTINCTIVE = "zzqvxk flibbertigibbet possession dispute remedy provision"


def _doc(doc_id: str, doc_type: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=f"Title {doc_id}",
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


def test_search_vector_finds_the_semantically_closest_document(conn):
    upsert_document(conn, _doc("test:vec-1", "act", DISTINCTIVE), embedding=embed(DISTINCTIVE))

    results = search_vector(conn, DISTINCTIVE, limit=5)

    assert "test:vec-1" in [doc_id for doc_id, _distance in results]


def test_search_vector_returns_distance_where_lower_is_better(conn):
    upsert_document(conn, _doc("test:vec-2", "act", DISTINCTIVE), embedding=embed(DISTINCTIVE))

    results = search_vector(conn, DISTINCTIVE, limit=5)
    distance = dict(results)["test:vec-2"]

    assert distance < 0.05


def test_search_vector_respects_document_type_filter(conn):
    upsert_document(conn, _doc("test:vec-act", "act", DISTINCTIVE), embedding=embed(DISTINCTIVE))
    upsert_document(conn, _doc("test:vec-judg", "judgment", DISTINCTIVE), embedding=embed(DISTINCTIVE))

    results = search_vector(
        conn, DISTINCTIVE, limit=5, filters=MetadataFilters(document_type="judgment")
    )

    result_ids = [doc_id for doc_id, _distance in results]
    assert "test:vec-judg" in result_ids
    assert "test:vec-act" not in result_ids


def test_search_vector_respects_limit(conn):
    results = search_vector(conn, DISTINCTIVE, limit=3)
    assert len(results) <= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_vector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.retrieval.vector'`.

- [ ] **Step 3: Implement `vector.py`**

Create `src/legal_ai/retrieval/vector.py`:

```python
"""Vector search over the canonical store -- semantic similarity.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

The existing knowledge.static.store.find_similar is deliberately left
untouched: several callers depend on its current unfiltered behaviour.
This adds MetadataFilters support and returns ids rather than whole
documents, so the fan-in can fuse cheaply and fetch full text only once,
at the end, for the documents that actually survive.

Scores are cosine DISTANCE -- lower is better -- matching find_similar and
the pgvector <=> operator.
"""

from __future__ import annotations

import psycopg

from legal_ai.knowledge.static.embeddings import embed
from legal_ai.retrieval.metadata import MetadataFilters


def search_vector(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
) -> list[tuple[str, float]]:
    filter_sql, filter_params = (filters or MetadataFilters()).to_sql()
    query_embedding = embed(query)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT document_id, embedding <=> %s::vector AS distance
            FROM documents
            WHERE embedding IS NOT NULL{filter_sql}
            ORDER BY distance ASC
            LIMIT %s
            """,
            [query_embedding, *filter_params, limit],
        )
        rows = cur.fetchall()

    return [(document_id, float(distance)) for document_id, distance in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_vector.py -v`
Expected: PASS (4 tests).

---

### Task 5: `graph_search.py` — one-hop expansion from seeds

**Files:**
- Create: `src/legal_ai/retrieval/graph_search.py`
- Test: `tests/test_retrieval_graph_search.py`

**Interfaces:**
- Consumes: `get_driver()` from `legal_ai.graphdb.client`; the existing `CONTAINS`, `CITES`, and `CITES_SECTION` edges written by `legal_ai.graphdb.ingest`.
- Produces: `expand_via_graph(driver, seed_document_ids: list[str], limit: int = 10) -> list[tuple[str, float]]`, score = fraction of seeds that reach the document (0.0–1.0). Used by Task 7.
- **Must not import from `legal_ai.tools`** — see Global Constraints; `tools/graph.py` will import from `retrieval/evidence_builder.py` in Task 6, so the reverse direction would be a circular import. Write the Cypher directly here (it is a different query anyway: multi-seed expansion, not single-document citation listing).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_graph_search.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.retrieval.graph_search import expand_via_graph
from legal_ai.schemas.evidence import Provenance, SourceRef


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
def driver():
    d = get_driver()
    yield d
    with d.session() as session:
        session.run("MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n")
    d.close()


def test_expand_finds_sections_contained_by_a_seed_act(driver):
    act = _doc("test:g-act", "act", "Test Act, 2026", "An Act.")
    section = _doc("test:g-act:sec-1", "section", "Section 1", "Body.", act_id="test:g-act")
    write_act_section(driver, act, section)

    results = expand_via_graph(driver, ["test:g-act"])

    assert "test:g-act:sec-1" in [doc_id for doc_id, _score in results]


def test_expand_excludes_the_seeds_themselves(driver):
    act = _doc("test:g-act2", "act", "Test Act, 2026", "An Act.")
    section = _doc("test:g-act2:sec-1", "section", "Section 1", "Body.", act_id="test:g-act2")
    write_act_section(driver, act, section)

    results = expand_via_graph(driver, ["test:g-act2"])

    assert "test:g-act2" not in [doc_id for doc_id, _score in results]


def test_expand_ranks_a_document_reached_by_two_seeds_above_one_reached_by_one(driver):
    shared = _doc("test:g-shared", "section", "Shared Section", "Body.", act_id="test:g-a")
    act_a = _doc("test:g-a", "act", "Act A", "Body.")
    act_b = _doc("test:g-b", "act", "Act B", "Body.")
    lonely = _doc("test:g-lonely", "section", "Lonely Section", "Body.", act_id="test:g-b")
    write_act_section(driver, act_a, shared)
    write_act_section(driver, act_b, shared)
    write_act_section(driver, act_b, lonely)

    results = expand_via_graph(driver, ["test:g-a", "test:g-b"])
    scores = dict(results)

    assert scores["test:g-shared"] > scores["test:g-lonely"]


def test_expand_returns_empty_for_no_seeds(driver):
    assert expand_via_graph(driver, []) == []


def test_expand_returns_empty_when_a_seed_has_no_neighbours(driver):
    judgment = _doc("test:g-lone-judg", "judgment", "Lone Case", "no citations here", court="Test Court")
    write_judgment(driver, judgment)

    assert expand_via_graph(driver, ["test:g-lone-judg"]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_graph_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.retrieval.graph_search'`.

- [ ] **Step 3: Implement `graph_search.py`**

Create `src/legal_ai/retrieval/graph_search.py`:

```python
"""Knowledge-graph expansion -- what else connects to what we already found.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

Deliberately expansion rather than a standalone signal: the graph stores no
text to match a raw query against, so the only question it can answer well
is "given these documents, what is connected to them?".

Traverses the existing structural edges in both directions -- CONTAINS
(Act->Section), CITES (Judgment->Judgment), CITES_SECTION
(Judgment->Section). A document reached from more distinct seeds scores
higher, so a Section that several retrieved judgments all rely on rises.

Does not import from legal_ai.tools: tools/graph.py imports to_evidence
from retrieval/evidence_builder.py, so importing it back here would be a
circular import.
"""

from __future__ import annotations

import neo4j


def expand_via_graph(
    driver: neo4j.Driver,
    seed_document_ids: list[str],
    limit: int = 10,
) -> list[tuple[str, float]]:
    if not seed_document_ids:
        return []

    with driver.session() as session:
        result = session.run(
            """
            MATCH (seed) WHERE seed.document_id IN $seeds
            MATCH (seed)-[:CONTAINS|CITES|CITES_SECTION]-(neighbour)
            WHERE neighbour.document_id IS NOT NULL
              AND NOT neighbour.document_id IN $seeds
            RETURN neighbour.document_id AS document_id,
                   count(DISTINCT seed) AS seed_count
            ORDER BY seed_count DESC, document_id ASC
            LIMIT $limit
            """,
            seeds=seed_document_ids,
            limit=limit,
        )
        rows = [(record["document_id"], record["seed_count"]) for record in result]

    seed_total = len(seed_document_ids)
    return [(document_id, seed_count / seed_total) for document_id, seed_count in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_graph_search.py -v`
Expected: PASS (5 tests).

---

### Task 6: `evidence_builder.py` — documents to Evidence, consolidating the duplicates

**Files:**
- Create: `src/legal_ai/retrieval/evidence_builder.py`
- Modify: `src/legal_ai/tools/statutes.py` (remove its private `_to_evidence`, import the shared one)
- Modify: `src/legal_ai/tools/judgments.py` (same)
- Modify: `src/legal_ai/tools/graph.py` (same)
- Test: `tests/test_retrieval_evidence_builder.py`

**Interfaces:**
- Consumes: `CanonicalDocument`, `Evidence`, `get_document(conn, document_id)`.
- Produces:
  - `to_evidence(doc: CanonicalDocument) -> Evidence`
  - `build_evidence(conn, document_ids: list[str]) -> list[Evidence]` — preserves the given order, silently skipping ids with no stored document.

  Task 7 uses `build_evidence`. The three `tools/` modules use `to_evidence`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_evidence_builder.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.evidence_builder import build_evidence, to_evidence
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(doc_id: str, doc_type: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://indiacode.nic.in/x", source_type="primary"),
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


def test_to_evidence_carries_identity_and_provenance():
    evidence = to_evidence(_doc("test:e-1", "section", "Section 1", "Body text."))

    assert evidence.document_id == "test:e-1"
    assert evidence.title == "Section 1"
    assert evidence.document_type == "section"
    assert evidence.content == "Body text."
    assert evidence.provenance.source.url == "https://indiacode.nic.in/x"


def test_build_evidence_preserves_the_given_order(conn):
    upsert_document(conn, _doc("test:e-a", "act", "A", "text a"))
    upsert_document(conn, _doc("test:e-b", "act", "B", "text b"))

    evidence = build_evidence(conn, ["test:e-b", "test:e-a"])

    assert [e.document_id for e in evidence] == ["test:e-b", "test:e-a"]


def test_build_evidence_skips_ids_with_no_stored_document(conn):
    upsert_document(conn, _doc("test:e-c", "act", "C", "text c"))

    evidence = build_evidence(conn, ["test:e-c", "test:e-missing"])

    assert [e.document_id for e in evidence] == ["test:e-c"]


def test_build_evidence_returns_empty_for_no_ids(conn):
    assert build_evidence(conn, []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_evidence_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.retrieval.evidence_builder'`.

- [ ] **Step 3: Implement `evidence_builder.py`**

Create `src/legal_ai/retrieval/evidence_builder.py`:

```python
"""Canonical documents -> Evidence, with provenance intact.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

The single home for this conversion. tools/statutes.py, tools/judgments.py
and tools/graph.py each had their own identical private copy; they now
import to_evidence from here.

No score field is set: the returned list is already ordered by the fusion
that produced it, and adding an unused field would be speculative.
"""

from __future__ import annotations

import psycopg

from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Evidence


def to_evidence(doc: CanonicalDocument) -> Evidence:
    return Evidence(
        content=doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        provenance=doc.provenance,
    )


def build_evidence(conn: psycopg.Connection, document_ids: list[str]) -> list[Evidence]:
    """Fetch documents for `document_ids`, preserving that order.

    An id with no stored document is skipped rather than raising: the graph
    can legitimately hold a node whose Postgres row was never stored, and
    dropping it is honest -- inventing a placeholder would not be.

    One round-trip per id is fine here: this runs on the fused top-K
    (single digits), not on a whole result set.
    """
    evidence: list[Evidence] = []
    for document_id in document_ids:
        doc = get_document(conn, document_id)
        if doc is not None:
            evidence.append(to_evidence(doc))
    return evidence
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_evidence_builder.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Consolidate the three duplicate `_to_evidence` copies**

In `src/legal_ai/tools/statutes.py`, `src/legal_ai/tools/judgments.py`, and `src/legal_ai/tools/graph.py`: delete the local `def _to_evidence(doc: CanonicalDocument) -> Evidence:` function from each, add

```python
from legal_ai.retrieval.evidence_builder import to_evidence
```

and replace every `_to_evidence(` call with `to_evidence(`. Then remove any now-unused imports in those three files — check whether `CanonicalDocument` and `Evidence` are still referenced in each file before deleting their imports (in `tools/graph.py`, `Evidence` is still used in the return type annotations, and `CanonicalDocument` becomes unused; in `tools/statutes.py` and `tools/judgments.py`, both become unused only if no other reference remains).

- [ ] **Step 6: Run the tools tests to verify the consolidation broke nothing**

Run: `.venv/bin/pytest tests/test_tools_statutes.py tests/test_tools_judgments.py tests/test_tools_graph.py -v`
Expected: PASS (11 tests) — unchanged behaviour, one shared implementation.

---

### Task 7: `hybrid.py` — Reciprocal Rank Fusion and orchestration

**Files:**
- Create: `src/legal_ai/retrieval/hybrid.py`
- Test: `tests/test_retrieval_hybrid.py`

**Interfaces:**
- Consumes: `search_keyword(conn, query, limit, filters)` (Task 3), `search_vector(conn, query, limit, filters)` (Task 4), `search_metadata(conn, query, limit, filters)` and `MetadataFilters` (Task 2), `expand_via_graph(driver, seed_document_ids, limit)` (Task 5), `build_evidence(conn, document_ids)` (Task 6), `get_connection()`, `get_driver()`.
- Produces:
  - `reciprocal_rank_fusion(ranked_lists: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]` — a pure function, unit-testable without any database.
  - `hybrid_search(query: str, limit: int = 10, filters: MetadataFilters | None = None, expand_graph: bool = True) -> list[Evidence]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retrieval_hybrid.py`:

```python
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_retrieval_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.hybrid import hybrid_search, reciprocal_rank_fusion
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.schemas.evidence import Provenance, SourceRef

DISTINCTIVE = "zzqvxk flibbertigibbet possession dispute remedy provision"


def _doc(doc_id: str, doc_type: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
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
    ensure_retrieval_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_fusion_ranks_a_document_found_by_two_signals_above_one_found_by_one():
    keyword_results = [("doc-a", 0.9), ("doc-b", 0.5)]
    vector_results = [("doc-a", 0.01)]

    fused = reciprocal_rank_fusion([keyword_results, vector_results])

    assert [doc_id for doc_id, _score in fused][0] == "doc-a"
    assert dict(fused)["doc-a"] > dict(fused)["doc-b"]


def test_fusion_uses_rank_not_raw_score():
    # doc-b's raw score is far larger, but it ranks second in its own list,
    # so a document ranked first elsewhere must not be beaten by scale alone.
    list_one = [("doc-a", 0.001)]
    list_two = [("doc-c", 999.0), ("doc-b", 998.0)]

    fused = dict(reciprocal_rank_fusion([list_one, list_two]))

    assert fused["doc-a"] == fused["doc-c"]
    assert fused["doc-a"] > fused["doc-b"]


def test_fusion_of_no_lists_is_empty():
    assert reciprocal_rank_fusion([]) == []


def test_fusion_ignores_empty_signal_lists():
    fused = reciprocal_rank_fusion([[], [("doc-a", 1.0)], []])
    assert [doc_id for doc_id, _score in fused] == ["doc-a"]


def test_hybrid_search_finds_a_document_matching_on_both_keyword_and_vector(conn):
    upsert_document(
        conn, _doc("test:h-1", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(DISTINCTIVE, limit=5, expand_graph=False)

    assert "test:h-1" in [e.document_id for e in results]


def test_hybrid_search_returns_evidence_objects(conn):
    upsert_document(
        conn, _doc("test:h-2", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(DISTINCTIVE, limit=5, expand_graph=False)
    match = next(e for e in results if e.document_id == "test:h-2")

    assert match.content == DISTINCTIVE
    assert match.document_type == "act"
    assert match.provenance.source.name == "India Code"


def test_hybrid_search_respects_the_limit(conn):
    results = hybrid_search(DISTINCTIVE, limit=3, expand_graph=False)
    assert len(results) <= 3


def test_hybrid_search_respects_metadata_filters(conn):
    upsert_document(
        conn, _doc("test:h-act", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )
    upsert_document(
        conn, _doc("test:h-judg", "judgment", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(
        DISTINCTIVE, limit=10, filters=MetadataFilters(document_type="judgment"), expand_graph=False
    )

    result_ids = [e.document_id for e in results]
    assert "test:h-judg" in result_ids
    assert "test:h-act" not in result_ids


def test_hybrid_search_returns_empty_when_nothing_matches(conn):
    results = hybrid_search("quhwjxbz vurpleknack nonexistentterm", limit=5, expand_graph=False)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retrieval_hybrid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.retrieval.hybrid'`.

- [ ] **Step 3: Implement `hybrid.py`**

Create `src/legal_ai/retrieval/hybrid.py`:

```python
"""Hybrid retrieval -- fan the query out across signals, fuse, expand, build.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

The three signals produce mutually incomparable scores: cosine distance
(lower is better), ts_rank_cd (higher is better, unbounded), and exact
match (boolean). Normalising those against each other would be arbitrary
and fragile, so fusion is by RANK, via Reciprocal Rank Fusion.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.retrieval.evidence_builder import build_evidence
from legal_ai.retrieval.graph_search import expand_via_graph
from legal_ai.retrieval.keyword import search_keyword
from legal_ai.retrieval.metadata import MetadataFilters, search_metadata
from legal_ai.retrieval.vector import search_vector
from legal_ai.schemas.evidence import Evidence

# The constant from the original RRF paper (Cormack et al., 2009). Large
# enough that the gap between rank 1 and rank 2 does not dominate agreement
# between signals -- which is the whole point of fusing.
RRF_K = 60

# Each signal returns more candidates than the caller asked for, so fusion
# has room to promote documents that several signals agree on but none
# ranked first.
_SIGNAL_OVERFETCH = 3


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse ranked lists by rank: score(d) = sum over lists of 1 / (k + rank).

    Input scores are ignored on purpose -- only position matters, which is
    what makes incomparable scales safe to combine.
    """
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (document_id, _score) in enumerate(ranked, start=1):
            fused[document_id] = fused.get(document_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))


def hybrid_search(
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
    expand_graph: bool = True,
) -> list[Evidence]:
    """Retrieve the most relevant stored documents for `query`.

    Searches only what is already in the store. Fetching new judgments from
    live external sources is a different job, done by
    legal_ai.tools.judgments.search_judgments.
    """
    fetch = limit * _SIGNAL_OVERFETCH
    conn = get_connection()
    try:
        signal_results = [
            search_keyword(conn, query, limit=fetch, filters=filters),
            search_vector(conn, query, limit=fetch, filters=filters),
            search_metadata(conn, query, limit=fetch, filters=filters),
        ]
        fused = reciprocal_rank_fusion(signal_results)

        if expand_graph and fused:
            seeds = [document_id for document_id, _score in fused[:limit]]
            driver = get_driver()
            try:
                expanded = expand_via_graph(driver, seeds, limit=fetch)
            finally:
                driver.close()
            if expanded:
                fused = reciprocal_rank_fusion([fused, expanded])

        top_ids = [document_id for document_id, _score in fused[:limit]]
        return build_evidence(conn, top_ids)
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_retrieval_hybrid.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — the 74 pre-existing tests plus the 37 added across Tasks 1–7.

- [ ] **Step 6: Sanity-check against real data**

Run:
```bash
.venv/bin/python -c "
from legal_ai.retrieval.hybrid import hybrid_search
for e in hybrid_search('builder failed to give possession on time refund', limit=5):
    print(e.document_id, '|', e.title)
"
```
Expected: five real Act/Section results, RERA-related ones among them. This is a smoke test against the real corpus, not an assertion — record what it returns in the final report, including if the results look weak, rather than reporting success unconditionally.

---

## Self-Review Notes

**Spec coverage:** every module in the spec's architecture diagram has a task — `keyword.py` (3), `vector.py` (4), `metadata.py` (2), `graph_search.py` (5), `hybrid.py` (7), `evidence_builder.py` (6) — plus the spec's two schema changes (1) and the `_to_evidence` consolidation it calls for (6, Step 5). The spec's error-handling rules are enforced by tests: empty-not-error is asserted in Tasks 2, 3, 5, and 7; exceptions are left to propagate everywhere (no bare `except`).

**Deliberately out of scope, per the spec:** sub-projects 2–4 (embeddings abstraction, chunking, reranking) and `search_related_judgments`. No task touches them.

**Type consistency:** every signal returns `list[tuple[str, float]]`; `reciprocal_rank_fusion` consumes `list[list[tuple[str, float]]]` and returns the same element type; `build_evidence` takes `list[str]` and returns `list[Evidence]`. `MetadataFilters.to_sql() -> tuple[str, list]` is consumed identically in Tasks 3 and 4. `expand_via_graph` takes `driver` first (not `conn`) because it touches only Neo4j.

**Known trade-off, stated rather than hidden:** `search_metadata` relies on `extract_section_references`, whose regex needs a reasonably full statutory reference (e.g. "Section 18 of the Real Estate (Regulation and Development) Act, 2016") or a known abbreviation (IPC, CrPC, CPC, NI Act, Evidence Act). A terse query like "Section 18 RERA" will not match, and that signal simply contributes nothing — which RRF handles gracefully, since the other two signals still rank the query. Broadening that regex is a separate change with its own risk of false positives, not folded in here.
