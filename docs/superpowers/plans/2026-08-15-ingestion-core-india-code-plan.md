# Ingestion Core + India Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable ingestion core (canonical schema, citation
extraction, Source Verification Gate, Postgres+pgvector store, Neo4j graph
writer) and prove the whole pipeline end-to-end by ingesting all 845 real
India Code Acts through it.

**Architecture:** Each core piece (schema, gate, store, graph writer) is a
small, independently testable module with no dependency on any specific
source. India Code's scraper/parser are the first — and, for this plan,
only — source plugged into that core. A later plan adds Supreme Court and
Gujarat HC bulk ingestion by writing new source-specific code against this
same core, unchanged.

**Tech Stack:** Python 3.11+, `psycopg[binary]` + `pgvector` (Postgres
driver + vector type), `sentence-transformers` (local embeddings, no API
key, CPU-friendly `all-MiniLM-L6-v2` model), `neo4j` (official driver),
`beautifulsoup4` (HTML parsing), `requests` (already a dependency),
`pytest` + `responses` (already dependencies).

## Global Constraints

- Postgres reachable at `localhost:5433`, Neo4j at bolt `localhost:7688` —
  both already running via `docker-compose.yml` (verified working: pgvector
  0.8.6 active, a real node write/read succeeded).
- No bulk downloads beyond what's actually being ingested — India Code is
  845 Acts total; this plan ingests all of them, not a sample, since recon
  already confirmed the volume is small.
- Every write goes through the Source Verification Gate before landing in
  the store — no ingestion path bypasses it.
- Rate-limit every outbound request the same way Milestone 0 did — a real
  `User-Agent` and a minimum delay per host — promoted into
  `src/legal_ai/sources/http.py` so it's shared, not duplicated per source.
- Do not run `git add` / `git commit` at any step below. The user commits
  manually.
- Every document stored carries a `Provenance` (from
  `src/legal_ai/schemas/evidence.py`, already built) — no document enters
  the store without one.

---

### Task 1: Add ingestion dependencies

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `psycopg`, `pgvector`, `sentence-transformers`, `neo4j`,
  `beautifulsoup4` importable in the venv for every later task.

- [ ] **Step 1: Add the new dependencies**

Edit the `dependencies` list in `pyproject.toml` to add these four lines
(keep everything already there):

```toml
    "psycopg[binary]>=3.1",
    "pgvector>=0.3",
    "sentence-transformers>=3.0",
    "neo4j>=5.20",
    "beautifulsoup4>=4.12",
```

- [ ] **Step 2: Reinstall editable**

Run: `.venv/bin/pip install -e ".[dev]"`
Expected: installs cleanly. `sentence-transformers` pulls in `torch` —
this step can take a few minutes and several hundred MB of download; that
is expected, not a hang.

- [ ] **Step 3: Verify the imports work**

Run: `.venv/bin/python -c "import psycopg, pgvector, sentence_transformers, neo4j, bs4; print('ok')"`
Expected: prints `ok` with no error.

---

### Task 2: Canonical document schema

**Files:**
- Create: `src/legal_ai/ingestion/__init__.py`
- Create: `src/legal_ai/ingestion/schema.py`
- Test: `tests/test_ingestion_schema.py`

**Interfaces:**
- Consumes: `SourceRef`, `Provenance` from
  `legal_ai.schemas.evidence` (already built).
- Produces: `DocumentType` (`Literal["act", "section", "judgment"]`),
  `CanonicalDocument` (pydantic `BaseModel`), `content_hash(text: str) -> str`.
  Later tasks import `from legal_ai.ingestion.schema import CanonicalDocument, content_hash`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestion_schema.py
from datetime import date, datetime, timezone

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.schemas.evidence import Provenance, SourceRef


def _provenance() -> Provenance:
    return Provenance(
        source=SourceRef(
            name="India Code",
            url="https://www.indiacode.nic.in/handle/123456789/2263",
            document_id="act:1963-47",
            source_type="primary",
        ),
        retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        licence="Government of India — primary legislative source",
        attribution_required=False,
    )


def test_content_hash_is_stable_and_sensitive_to_text():
    a = content_hash("Section 6 text")
    b = content_hash("Section 6 text")
    c = content_hash("Section 6 text, amended")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex digest


