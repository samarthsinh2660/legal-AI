# Phase 1 --- Data Foundation

## Objective

Build a clean, searchable, versioned Indian legal data foundation.

**No agents, no query tools, no retrieval system yet.** Phase 1 answers one
question only: *do we have reliable Indian legal data, in a usable
structure, with provenance and licensing attached?* Everything else --
searching it, reasoning over it, drafting from it -- is later phases.

------------------------------------------------------------------------

## 1. Scope

``` text
                      PHASE 1
                 DATA FOUNDATION
                        |
           +------------+------------+
           |            |            |
           v            v            v
       India Code  Supreme Court  Gujarat HC
           |            |            |
           +------------+------------+
                        |
                        v
                   Normalize
                        |
                        v
              Canonical Data Store
                        |
               +--------+--------+
               |                 |
               v                 v
           Vector Store      Initial KG
```

**Static sources for Phase 1:**

``` text
India Code
Supreme Court
Gujarat HC
```

Get the data -> normalize -> store -> attach metadata -> attach provenance.

**Also investigate** (to determine the best ingestion/search mechanism for
each, without committing to using all of them in production):

``` text
Bharat Courts
Vanga SC
Vanga HC
Indian Kanoon
```

------------------------------------------------------------------------

## 2. Milestone 0 --- Data Recon (complete)

Before building anything, this milestone answered the scope question above
with evidence instead of assumption.

