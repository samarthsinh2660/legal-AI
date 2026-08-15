# Phase 1 — Data Foundation: Ingestion Pipeline

**Status:** Draft — pending review
**Depends on:** `docs/DATA_LAYER_ARCHITECTURE.md`, `docs/LEGAL_DATA_SOURCES.md`,
`docs/PROJECT_STRUCTURE.md`, `docs/DATA_RECON_FINDINGS.md`,
`docs/phases/PHASE_1_DATA_FOUNDATION.md`

## 1. Objective

Turn the confirmed-viable sources from Milestone 0 (data recon) into an
actual, queryable data foundation: India Code, Supreme Court, and Gujarat
HC, ingested, normalized, verified against their primary sources, stored in
a canonical schema, and indexed in a basic vector store and initial
knowledge graph.

This is Milestones 1–3 of `PHASE_1_DATA_FOUNDATION.md`.

## 2. Scope

### In scope

- **India Code** — all 845 confirmed Central Acts (`DATA_RECON_FINDINGS.md`),
  scraped, parsed into Acts + Sections, normalized.
- **Supreme Court** — bulk ingestion from the Vanga S3 corpus, **years
  2022–2026 only** for this pass.
- **Gujarat High Court** — bulk ingestion from the Vanga S3 corpus,
  **years 2022–2026 only** for this pass (within the confirmed 2000–2026
  coverage window).
- The **Source Verification Gate** (`DATA_LAYER_ARCHITECTURE.md` §4),
  actually implemented and run against every ingested batch, not just
  described.
- A **canonical document schema** covering Acts, Sections, and Judgments in
  one unified shape.
- **Postgres + pgvector** as the canonical store and vector index.
- **Neo4j** as the initial knowledge graph, populated with **structural**
  relationships only (`CONTAINS`, `CITES`, `DECIDED_BY`) extracted by
  parsing, not by an LLM.
- **Versioning** — a content hash per document, so re-running ingestion
  updates only what actually changed.

### Out of scope (deferred to later phases/milestones)

- Full historical corpora (pre-2022 SC/HC, and any expansion beyond
  Gujarat) — a config change on this same pipeline, not a redesign, but not
  done now.
- Hybrid retrieval (keyword search, reranking, metadata/graph fan-in) —
  Phase 2.
- Semantic graph relationships (`INTERPRETED_BY`, `DISTINGUISHES`,
  `OVERRULES`) that require an LLM to read and understand a judgment —
  Phase 7 (GraphRAG).
- Embedding model benchmarking (InLegalBERT vs. general-purpose) — Phase 2
  per `LEGAL_DATA_SOURCES.md` §18; this milestone uses one reasonable
  default embedding model and does not evaluate alternatives.
- District Courts, other High Courts, Indian Kanoon, Bharat Courts bulk
  ingestion — none of these are Phase 1 sources per
  `PHASE_1_DATA_FOUNDATION.md` §1.
- Any `tools/`, `agents/`, or query interface — Phase 2 onward.

## 3. Architecture

### 3.1 Pipeline

``` text
                 PRIMARY SOURCES
                       |
       +---------------+---------------+
       |               |               |
       v               v               v
   India Code     Supreme Court    Gujarat HC
   (845 Acts)      (2022-2026)     (2022-2026)
       |               |               |
       +---------------+---------------+
                       |
                       v
                Data Ingestion
                       |
                       v
             Parse / Normalize
              (canonical schema)
                       |
                       v
           Citation Extraction
          (regex, for graph edges)
                       |
                       v
          SOURCE VERIFICATION GATE
                       |
              +--------+--------+
              |                 |
           passed            failed
              |                 |
              v                 v
     +--------+--------+   Held for review
     |                 |   (docs/DATA_INGESTION_REVIEW/<batch>.json)
     v                 v
  pgvector          Neo4j
  (embeddings)   (structural graph)
```

### 3.2 Canonical document schema

One shape for all three document types, discriminated by `document_type`.
Extends the `Evidence`/`Provenance` schema already built in Milestone 0
(`src/legal_ai/schemas/evidence.py`) rather than replacing it — every
canonical document carries a `Provenance`.

``` python
DocumentType = Literal["act", "section", "judgment"]

class CanonicalDocument(BaseModel):
    document_id: str            # stable, source-prefixed (e.g. "sc:2023_16_872")
    document_type: DocumentType
    title: str
    court: str | None           # None for act/section
    citation: str | None
    case_number: str | None     # CNR for judgments
    parties: dict | None        # {"petitioner": ..., "respondent": ...}
    decision_date: date | None  # judgments
    enactment_date: date | None # acts
    disposal_nature: str | None
    act_id: str | None          # for sections: parent act's document_id
    full_text: str
    content_hash: str           # sha256(full_text) — versioning key
    provenance: Provenance      # from legal_ai.schemas.evidence
    ingested_at: datetime
```

Real field names confirmed in `DATA_RECON_FINDINGS.md` (e.g. SC's
`nc_display`, `author_judge`, `available_languages`) map into
`CanonicalDocument` via source-specific parsers, not by inventing new
assumed fields.