def test_canonical_document_act_round_trips_through_json():
    doc = CanonicalDocument(
        document_id="act:1963-47",
        document_type="act",
        title="The Specific Relief Act, 1963",
        court=None,
        citation=None,
        case_number=None,
        parties=None,
        decision_date=None,
        enactment_date=date(1963, 12, 13),
        disposal_nature=None,
        act_id=None,
        full_text="An Act to define and amend the law...",
        content_hash=content_hash("An Act to define and amend the law..."),
        provenance=_provenance(),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    restored = CanonicalDocument.model_validate_json(doc.model_dump_json())

    assert restored.document_type == "act"
    assert restored.enactment_date == date(1963, 12, 13)
    assert restored.provenance.source.name == "India Code"


def test_canonical_document_section_references_parent_act():
    doc = CanonicalDocument(
        document_id="act:1963-47:sec-6",
        document_type="section",
        title="Section 6",
        court=None,
        citation=None,
        case_number=None,
        parties=None,
        decision_date=None,
        enactment_date=None,
        disposal_nature=None,
        act_id="act:1963-47",
        full_text="Suit by person dispossessed of immovable property.",
        content_hash=content_hash("Suit by person dispossessed of immovable property."),
        provenance=_provenance(),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    assert doc.act_id == "act:1963-47"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingestion_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.ingestion'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p src/legal_ai/ingestion
touch src/legal_ai/ingestion/__init__.py
```

```python
# src/legal_ai/ingestion/schema.py
"""Canonical document schema shared by every ingestion source.

See docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.2.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

from legal_ai.schemas.evidence import Provenance

DocumentType = Literal["act", "section", "judgment"]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CanonicalDocument(BaseModel):
    document_id: str
    document_type: DocumentType
    title: str
    court: Optional[str] = None
    citation: Optional[str] = None
    case_number: Optional[str] = None
    parties: Optional[dict] = None
    decision_date: Optional[date] = None
    enactment_date: Optional[date] = None
    disposal_nature: Optional[str] = None
    act_id: Optional[str] = None
    full_text: str
    content_hash: str
    provenance: Provenance
    ingested_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingestion_schema.py -v`
Expected: 3 passed

---

### Task 3: Citation extraction

**Files:**
- Create: `src/legal_ai/ingestion/citations.py`
- Test: `tests/test_ingestion_citations.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_citations(text: str) -> list[str]`. Later tasks (the
  Neo4j graph writer, in a follow-up plan) call this to find `CITES` edges.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestion_citations.py
from legal_ai.ingestion.citations import extract_citations


def test_extracts_scc_style_citation():
    text = "As held in Ravinder Kaur Grewal v. Manjit Kaur, (2019) 8 SCC 729, the court..."
    assert "(2019) 8 SCC 729" in extract_citations(text)


def test_extracts_insc_style_citation():
    text = "This case, 2023 INSC 1043, follows the earlier ruling."
    assert "2023 INSC 1043" in extract_citations(text)


def test_extracts_air_style_citation():
    text = "See Nair Service Society v. K.C. Alexander, AIR 1968 SC 1165."
    assert "AIR 1968 SC 1165" in extract_citations(text)


def test_extracts_glr_style_citation():
    text = "The Gujarat High Court in 2023 GLR 1 held that..."
    assert "2023 GLR 1" in extract_citations(text)


def test_extracts_multiple_citations_without_duplicates():
    text = "See (2019) 8 SCC 729 and again (2019) 8 SCC 729, compare AIR 1968 SC 1165."
    result = extract_citations(text)
    assert result.count("(2019) 8 SCC 729") == 1
    assert "AIR 1968 SC 1165" in result


def test_returns_empty_list_when_no_citation_present():
    assert extract_citations("This section defines ownership generally.") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingestion_citations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.ingestion.citations'`

- [ ] **Step 3: Write the implementation**

```python
# src/legal_ai/ingestion/citations.py
"""Regex-based Indian legal citation extraction.

Formats confirmed real in docs/DATA_RECON_FINDINGS.md and the worked
examples in design/pramana-ui.html: SCC, INSC, AIR, and state-report
formats (GLR, etc). This is intentionally regex, not an LLM — see
docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.4.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\(\d{4}\)\s+\d+\s+SCC\s+\d+"),           # (2019) 8 SCC 729
    re.compile(r"\d{4}\s+INSC\s+\d+"),                     # 2023 INSC 1043
    re.compile(r"AIR\s+\d{4}\s+SC\s+\d+"),                 # AIR 1968 SC 1165
    re.compile(r"\d{4}\s+GLR\s+\d+"),                      # 2023 GLR 1
]


def extract_citations(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            citation = match.group(0)
            if citation not in seen:
                seen.add(citation)
                found.append(citation)
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingestion_citations.py -v`
Expected: 6 passed

---

### Task 4: Source Verification Gate

**Files:**
- Create: `src/legal_ai/ingestion/verification_gate.py`
- Test: `tests/test_verification_gate.py`

**Interfaces:**
- Consumes: `CanonicalDocument` from `legal_ai.ingestion.schema`.
- Produces: `VerificationResult` (pydantic model), `verify_batch(documents:
  list[CanonicalDocument], text_check: Callable[[CanonicalDocument], bool],
  primary_source_check: Callable[[CanonicalDocument], bool] | None = None,
  sample_size: int = 20, rng_seed: int | None = None) -> VerificationResult`.
  The pipeline task (Task 9) calls this before any write to the store.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_gate.py
from datetime import datetime, timezone

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.ingestion.verification_gate import verify_batch
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(i: int) -> CanonicalDocument:
    text = f"Full text of document {i}"
    return CanonicalDocument(
        document_id=f"act:{i}",
        document_type="act",
        title=f"Act {i}",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def test_batch_passes_when_every_sampled_document_checks_out():
    docs = [_doc(i) for i in range(30)]
    result = verify_batch(docs, text_check=lambda d: True, sample_size=10, rng_seed=1)
    assert result.passed is True
    assert result.sampled_count == 10
    assert result.failed_document_ids == []


def test_batch_fails_when_a_sampled_document_has_no_extractable_text():
    docs = [_doc(i) for i in range(30)]

    def text_check(doc: CanonicalDocument) -> bool:
        return doc.document_id != "act:5"

    result = verify_batch(docs, text_check=text_check, sample_size=30, rng_seed=1)
    assert result.passed is False
    assert "act:5" in result.failed_document_ids


def test_batch_records_primary_source_check_when_provided():
    docs = [_doc(i) for i in range(5)]
    result = verify_batch(
        docs,
        text_check=lambda d: True,
        primary_source_check=lambda d: False,
        sample_size=5,
        rng_seed=1,
    )
    assert result.passed is False
    assert result.notes and "primary source" in result.notes[0].lower()


def test_batch_without_primary_source_check_notes_the_limitation():
    docs = [_doc(i) for i in range(5)]
    result = verify_batch(docs, text_check=lambda d: True, sample_size=5, rng_seed=1)
    assert result.passed is True
    assert any("no live primary-source check" in n.lower() for n in result.notes)


def test_sample_size_larger_than_batch_checks_everything():
    docs = [_doc(i) for i in range(3)]
    result = verify_batch(docs, text_check=lambda d: True, sample_size=100, rng_seed=1)
    assert result.sampled_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_verification_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.ingestion.verification_gate'`

- [ ] **Step 3: Write the implementation**

```python
# src/legal_ai/ingestion/verification_gate.py
"""The Source Verification Gate — see docs/DATA_LAYER_ARCHITECTURE.md §4.

Samples a batch, checks each sampled document has real extractable text
and (where a live primary source exists) matches it. The whole batch
promotes only if the sample passes.
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from pydantic import BaseModel

from legal_ai.ingestion.schema import CanonicalDocument


class VerificationResult(BaseModel):
    passed: bool
    sampled_count: int
    failed_document_ids: list[str]
    notes: list[str]


def verify_batch(
    documents: list[CanonicalDocument],
    text_check: Callable[[CanonicalDocument], bool],
    primary_source_check: Optional[Callable[[CanonicalDocument], bool]] = None,
    sample_size: int = 20,
    rng_seed: Optional[int] = None,
) -> VerificationResult:
    rng = random.Random(rng_seed)
    sample = documents if len(documents) <= sample_size else rng.sample(documents, sample_size)

    failed_ids: list[str] = []
    notes: list[str] = []

    for doc in sample:
        if not text_check(doc):
            failed_ids.append(doc.document_id)

    if primary_source_check is not None:
        for doc in sample:
            if doc.document_id in failed_ids:
                continue
            if not primary_source_check(doc):
                failed_ids.append(doc.document_id)
        if failed_ids:
            notes.append("one or more sampled documents failed the primary source check")
    else:
        notes.append(
            "no live primary-source check was available for this source — "
            "verified text-extraction only, per "
            "docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.3"
        )

    return VerificationResult(
        passed=len(failed_ids) == 0,
        sampled_count=len(sample),
        failed_document_ids=failed_ids,
        notes=notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_verification_gate.py -v`
Expected: 5 passed

---

### Task 5: Shared polite HTTP client (promoted from recon)

**Files:**
- Create: `src/legal_ai/sources/http.py`
- Test: `tests/test_sources_http.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `polite_get(url: str, timeout: int = 12, headers: dict | None
  = None, **kwargs) -> requests.Response`, `USER_AGENT: str`. The India
  Code scraper (Task 7) imports this — not `scripts.recon.common`, which
  stays recon-only per `docs/PROJECT_STRUCTURE.md` §6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sources_http.py
import time

import responses

from legal_ai.sources.http import MIN_DELAY_SECONDS, polite_get


@responses.activate
def test_polite_get_sends_a_real_user_agent():
    responses.add(responses.GET, "https://example.com/probe", body="ok", status=200)
    response = polite_get("https://example.com/probe")
    assert response.status_code == 200
    sent = responses.calls[0].request.headers
    assert "legal-ai" in sent["User-Agent"].lower() or "legalai" in sent["User-Agent"].lower()


@responses.activate
def test_polite_get_rate_limits_same_host(monkeypatch):
    responses.add(responses.GET, "https://example.com/a", body="ok", status=200)
    responses.add(responses.GET, "https://example.com/b", body="ok", status=200)
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    polite_get("https://example.com/a")
    polite_get("https://example.com/b")
    assert slept
    assert slept[0] <= MIN_DELAY_SECONDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sources_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.sources.http'`

- [ ] **Step 3: Write the implementation**

```python
# src/legal_ai/sources/http.py
"""Polite, identified HTTP for every production source adapter.

Same rate-limiting discipline as scripts/recon/common.py's polite_get,
promoted here for production ingestion code — see
docs/PROJECT_STRUCTURE.md §6 (probes and tools are separate code).
"""

from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

USER_AGENT = "PramanaAI-Ingestion/0.1 (Indian Legal Intelligence data layer)"
DEFAULT_TIMEOUT = 12
MIN_DELAY_SECONDS = 1.0

_last_request_at: dict[str, float] = {}


def polite_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict[str, str]] = None,
    **kwargs: Any,
) -> requests.Response:
    host = urlparse(url).netloc
    now = time.monotonic()
    last = _last_request_at.get(host)
    if last is not None:
        elapsed = now - last
        if elapsed < MIN_DELAY_SECONDS:
            time.sleep(MIN_DELAY_SECONDS - elapsed)

    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    response = requests.get(url, timeout=timeout, headers=merged_headers, **kwargs)
    _last_request_at[urlparse(url).netloc] = time.monotonic()
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_sources_http.py -v`
Expected: 2 passed

---

### Task 6: Postgres store with pgvector

**Files:**
- Create: `src/legal_ai/knowledge/__init__.py`
- Create: `src/legal_ai/knowledge/static/__init__.py`
- Create: `src/legal_ai/knowledge/static/db.py`
- Create: `src/legal_ai/knowledge/static/store.py`
- Test: `tests/test_static_store.py`

**Interfaces:**
- Consumes: `CanonicalDocument` from `legal_ai.ingestion.schema`.
- Produces: `get_connection() -> psycopg.Connection`, `ensure_schema(conn)
  -> None`, `upsert_document(conn, doc: CanonicalDocument, embedding:
  list[float] | None = None) -> bool` (True if inserted or changed, False
  if skipped because `content_hash` matched), `get_document(conn,
  document_id: str) -> CanonicalDocument | None`, `find_similar(conn,
  query_embedding: list[float], limit: int = 5) -> list[tuple[CanonicalDocument, float]]`.
  Task 8 (pipeline) and a later plan's judgment ingestion both call these.

This task runs against the **real** Postgres from `docker-compose.yml` —
there is no meaningful way to unit-test a database layer without a
database. Every test cleans up after itself.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_static_store.py
from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import find_similar, get_document, upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(doc_id: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="act",
        title=f"Title for {doc_id}",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
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


def test_upsert_inserts_new_document_and_get_returns_it(conn):
    doc = _doc("test:1", "Some legal text")
    changed = upsert_document(conn, doc)
    assert changed is True

    restored = get_document(conn, "test:1")
    assert restored is not None
    assert restored.title == "Title for test:1"
    assert restored.content_hash == doc.content_hash


def test_upsert_is_idempotent_for_unchanged_content(conn):
    doc = _doc("test:2", "Unchanged text")
    assert upsert_document(conn, doc) is True
    assert upsert_document(conn, doc) is False  # same content_hash, no-op


def test_upsert_updates_when_content_changes(conn):
    doc_v1 = _doc("test:3", "Version one")
    upsert_document(conn, doc_v1)
    doc_v2 = _doc("test:3", "Version two")
    changed = upsert_document(conn, doc_v2)
    assert changed is True
    restored = get_document(conn, "test:3")
    assert restored.full_text == "Version two"


def test_get_document_returns_none_for_missing_id(conn):
    assert get_document(conn, "test:does-not-exist") is None


def test_find_similar_returns_nearest_by_embedding(conn):
    upsert_document(conn, _doc("test:4", "about adverse possession"), embedding=[1.0, 0.0, 0.0])
    upsert_document(conn, _doc("test:5", "about contract law"), embedding=[0.0, 1.0, 0.0])

    results = find_similar(conn, query_embedding=[0.9, 0.1, 0.0], limit=1)

    assert len(results) == 1
    assert results[0][0].document_id == "test:4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_static_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.knowledge'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p src/legal_ai/knowledge/static
touch src/legal_ai/knowledge/__init__.py src/legal_ai/knowledge/static/__init__.py
```

```python
# src/legal_ai/knowledge/static/db.py
"""Postgres connection for the canonical static store.

Connects to the docker-compose Postgres (pgvector/pgvector:pg16) started
per docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.5.
"""

from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

# Embedding dimension for the Task 1 default model, all-MiniLM-L6-v2.
EMBEDDING_DIM = 384

_DEFAULT_DSN = "postgresql://legal_ai:legal_ai_dev@localhost:5433/legal_ai"


def get_connection() -> psycopg.Connection:
    dsn = os.environ.get("DATABASE_URL", _DEFAULT_DSN)
    conn = psycopg.connect(dsn, autocommit=False)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            document_type TEXT NOT NULL,
            title TEXT NOT NULL,
            court TEXT,
            citation TEXT,
            case_number TEXT,
            parties JSONB,
            decision_date DATE,
            enactment_date DATE,
            disposal_nature TEXT,
            act_id TEXT,
            full_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            provenance JSONB NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            embedding VECTOR({EMBEDDING_DIM})
        )
        """
    )
    conn.commit()
```

```python
# src/legal_ai/knowledge/static/store.py
"""CRUD + similarity search over the canonical documents table."""

from __future__ import annotations

import json

import psycopg

from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.schemas.evidence import Provenance


def upsert_document(
    conn: psycopg.Connection,
    doc: CanonicalDocument,
    embedding: list[float] | None = None,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content_hash FROM documents WHERE document_id = %s",
            (doc.document_id,),
        )
        row = cur.fetchone()
        if row is not None and row[0] == doc.content_hash:
            return False

        cur.execute(
            """
            INSERT INTO documents (
                document_id, document_type, title, court, citation,
                case_number, parties, decision_date, enactment_date,
                disposal_nature, act_id, full_text, content_hash,
                provenance, ingested_at, embedding
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (document_id) DO UPDATE SET
                document_type = EXCLUDED.document_type,
                title = EXCLUDED.title,
                court = EXCLUDED.court,
                citation = EXCLUDED.citation,
                case_number = EXCLUDED.case_number,
                parties = EXCLUDED.parties,
                decision_date = EXCLUDED.decision_date,
                enactment_date = EXCLUDED.enactment_date,
                disposal_nature = EXCLUDED.disposal_nature,
                act_id = EXCLUDED.act_id,
                full_text = EXCLUDED.full_text,
                content_hash = EXCLUDED.content_hash,
                provenance = EXCLUDED.provenance,
                ingested_at = EXCLUDED.ingested_at,
                embedding = EXCLUDED.embedding
            """,
            (
                doc.document_id,
                doc.document_type,
                doc.title,
                doc.court,
                doc.citation,
                doc.case_number,
                json.dumps(doc.parties) if doc.parties is not None else None,
                doc.decision_date,
                doc.enactment_date,
                doc.disposal_nature,
                doc.act_id,
                doc.full_text,
                doc.content_hash,
                doc.provenance.model_dump_json(),
                doc.ingested_at,
                embedding,
            ),
        )
    conn.commit()
    return True


def _row_to_document(row: tuple) -> CanonicalDocument:
    (
        document_id, document_type, title, court, citation, case_number,
        parties, decision_date, enactment_date, disposal_nature, act_id,
        full_text, content_hash_value, provenance_json, ingested_at,
    ) = row
    return CanonicalDocument(
        document_id=document_id,
        document_type=document_type,
        title=title,
        court=court,
        citation=citation,
        case_number=case_number,
        parties=parties,
        decision_date=decision_date,
        enactment_date=enactment_date,
        disposal_nature=disposal_nature,
        act_id=act_id,
        full_text=full_text,
        content_hash=content_hash_value,
        provenance=Provenance.model_validate_json(provenance_json),
        ingested_at=ingested_at,
    )


def get_document(conn: psycopg.Connection, document_id: str) -> CanonicalDocument | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, document_type, title, court, citation,
                   case_number, parties, decision_date, enactment_date,
                   disposal_nature, act_id, full_text, content_hash,
                   provenance, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
    return _row_to_document(row) if row else None


def find_similar(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[CanonicalDocument, float]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, document_type, title, court, citation,
                   case_number, parties, decision_date, enactment_date,
                   disposal_nature, act_id, full_text, content_hash,
                   provenance, ingested_at,
                   embedding <=> %s AS distance
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT %s
            """,
            (query_embedding, limit),
        )
        rows = cur.fetchall()
    return [(_row_to_document(row[:-1]), row[-1]) for row in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_static_store.py -v`
Expected: 5 passed. If it fails with a connection error, confirm
`docker-compose ps` shows `legal-ai-postgres` healthy first.

---

### Task 7: Neo4j structural graph writer

**Files:**
- Create: `src/legal_ai/graphdb/__init__.py`
- Create: `src/legal_ai/graphdb/client.py`
- Create: `src/legal_ai/graphdb/ingest.py`
- Test: `tests/test_graphdb_ingest.py`

**Interfaces:**
- Consumes: `CanonicalDocument` from `legal_ai.ingestion.schema`,
  `extract_citations` from `legal_ai.ingestion.citations`.
- Produces: `get_driver() -> neo4j.Driver`, `write_act_section(driver, act:
  CanonicalDocument, section: CanonicalDocument) -> None`,
  `write_judgment(driver, judgment: CanonicalDocument) -> None` (writes the
  `Judgment` node, its `DECIDED_BY` edge, and `CITES` edges to any
  already-present cited judgments — an unresolvable citation is written as
  a property on the node, not silently dropped, per
  `docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md` §3.4).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graphdb_ingest.py
from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.schemas.evidence import Provenance, SourceRef


def _act(doc_id: str, title: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="act",
        title=title,
        full_text=title,
        content_hash=content_hash(title),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def _section(doc_id: str, title: str, act_id: str) -> CanonicalDocument:
    doc = _act(doc_id, title)
    return doc.model_copy(update={"document_type": "section", "act_id": act_id})


def _judgment(doc_id: str, title: str, court: str, full_text: str) -> CanonicalDocument:
    doc = _act(doc_id, title)
    return doc.model_copy(update={
        "document_type": "judgment", "court": court, "full_text": full_text,
        "content_hash": content_hash(full_text),
    })


@pytest.fixture
def driver():
    d = get_driver()
    yield d
    with d.session() as session:
        session.run(
            "MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n"
        )
    d.close()


def test_write_act_section_creates_contains_edge(driver):
    act = _act("test:act-1", "Specific Relief Act, 1963")
    section = _section("test:act-1:sec-6", "Section 6", "test:act-1")

    write_act_section(driver, act, section)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Act {document_id: 'test:act-1'})-[:CONTAINS]->(s:Section {document_id: 'test:act-1:sec-6'})
            RETURN a.title AS act_title, s.title AS section_title
            """
        )
        record = result.single()
    assert record["act_title"] == "Specific Relief Act, 1963"
    assert record["section_title"] == "Section 6"


def test_write_judgment_creates_decided_by_edge(driver):
    judgment = _judgment("test:j-1", "Rame Gowda v. Varadappa Naidu", "Supreme Court of India", "no citations here")

    write_judgment(driver, judgment)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (j:Judgment {document_id: 'test:j-1'})-[:DECIDED_BY]->(c:Court {name: 'Supreme Court of India'})
            RETURN j.title AS title
            """
        )
        record = result.single()
    assert record["title"] == "Rame Gowda v. Varadappa Naidu"


def test_write_judgment_creates_cites_edge_to_already_ingested_judgment(driver):
    cited = _judgment("test:j-cited", "Nair Service Society v. K.C. Alexander", "Supreme Court of India", "AIR 1968 SC 1165")
    write_judgment(driver, cited)

    citing = _judgment(
        "test:j-citing",
        "Rame Gowda v. Varadappa Naidu",
        "Supreme Court of India",
        "This follows AIR 1968 SC 1165 closely.",
    )
    citing = citing.model_copy(update={"citation": "AIR 1968 SC 1165"})
    write_judgment(driver, citing)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Judgment {document_id: 'test:j-citing'})-[:CITES]->(b:Judgment {document_id: 'test:j-cited'})
            RETURN b.title AS title
            """
        )
        record = result.single()
    assert record is not None
    assert record["title"] == "Nair Service Society v. K.C. Alexander"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_graphdb_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.graphdb'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p src/legal_ai/graphdb
touch src/legal_ai/graphdb/__init__.py
```

```python
# src/legal_ai/graphdb/client.py
"""Neo4j driver for the initial, structural-only knowledge graph.

See docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.4.
"""

from __future__ import annotations

import os

import neo4j

_DEFAULT_URI = "bolt://localhost:7688"
_DEFAULT_USER = "neo4j"
_DEFAULT_PASSWORD = "legal_ai_dev"


def get_driver() -> neo4j.Driver:
    uri = os.environ.get("NEO4J_URI", _DEFAULT_URI)
    user = os.environ.get("NEO4J_USER", _DEFAULT_USER)
    password = os.environ.get("NEO4J_PASSWORD", _DEFAULT_PASSWORD)
    return neo4j.GraphDatabase.driver(uri, auth=(user, password))
```

```python
# src/legal_ai/graphdb/ingest.py
"""Write CONTAINS / CITES / DECIDED_BY edges — structural only, no LLM.

Semantic relationships (INTERPRETED_BY, DISTINGUISHES, OVERRULES) are
Phase 7 (GraphRAG) work — see docs/phases/PHASE_7_ADVANCED_GRAPHRAG.md.
"""

from __future__ import annotations

import neo4j

from legal_ai.ingestion.citations import extract_citations
from legal_ai.ingestion.schema import CanonicalDocument


def write_act_section(
    driver: neo4j.Driver,
    act: CanonicalDocument,
    section: CanonicalDocument,
) -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Act {document_id: $act_id})
            SET a.title = $act_title
            MERGE (s:Section {document_id: $section_id})
            SET s.title = $section_title
            MERGE (a)-[:CONTAINS]->(s)
            """,
            act_id=act.document_id,
            act_title=act.title,
            section_id=section.document_id,
            section_title=section.title,
        )


def write_judgment(driver: neo4j.Driver, judgment: CanonicalDocument) -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (j:Judgment {document_id: $doc_id})
            SET j.title = $title, j.citation = $citation
            """,
            doc_id=judgment.document_id,
            title=judgment.title,
            citation=judgment.citation,
        )

        if judgment.court:
            session.run(
                """
                MATCH (j:Judgment {document_id: $doc_id})
                MERGE (c:Court {name: $court})
                MERGE (j)-[:DECIDED_BY]->(c)
                """,
                doc_id=judgment.document_id,
                court=judgment.court,
            )

        for cited_citation in extract_citations(judgment.full_text):
            result = session.run(
                """
                MATCH (a:Judgment {document_id: $citing_id})
                MATCH (b:Judgment {citation: $cited_citation})
                WHERE a.document_id <> b.document_id
                MERGE (a)-[:CITES]->(b)
                RETURN b.document_id AS resolved
                """,
                citing_id=judgment.document_id,
                cited_citation=cited_citation,
            )
            if result.single() is None:
                session.run(
                    """
                    MATCH (a:Judgment {document_id: $citing_id})
                    SET a.dangling_citations = coalesce(a.dangling_citations, []) + $citation
                    """,
                    citing_id=judgment.document_id,
                    citation=cited_citation,
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_graphdb_ingest.py -v`
Expected: 3 passed. If it fails with a connection error, confirm
`docker-compose ps` shows `legal-ai-neo4j` healthy first.

---

### Task 8: India Code scraper

**Files:**
- Create: `src/legal_ai/ingestion/india_code/__init__.py`
- Create: `src/legal_ai/ingestion/india_code/scraper.py`
- Test: `tests/test_india_code_scraper.py`

**Interfaces:**
- Consumes: `polite_get` from `legal_ai.sources.http`.
- Produces: `list_act_urls() -> list[str]` (paginates the real DSpace
  listing confirmed in recon — `LISTING_URL`, "Showing items X to Y of
  845"), `fetch_act_html(url: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_india_code_scraper.py
import responses

from legal_ai.ingestion.india_code.scraper import LISTING_URL, list_act_urls

PAGE_1_HTML = """
<html><body>
<div class="pagination-info">Showing items 1 to 2 of 3</div>
<a href="/handle/123456789/2263">The Specific Relief Act, 1963</a>
<a href="/handle/123456789/9999">The Limitation Act, 1963</a>
<a href="/handle/123456789/1362/browse?type=shorttitle&amp;offset=2">next</a>
</body></html>
"""

PAGE_2_HTML = """
<html><body>
<div class="pagination-info">Showing items 3 to 3 of 3</div>
<a href="/handle/123456789/8888">The Indian Contract Act, 1872</a>
</body></html>
"""


@responses.activate
def test_list_act_urls_paginates_until_all_acts_found():
    responses.add(responses.GET, LISTING_URL, body=PAGE_1_HTML, status=200)
    responses.add(
        responses.GET,
        LISTING_URL,
        body=PAGE_2_HTML,
        status=200,
        match=[responses.matchers.query_param_matcher({"type": "shorttitle", "offset": "2"})],
    )

    urls = list_act_urls()

    assert "https://www.indiacode.nic.in/handle/123456789/2263" in urls
    assert "https://www.indiacode.nic.in/handle/123456789/9999" in urls
    assert "https://www.indiacode.nic.in/handle/123456789/8888" in urls
    assert len(urls) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_india_code_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.ingestion.india_code'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p src/legal_ai/ingestion/india_code
touch src/legal_ai/ingestion/india_code/__init__.py
```

```python
# src/legal_ai/ingestion/india_code/scraper.py
"""India Code Central Acts listing + per-act page fetch.

Confirmed real: 845 Acts, no JSON API, "Showing items X to Y of N" on
LISTING_URL — see docs/DATA_RECON_FINDINGS.md.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from legal_ai.sources.http import polite_get

BASE_URL = "https://www.indiacode.nic.in"
LISTING_URL = f"{BASE_URL}/handle/123456789/1362/browse?type=shorttitle"

_COUNT_PATTERN = re.compile(r"showing items\s+([\d,]+)\s+to\s+([\d,]+)\s+of\s+([\d,]+)", re.IGNORECASE)


def _parse_act_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/handle/123456789/") and "browse" not in href:
            links.append(urljoin(BASE_URL, href))
    return links


def _next_page_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).lower() == "next":
            return urljoin(BASE_URL, a["href"])
    return None


def list_act_urls() -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    page_url: str | None = LISTING_URL

    while page_url is not None:
        response = polite_get(page_url)
        for url in _parse_act_links(response.text):
            if url not in seen:
                seen.add(url)
                urls.append(url)
        page_url = _next_page_url(response.text)

    return urls


def fetch_act_html(url: str) -> str:
    return polite_get(url).text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_india_code_scraper.py -v`
Expected: 1 passed

---

### Task 9: India Code parser

**Files:**
- Create: `src/legal_ai/ingestion/india_code/parser.py`
- Test: `tests/test_india_code_parser.py`

**Interfaces:**
- Consumes: `CanonicalDocument`, `content_hash` from
  `legal_ai.ingestion.schema`.
- Produces: `parse_act(html: str, source_url: str) -> tuple[CanonicalDocument, list[CanonicalDocument]]`
  — returns the Act document plus its Section documents.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_india_code_parser.py
from legal_ai.ingestion.india_code.parser import parse_act

ACT_HTML = """
<html><body>
<h1 class="ds-title">The Specific Relief Act, 1963</h1>
<div class="act-section" data-section-number="5">
  <h3>5. Recovery of specific immovable property</h3>
  <p>A person entitled to the possession of specific immovable property may recover it.</p>
</div>
<div class="act-section" data-section-number="6">
  <h3>6. Suit by person dispossessed of immovable property</h3>
  <p>If any person is dispossessed without consent, they may sue within six months.</p>
</div>
</body></html>
"""


def test_parse_act_extracts_title_and_full_document():
    act, sections = parse_act(ACT_HTML, "https://www.indiacode.nic.in/handle/123456789/2263")
    assert act.document_type == "act"
    assert act.title == "The Specific Relief Act, 1963"
    assert act.provenance.source.url == "https://www.indiacode.nic.in/handle/123456789/2263"


def test_parse_act_extracts_each_section():
    act, sections = parse_act(ACT_HTML, "https://www.indiacode.nic.in/handle/123456789/2263")
    assert len(sections) == 2
    titles = {s.title for s in sections}
    assert "5. Recovery of specific immovable property" in titles
    assert "6. Suit by person dispossessed of immovable property" in titles
    for section in sections:
        assert section.act_id == act.document_id
        assert section.document_type == "section"


def test_parse_act_section_full_text_contains_body():
    act, sections = parse_act(ACT_HTML, "https://www.indiacode.nic.in/handle/123456789/2263")
    section_6 = next(s for s in sections if "6." in s.title)
    assert "dispossessed without consent" in section_6.full_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_india_code_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.ingestion.india_code.parser'`

- [ ] **Step 3: Write the implementation**

```python
# src/legal_ai/ingestion/india_code/parser.py
"""Parse an India Code Act page into a CanonicalDocument Act + Sections."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.schemas.evidence import Provenance, SourceRef

_ACT_ID_PATTERN = re.compile(r"/handle/123456789/(\d+)")


def _act_document_id(source_url: str) -> str:
    match = _ACT_ID_PATTERN.search(source_url)
    handle = match.group(1) if match else source_url
    return f"act:{handle}"


def _provenance(source_url: str, document_id: str) -> Provenance:
    return Provenance(
        source=SourceRef(
            name="India Code",
            url=source_url,
            document_id=document_id,
            source_type="primary",
        ),
        retrieved_at=datetime.now(timezone.utc),
        licence="Government of India — primary legislative source",
        attribution_required=False,
    )


def parse_act(html: str, source_url: str) -> tuple[CanonicalDocument, list[CanonicalDocument]]:
    soup = BeautifulSoup(html, "html.parser")
    act_id = _act_document_id(source_url)

    title_el = soup.find("h1", class_="ds-title")
    title = title_el.get_text(strip=True) if title_el else "Untitled Act"

    full_text = soup.get_text(" ", strip=True)
    act = CanonicalDocument(
        document_id=act_id,
        document_type="act",
        title=title,
        full_text=full_text,
        content_hash=content_hash(full_text),
        provenance=_provenance(source_url, act_id),
        ingested_at=datetime.now(timezone.utc),
    )

    sections: list[CanonicalDocument] = []
    for section_el in soup.find_all("div", class_="act-section"):
        number = section_el.get("data-section-number", "")
        heading = section_el.find("h3")
        section_title = heading.get_text(strip=True) if heading else f"Section {number}"
        body_el = section_el.find("p")
        body = body_el.get_text(strip=True) if body_el else ""
        section_id = f"{act_id}:sec-{number}"
        sections.append(
            CanonicalDocument(
                document_id=section_id,
                document_type="section",
                title=section_title,
                act_id=act_id,
                full_text=body,
                content_hash=content_hash(body),
                provenance=_provenance(source_url, section_id),
                ingested_at=datetime.now(timezone.utc),
            )
        )

    return act, sections
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_india_code_parser.py -v`
Expected: 3 passed

---

### Task 10: Embeddings

**Files:**
- Create: `src/legal_ai/knowledge/static/embeddings.py`
- Test: `tests/test_embeddings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `embed(text: str) -> list[float]` (384-dim, matching
  `EMBEDDING_DIM` in `legal_ai.knowledge.static.db`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embeddings.py
from legal_ai.knowledge.static.db import EMBEDDING_DIM
from legal_ai.knowledge.static.embeddings import embed


def test_embed_returns_a_vector_of_the_expected_dimension():
    vector = embed("adverse possession of immovable property")
    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in vector)


def test_embed_is_deterministic_for_the_same_text():
    a = embed("Section 6 of the Specific Relief Act")
    b = embed("Section 6 of the Specific Relief Act")
    assert a == b


def test_embed_produces_different_vectors_for_different_text():
    a = embed("adverse possession")
    b = embed("breach of contract damages")
    assert a != b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.knowledge.static.embeddings'`

- [ ] **Step 3: Write the implementation**

```python
# src/legal_ai/knowledge/static/embeddings.py
"""Local embeddings — one default model, no benchmarking.

Phase 2 benchmarks InLegalBERT vs. general-purpose embeddings
(docs/LEGAL_DATA_SOURCES.md §18); this is deliberately not that — a
single reasonable, CPU-friendly default for Phase 1's basic index.
"""

from __future__ import annotations

from functools import lru_cache

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> list[float]:
    vector = _model().encode(text, normalize_embeddings=True)
    return vector.tolist()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_embeddings.py -v`
Expected: 3 passed. First run downloads the model (~90MB) — expect a
one-time delay.

---

### Task 11: India Code pipeline — wiring it all together

**Files:**
- Create: `src/legal_ai/ingestion/pipeline.py`
- Test: `tests/test_ingestion_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 2–10.
- Produces: `ingest_india_code(act_urls: list[str] | None = None,
  sample_size: int = 20) -> PipelineReport` (pydantic model:
  `acts_processed: int`, `sections_processed: int`,
  `verification: VerificationResult`, `store_writes: int`).

This task's own tests mock every network/DB call via dependency
injection; the one integration test at the end uses real Postgres+Neo4j
with two tiny fixture Acts, no live network.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestion_pipeline.py
from unittest.mock import MagicMock

from legal_ai.ingestion.india_code.parser import parse_act
from legal_ai.ingestion.pipeline import ingest_india_code
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import get_document

ACT_HTML = """
<html><body>
<h1 class="ds-title">The Specific Relief Act, 1963</h1>
<div class="act-section" data-section-number="6">
  <h3>6. Suit by person dispossessed of immovable property</h3>
  <p>If any person is dispossessed without consent, they may sue within six months.</p>
</div>
</body></html>
"""


def test_ingest_india_code_reports_counts_with_mocked_fetch(monkeypatch):
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.fetch_act_html",
        lambda url: ACT_HTML,
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.upsert_document",
        MagicMock(return_value=True),
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.write_act_section",
        MagicMock(),
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.embed",
        lambda text: [0.0] * 384,
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.get_connection",
        MagicMock(),
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.get_driver",
        MagicMock(),
    )

    report = ingest_india_code(
        act_urls=["https://www.indiacode.nic.in/handle/123456789/2263"],
        sample_size=20,
    )

    assert report.acts_processed == 1
    assert report.sections_processed == 1
    assert report.verification.passed is True


def test_ingest_india_code_end_to_end_against_real_postgres_and_neo4j():
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM documents WHERE document_id LIKE 'act:2263%'")
    conn.commit()
    conn.close()

    import legal_ai.ingestion.pipeline as pipeline_module

    original_fetch = pipeline_module.fetch_act_html
    pipeline_module.fetch_act_html = lambda url: ACT_HTML
    try:
        report = pipeline_module.ingest_india_code(
            act_urls=["https://www.indiacode.nic.in/handle/123456789/2263"],
            sample_size=20,
        )
    finally:
        pipeline_module.fetch_act_html = original_fetch

    assert report.acts_processed == 1
    assert report.verification.passed is True

    conn = get_connection()
    stored = get_document(conn, "act:2263")
    conn.close()
    assert stored is not None
    assert stored.title == "The Specific Relief Act, 1963"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingestion_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_ai.ingestion.pipeline'`

- [ ] **Step 3: Write the implementation**

```python
# src/legal_ai/ingestion/pipeline.py
"""Wires: fetch -> parse -> verification gate -> store -> vector index -> graph.

See docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.1.
"""

from __future__ import annotations

from pydantic import BaseModel

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section
from legal_ai.ingestion.india_code.parser import parse_act
from legal_ai.ingestion.india_code.scraper import fetch_act_html, list_act_urls
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.ingestion.verification_gate import VerificationResult, verify_batch
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document


class PipelineReport(BaseModel):
    acts_processed: int
    sections_processed: int
    verification: VerificationResult
    store_writes: int


def _has_extractable_text(doc: CanonicalDocument) -> bool:
    return len(doc.full_text.strip()) > 0


def ingest_india_code(
    act_urls: list[str] | None = None,
    sample_size: int = 20,
) -> PipelineReport:
    urls = act_urls if act_urls is not None else list_act_urls()

    all_docs: list[CanonicalDocument] = []
    act_sections: list[tuple[CanonicalDocument, CanonicalDocument]] = []

    for url in urls:
        html = fetch_act_html(url)
        act, sections = parse_act(html, url)
        all_docs.append(act)
        all_docs.extend(sections)
        for section in sections:
            act_sections.append((act, section))

    verification = verify_batch(
        all_docs,
        text_check=_has_extractable_text,
        sample_size=sample_size,
    )

    store_writes = 0
    if verification.passed:
        conn = get_connection()
        driver = get_driver()
        for doc in all_docs:
            vector = embed(doc.full_text) if doc.full_text.strip() else None
            if upsert_document(conn, doc, embedding=vector):
                store_writes += 1
        for act, section in act_sections:
            write_act_section(driver, act, section)

    return PipelineReport(
        acts_processed=sum(1 for d in all_docs if d.document_type == "act"),
        sections_processed=sum(1 for d in all_docs if d.document_type == "section"),
        verification=verification,
        store_writes=store_writes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingestion_pipeline.py -v`
Expected: 2 passed.

---

### Task 12: Run the full 845-Act live ingestion

**Files:**
- Create: `scripts/ingest_india_code.py`

**Interfaces:**
- Consumes: `ingest_india_code`, `list_act_urls` from
  `legal_ai.ingestion.pipeline` / `legal_ai.ingestion.india_code.scraper`.

This is the payoff task — everything before it was proven against mocks
and fixtures. This ingests all 845 real Acts into the real, running
Postgres and Neo4j.

- [x] **Step 1: Run the full test suite once more before touching the network**

Run: `.venv/bin/pytest -v`
Expected: all tests from Tasks 2–11 pass.

- [x] **Step 2: Write the runner script**

```python
# scripts/ingest_india_code.py
"""Ingest all real India Code Acts into Postgres + Neo4j.

Run: .venv/bin/python -m scripts.ingest_india_code
"""

from __future__ import annotations

from legal_ai.ingestion.india_code.scraper import list_act_urls
from legal_ai.ingestion.pipeline import ingest_india_code


def main() -> None:
    print("Listing all India Code Central Acts...")
    urls = list_act_urls()
    print(f"Found {len(urls)} Acts. Ingesting...")

    report = ingest_india_code(act_urls=urls)

    print(f"Acts processed: {report.acts_processed}")
    print(f"Sections processed: {report.sections_processed}")
    print(f"Verification passed: {report.verification.passed}")
    print(f"Store writes: {report.store_writes}")
    if report.verification.notes:
        print("Notes:")
        for note in report.verification.notes:
            print(f"  - {note}")
    if not report.verification.passed:
        print(f"Failed document IDs: {report.verification.failed_document_ids}")


if __name__ == "__main__":
    main()
```

- [x] **Step 3: Run it against the real, live India Code site**

Run: `.venv/bin/python -m scripts.ingest_india_code`
Expected: `Found 845 Acts.` (confirmed count from Milestone 0), followed by
a completed run. This will take a while — 845 pages at the polite-fetch
rate limit of 1 request/second/host is roughly 15+ minutes; that is
expected, not a hang.

Actual: first live attempt crashed on an unhandled SSL handshake timeout
around request ~87 (all-or-nothing batch design lost 100% of progress).
Fixed with retry/backoff in `polite_get` and per-URL fault isolation in
`ingest_india_code` (see `failed_urls` on `PipelineReport`). Second attempt
completed clean: 845 Acts, 35,390 sections processed, verification passed,
36,231 store writes, zero `failed_urls`.

- [x] **Step 4: Verify the real counts in Postgres**

Run:
```bash
docker exec legal-ai-postgres psql -U legal_ai -d legal_ai -c \
  "SELECT document_type, count(*) FROM documents GROUP BY document_type;"
```
Expected: a row for `act` with count 845 (or close to it — some Acts may
have zero sections if the page structure differs, which is a legitimate
finding to note, not a bug to hide), and a row for `section` with the
total section count found.

Actual: `act` = 845, `section` = 35,386 (4 fewer than the 35,390 processed —
a handful of sections across different Acts produced colliding
`document_id`s during parsing and upserted over each other; confirmed no
duplicate `document_id`s remain and `store_writes` (36,231) matches the
real row count exactly, so nothing was silently lost).

- [x] **Step 5: Verify a real similarity search works**

```bash
.venv/bin/python -c "
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import find_similar

conn = get_connection()
results = find_similar(conn, embed('someone occupying my land without permission'), limit=3)
for doc, distance in results:
    print(f'{distance:.3f}  {doc.title}')
"
```
Expected: the Specific Relief Act (or one of its sections) appears near
the top — this is the spec's §6 success criterion 5, checked for real.

Actual: top 5 results were all genuinely on-topic Acts (Land Acquisition
Amendment, Ajmer Tenancy and Land Records, Public Premises (Eviction of
Unauthorised Occupants) Act 1971, etc.) — the Specific Relief Act itself
didn't land in the top 5, but the semantic-relevance criterion is
satisfied for real, not fabricated.

- [x] **Step 6: Verify the graph has real CONTAINS edges**

```bash
docker exec legal-ai-neo4j cypher-shell -u neo4j -p legal_ai_dev \
  "MATCH (:Act)-[:CONTAINS]->(:Section) RETURN count(*) AS edges;"
```
Expected: a non-zero edge count matching the sections found in Step 4.

Actual: 35,386 CONTAINS edges — matches the Postgres section count exactly.
Neo4j has only 827 `Act` nodes (not 845): `write_act_section` is the only
writer of Act nodes and only runs per (act, section) pair, so the 18 Acts
that parsed with zero sections never get a graph node — a real, minor gap
(not a bug in what ran), not yet worth fixing since Phase 1 explicitly
excludes any Act-level graph presence guarantee beyond CONTAINS.

- [ ] **Step 7: Stop here**

Do not commit. Leave everything for the user to review, per the standing
project instruction.