Five one-time probe scripts (`scripts/recon/`) each sampled one or two
objects from a source, inspected the real schema, and reported back --- they
do not download a corpus and are not the `tools/` layer a query-time agent
will call (that's Phase 2).

- Spec: `docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md`
- Plan: `docs/superpowers/plans/2026-08-14-phase1-data-recon-plan.md`
- Findings: `docs/DATA_RECON_FINDINGS.md`

Key results:

``` text
Supreme Court bulk (Vanga S3)   -> ready to build an ingestion adapter against
                                    (confirmed: 856 real rows, 18 real columns,
                                    sampled 2023)
Gujarat HC bulk (Vanga S3)      -> ready, but coverage is 2000-2026, not
                                    1950-present as the bulk README implies
                                    globally -- confirmed per-court/bench
India Code                      -> confirmed scrape-only, no JSON API;
                                    845 real Central Acts confirmed
Official SC search portal       -> CAPTCHA-protected (Securimage +
                                    csrf-magic.js, confirmed in the live page)
                                    -- not automatable, not a Phase 1 target
Bharat Courts SDK               -> installs, imports, and a real call
                                    (list_recent_judgments(), no CAPTCHA)
                                    returned live current SC judgments
                                    via www.sci.gov.in
```

------------------------------------------------------------------------

## 3. Static Data Pipeline

``` text
Source
  |
  v
Ingestion
  |
  v
Parsing / normalization
  |
  v
Legal entity extraction
  |
  v
Citation extraction
  |
  v
Source Verification Gate      (see DATA_LAYER_ARCHITECTURE.md §4)
  |
  v
Knowledge graph + vector index
```

Initial data covered:

``` text
Constitution
India Code
Acts
Sections
Rules
Regulations
High-confidence Supreme Court judgments
Selected Gujarat High Court judgments
```

See `DATA_LAYER_ARCHITECTURE.md` §3--4 for the full static pipeline
architecture, including the Source Verification Gate that must pass before
any ingested batch is promoted to the trusted store.

------------------------------------------------------------------------

## 4. Milestones

### Milestone 1 --- Static India Code knowledge base (complete)

845 regular Acts + 14 Spent Acts (860 total, matching the official current
count), 35,601 Sections, real body text for 99.997% of them (the one
disclosed exception is documented in
`docs/superpowers/specs/2026-08-15-section-body-fetch-design.md`).
Real-estate-sector pilot tested against this data --- see
`docs/superpowers/specs/2026-08-17-real-estate-pilot-testing.md`.

### Milestone 2 --- Supreme Court + any state High Court (complete)

**Superseded the original plan of bulk-ingesting the full corpus, and
broadened from "Gujarat HC" specifically to any state HC.** Per team
decision 2026-08-17 (see
`docs/superpowers/specs/2026-08-17-dynamic-judgment-search-design.md`):
the static knowledge graph covers Acts/Sections/Penal Codes only. Supreme
Court judgments and state High Court judgments (via Bharat Courts'
`ArchiveClient`) are fetched **lazily and cached** --- a judgment is only
fetched, verified through the Source Verification Gate, and permanently
stored the first time a real query actually needs it, not speculatively
ahead of time.

Built and verified against real data 2026-08-19:
`src/legal_ai/ingestion/judgments/dynamic_search.py` (fetch + verify),
`src/legal_ai/ingestion/judgments/store.py` (store), `scripts/search_judgment.py`
(CLI). Also extended beyond the original design: judgment text is now
regex-scanned for Act/Section references (`statute_citations.py`) and
resolved into `CITES_SECTION` graph edges, queryable via
`scripts/section_case_lookup.py` --- e.g. "which stored judgments cite
Section 18 of RERA."

District Courts (also available via Bharat Courts, 700+ complexes) were
investigated and deliberately deferred --- two confirmed upstream bugs
make that path unreliable right now (wrong state codes; search failures
silently reported as "0 results"), filed as
[bharat-courts#25](https://github.com/iamshouvikmitra/bharat-courts/issues/25)
and
[#26](https://github.com/iamshouvikmitra/bharat-courts/issues/26). See
the design doc's "District Courts" section for the full writeup.

### Milestone 3 (complete)

Canonical document store, vector index, and initial knowledge graph --
the two outputs at the bottom of the §1 diagram. This is a basic index
sufficient to prove the corpus is stored and queryable; the full hybrid
retrieval system (keyword + vector + metadata + graph, reranking) is
Phase 2, not this milestone.

Satisfied as a byproduct of Milestones 1 and 2, not separate work: the
Postgres `documents` table (canonical store) and pgvector embeddings
(vector index) hold every ingested Act/Section/Judgment, and Neo4j holds
the initial graph -- `CONTAINS` (Act->Section), `CITES`
(judgment->judgment), `CITES_SECTION` (judgment->Section, added
2026-08-19), `DECIDED_BY` (judgment->Court) -- all populated with real
data, none of it speculative.

------------------------------------------------------------------------

## 5. Deliverable

> A clean, searchable, versioned Indian legal data foundation.

**Revised 2026-08-17** to match Milestone 2's revised approach (see
`docs/superpowers/specs/2026-08-17-dynamic-judgment-search-design.md`) --
the original bar required a fully bulk-ingested Supreme Court + Gujarat HC
corpus, which is no longer the plan. Phase 1 is now successful when:

**For India Code (static, fully ingested):**

1. Data has been ingested from a confirmed-reachable source.
2. Every document has passed the Source Verification Gate (sampled and
   checked against the primary source, not just the bulk mirror).
3. Every document carries full provenance (source, URL, document ID,
   retrieved-at, licence, attribution requirement).
4. The corpus is stored in a canonical schema, indexed in a basic vector
   store, and represented in an initial knowledge graph.
5. The store is versioned, so a later re-sync doesn't silently overwrite
   what an earlier answer was grounded in.

**Status:** complete -- see Milestone 1 above.

**For Supreme Court + any state High Court (dynamic, lazy-cached):**

1. A working fetch-verify-store mechanism exists that, given a real
   judgment lookup, checks the DB first, then searches the Bharat Courts
   archive (SC + any state HC) / Indian Kanoon in order, runs whatever it
   finds through the same Source Verification Gate as India Code, and
   stores it with full provenance + graph edges on success.
2. Bharat Courts has been probed and used live, the same way the Vanga
   buckets were probed in Milestone 0.
3. At least one real judgment has been fetched, verified, and stored this
   way end-to-end via the actual tool, proving the mechanism works on
   real data.

**Status:** complete -- see Milestone 2 above. Verified live 2026-08-19
against a real Delhi High Court judgment (`judgment:dlhc010257112023`,
found via the archive, verified, stored) and confirmed idempotent
(re-running the same lookup short-circuits on the DB check, no network
call). District Courts are a known, deliberately deferred gap -- not
required for this Status, see Milestone 2's note above.

**Why this fetch-verify-store mechanism is still Phase 1, not Phase 2:**
it is a data-layer utility parallel to `ingest_india_code` -- it fetches,
verifies, and stores one document, the same job the India Code pipeline
does, just triggered lazily instead of in a bulk batch. It is not an
agent, does not do multi-step reasoning, and does not answer a user's
question -- so the "no agent, no query interface" boundary below still
holds; only *how* Phase 1's own ingestion gets triggered has changed for
this data source, not *what* Phase 1 is responsible for.

No agent, no search tool, and no query interface is required to call this
phase done -- those are what Phase 2 and Phase 3 build on top of this
foundation.

------------------------------------------------------------------------

## 6. Explicitly not in this phase

``` text
search_*() tools               -> Phase 2
Hybrid retrieval / reranking   -> Phase 2
Supervisor / Research Agent    -> Phase 3
Document Agent / Case Agent    -> Phase 4
Analyst Agent / Draft Agent    -> Phase 5
Verification Agent             -> Phase 6
Active learning / promotion    -> Phase 6
GraphRAG / precedent graph     -> Phase 7
```

See `AI_PROJECT_PROPOSAL.md` §11 for the full 7-phase roadmap these hand off
to.