### 3.3 Source Verification Gate — implemented

Per `DATA_LAYER_ARCHITECTURE.md` §4, as a real function, not just a
diagram:

``` python
def verify_batch(documents: list[CanonicalDocument], sample_size: int = 20) -> VerificationResult:
    """Sample `sample_size` documents, check each against its primary
    source, confirm extractable text. Batch promotes only if the sample
    passes; otherwise it's held for review, not silently dropped or
    silently ingested."""
```

- For Supreme Court, "primary source" means `www.sci.gov.in` — confirmed
  reachable without CAPTCHA in Milestone 0 (`bharat_courts` probe). Sampled
  documents are checked against it where the document is recent enough to
  appear there; older sampled documents fall back to a documented "held for
  manual spot-check" outcome rather than a fabricated pass.
- For Gujarat HC and India Code, no equivalent CAPTCHA-free live check was
  confirmed in Milestone 0 — the gate for these two checks PDF-text
  extraction and internal consistency (dates, citation format) rather than
  a live cross-check, and this limitation is stated explicitly in the
  gate's own report, not hidden.

### 3.4 Knowledge graph — structural only

``` text
(:Act {document_id, title})-[:CONTAINS]->(:Section {document_id, title})
(:Judgment {document_id, citation})-[:CITES]->(:Judgment {document_id})
(:Judgment {document_id})-[:DECIDED_BY]->(:Court {name})
```

`CITES` edges come from a regex-based Indian citation parser
(`graphdb/extraction/citations.py`) run over each judgment's full text —
matching patterns like `(2019) 8 SCC 729`, `2023 INSC 1043`,
`AIR 1968 SC 1165` — resolved against `document_id`s already in the store.
An unresolvable citation (case not yet ingested) is recorded as a
dangling reference, not silently dropped, so it can resolve once that
judgment is ingested later.

### 3.5 Infrastructure

`docker-compose.yml` (does not exist yet — created by this work):

``` yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment: [POSTGRES_DB=legal_ai, ...]
    ports: ["5432:5432"]
  neo4j:
    image: neo4j:5
    ports: ["7474:7474", "7687:7687"]
```

`opensearch` is not included — it belongs to Phase 2's hybrid retrieval,
not this milestone's "basic, queryable" bar.

## 4. Error handling

- **Per-source isolation.** India Code, Supreme Court, and Gujarat HC
  ingest independently; one source failing doesn't block the others,
  matching the per-probe isolation pattern from Milestone 0.
- **Idempotent re-runs.** `content_hash` means re-running ingestion against
  an unchanged document is a no-op, not a duplicate write.
- **Verification failure is not a crash.** A batch that fails the
  Source Verification Gate is written to a review directory with the
  reasons, and ingestion continues with the next batch.
- **Politeness carries over.** The `polite_get()` rate-limiting built in
  Milestone 0 (`scripts/recon/common.py`) is promoted into
  `src/legal_ai/sources/` and reused here — full-corpus ingestion is where
  "avoid high-concurrency scraping" actually matters, not just recon.

## 5. Testing

- Unit tests for every parser (`ingestion/parsers/`) against fixture
  HTML/PDF, same mocked-HTTP pattern as the Milestone 0 probes.
- Unit tests for the citation-extraction regex against a table of real
  citation formats confirmed in recon (`2023 INSC 1043`, `(2019) 8 SCC 729`,
  `AIR 1968 SC 1165`, `2023 GLR 1`).
- Unit tests for the Source Verification Gate's pass/fail logic with
  fixture batches (all-pass, all-fail, mixed).
- One integration test, run against a docker-composed Postgres+Neo4j, that
  ingests a **tiny** real slice (1 Act, 5 judgments) end-to-end and asserts
  the documents land in both pgvector and Neo4j correctly. This is the only
  step that touches live infrastructure; it does not touch the live network
  (uses the same fixture data as the unit tests).
- A separate, manually-run final step ingests the real scoped slice
  (845 Acts, SC+Gujarat HC 2022–2026) against live sources — this is
  expected to take substantially longer than Milestone 0's recon and is
  not part of the automated test suite.

## 6. Success criteria

Matches `PHASE_1_DATA_FOUNDATION.md` §5, made concrete:

1. All 845 India Code Acts are ingested, normalized, and stored.
2. Supreme Court and Gujarat HC judgments for 2022–2026 are ingested,
   normalized, and stored.
3. Every ingested batch has a Source Verification Gate report (pass, fail,
   or documented partial-check) — none were silently skipped.
4. Every document carries full provenance and a content hash.
5. pgvector returns a plausible nearest-neighbor result for a known query
   (e.g. "adverse possession" surfaces the Specific Relief Act and at least
   one of the judgments already used as running examples in `design/`).
6. Neo4j contains real `CONTAINS` and `CITES` edges, queryable, for the
   ingested set.
7. Re-running ingestion is idempotent — a second run against unchanged
   sources writes nothing new.
