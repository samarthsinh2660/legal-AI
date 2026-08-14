# Phase 1 — Data Layer Recon & Scaffold

**Status:** Implemented — see `docs/DATA_RECON_FINDINGS.md` for results and
`docs/PHASE_1_AI_RESEARCH_PLAN.md` §11 Milestone 0 for how this fits the
overall Phase 1 sequence.
**Depends on:** `docs/AI_PROJECT_PROPOSAL.md`, `docs/DATA_LAYER_ARCHITECTURE.md`,
`docs/LEGAL_DATA_SOURCES.md`, `docs/PHASE_1_AI_RESEARCH_PLAN.md`,
`docs/PROJECT_STRUCTURE.md`

## 1. Objective

Before writing a single line of ingestion or agent code, answer one question
with evidence rather than assumption:

> Do we actually have good Indian legal data, in a usable structure, with
> reliable provenance — for India Code, the Supreme Court, and Gujarat High
> Court?

This reorders Phase 1 to be **data-first**: data layer → data quality → query
layer → analysis → verification, per the corrected execution order. District
Court coverage is explicitly "best effort," not a blocker — Supreme Court +
Gujarat HC + India Code is sufficient to stand up the first reliable data
layer.

This spec covers only the **reconnaissance** step: determine what can be
downloaded, how much exists, in what format, and under what licence — before
any bulk ingestion is written.

## 2. Scope

### In scope

- A minimal Python project scaffold matching `PROJECT_STRUCTURE.md`, enough
  to host recon scripts as real code rather than throwaway one-offs.
- Five probe scripts, one per source, each producing a small structured
  report rather than a wall of raw output.
- One aggregated findings document, written from what the scripts actually
  observed.

### Out of scope (explicitly deferred to the next spec)

- Bulk downloading of any corpus.
- Postgres/pgvector, Neo4j, or any persistent store.
- Parsing, normalization, or entity/citation extraction.
- The `ThreadContext`, any LangGraph node, or any agent.
- Anything under `src/legal_ai/ingestion/`, `knowledge/`, `graphdb/`,
  `retrieval/` beyond empty placeholder packages.

If a probe script tempts scope creep ("might as well download the whole
year while I'm here") — it doesn't. Recon samples one or two objects per
source; it never mirrors a corpus.

## 3. Already-confirmed findings (from live probing during design)

These were checked directly before writing this spec and inform the design
below rather than being re-discovered by the scripts from scratch:

- Both Vanga S3 buckets (`indian-supreme-court-judgments`,
  `indian-high-court-judgments`) are **public and unauthenticated** — plain
  HTTPS `GET ?list-type=2` works, no AWS credentials or `--no-sign-request`
  CLI flag required, though the CLI flag is the documented preferred method
  for bulk sync.
- Gujarat High Court has a single clean key in the HC bucket:
  `court=24_17/bench=gujarathc` — not fragmented across sub-benches the way
  some other states are.
- A real `metadata/parquet/year=2023/court=24_17/bench=gujarathc/metadata.parquet`
  exists and is directly fetchable (1.5MB for that one year/bench).
- India Code (`indiacode.nic.in`), the SC official search
  (`scr.sci.gov.in`), the Bharat Courts repo, and the Indian Kanoon API root
  are all reachable (HTTP 200).
- India Code returns HTML, not JSON — confirmed scrape-only, no API.

The probe scripts still need to independently verify and expand on these
(schema, full field list, per-year sizes, PDF vs. text availability) — this
section only establishes that the approach is viable.

## 4. Architecture

### 4.1 Project scaffold

Minimal slice of `PROJECT_STRUCTURE.md` §1 — just enough for recon scripts
to import shared code cleanly, not the full agent/graph tree:

``` text
legal-AI/
├── pyproject.toml
├── .env.example
├── src/
│   └── legal_ai/
│       ├── __init__.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── evidence.py       # Provenance/SourceRef — used by probes' reports
│       └── sources/
│           ├── __init__.py
│           └── licensing.py      # per-source licence/attribution facts, used by probes
├── scripts/
│   └── recon/
│       ├── __init__.py
│       ├── common.py             # shared probe report schema + polite-HTTP helpers
│       ├── probe_supreme_court_bulk.py
│       ├── probe_gujarat_hc_bulk.py
│       ├── probe_india_code.py
│       ├── probe_official_scr_search.py
│       └── probe_bharat_courts.py
├── data/
│   └── recon/                    # gitignored — sample files each probe downloads
└── docs/
    └── DATA_RECON_FINDINGS.md    # the deliverable
```

`schemas/evidence.py` is pulled forward from the full architecture (rather
than invented fresh for recon) because the probe report format should be the
same shape the real `Evidence`/`Provenance` objects will use later — no
throwaway schema to discard.

`sources/licensing.py` holds the known licence facts per source (CC-BY-4.0
for both Vanga corpora with attribution required, Indian Kanoon's
attribution-in-product requirement, India Code as government-primary with no
redistribution restriction implied). Probes read from it rather than
re-stating licence terms inline, so it's a single place to correct later.

### 4.2 Shared probe report schema (`scripts/recon/common.py`)

Every probe script returns the same shape, so the aggregator (§4.4) doesn't
need per-source parsing logic:

``` python
class ProbeReport(TypedDict):
    source: str                    # "supreme_court_bulk", "gujarat_hc_bulk", ...
    reachable: bool
    auth_required: bool
    access_method: str             # "public_s3_https", "html_scrape", "js_spa", "sdk", ...
    sample_fields: list[str]       # real field names observed, not assumed
    approx_volume: dict            # e.g. {"years": "1950-2026", "total_size_gb": 52.2}
    formats: list[str]             # ["pdf", "json", "parquet"]
    licence: str
    attribution_required: bool
    notes: list[str]               # anything surprising, broken, or worth flagging
    checked_at: str                # ISO timestamp
```

`common.py` also holds:
- A `polite_get()` wrapper — timeout, a real `User-Agent`, and a fixed
  delay between requests to the same host. The Vanga READMEs explicitly ask
  scrapers to be considerate; the India Code and SC portals are public
  government services, not built for scripted load.
- A `save_sample()` helper that writes any downloaded sample file to
  `data/recon/<source>/` and returns its path — probes report a path, not
  inline blobs.

### 4.3 Probe scripts

Each is a standalone `if __name__ == "__main__":` script — runnable
individually while developing, importable by an aggregator once all five
exist. Each **prints its `ProbeReport` as JSON to stdout** and also writes it
to `data/recon/<source>.json`.

**`probe_supreme_court_bulk.py`**
1. `GET` the bucket root listing; confirm `data/` and `metadata/` prefixes.
2. Fetch `dataset_sizes.csv` from the GitHub repo (not the bucket) for the
   documented per-year breakdown.
3. List `metadata/parquet/` to confirm the year-partitioned layout matches
   the README.
4. Download **one** `metadata.parquet` (a recent year) and read it with
   `pyarrow`/`pandas` — report the actual column names, not the ones
   guessed in `LEGAL_DATA_SOURCES.md` §5.
5. Download **one** sample PDF from `data/pdf/year=<recent>/english/` and
   confirm it's a real, openable, text-bearing PDF (not a scan requiring
   OCR — check via `pypdf` whether `extract_text()` returns non-empty
   content).
6. Report total corpus size and file count from the CSV/index files —
   without downloading the corpus.

**`probe_gujarat_hc_bulk.py`** — same five steps, scoped to
`court=24_17/bench=gujarathc` in the HC bucket. Additionally checks
`STATS.md` from the repo for the Gujarat-specific row, and lists every year
present for that court/bench to report actual coverage (the README's global
1950–present claim may not hold per-court).

**`probe_india_code.py`**
1. Confirm `GET /handle/123456789/1362` (Central Acts browse) returns HTML
   with a real Act listing.
2. Sample one Act's detail page (e.g. Specific Relief Act, 1963 — already
   used as a running example in `design/`) and report its DOM shape: is
   section text in the HTML directly, or behind a further click/PDF link?
3. Estimate total Act count from the browse page's pagination/count, if
   exposed.
4. Explicitly report `access_method: "html_scrape"` and flag that no JSON
   API exists, so this is never mistaken for one later.

**`probe_official_scr_search.py`**
1. `GET` the search page and inspect whether results are present in the
   initial HTML response or require JavaScript execution (look for an
   empty results container plus API calls in `<script>` tags, vs. a fully
   rendered results table).
2. If a same-origin XHR/API endpoint is visible in the page source, note its
   shape without calling it repeatedly.
3. Report clearly whether this source is scriptable at all in Phase 1, or
   whether it's realistically a "verify against this manually" source
   rather than a `Dynamic Researcher` tool target for now.

**`probe_bharat_courts.py`**
1. Attempt `pip install bharat-courts` (or the correct PyPI name — confirm
   it first; the repo may only support install-from-source) in an isolated
   step that cannot fail the whole recon run.
2. If installed, attempt one real, low-cost call (e.g. "recent Supreme
   Court judgments").
3. Report pass/fail plainly. This is the source most likely to need
   CAPTCHA/session handling per its own README — a clean failure report is
   a valid, useful outcome, not a bug in the probe.

### 4.4 Findings aggregation

A short script (`scripts/recon/aggregate.py`) reads every
`data/recon/*.json` report and renders `docs/DATA_RECON_FINDINGS.md` from a
template — one section per source, plus a summary table (source / reachable
/ format / approx size / licence / recommended Phase-1 role) and a final
"what this means for the ingestion pipeline" section that feeds directly
into the next spec.

The findings doc is generated, not hand-written, so it can be regenerated
if a probe is re-run later (these public sources sync daily per the HC
repo's GitHub Action).

## 5. Error handling

- **Per-probe isolation.** One source failing (Bharat Courts CAPTCHA-gated,
  say) must not stop the other four from running or from being aggregated.
  The runner script executes all five and collects whatever reports exist.
- **Network timeouts** are short (10–15s) with no silent hang — recon needs
  fast signal, not resilience.
- **No retries with backoff** for recon; a failed probe reports `reachable:
  false` with the error in `notes`. Retry logic belongs in the real
  ingestion adapters, not here.
- **Rate limiting is self-imposed**, not reactive — `polite_get()`'s fixed
  delay exists specifically so recon never becomes the kind of
  high-concurrency scraping both Vanga READMEs ask against.

## 6. Testing

Recon scripts are investigation tools, not product code, so testing stays
proportionate:

- A unit test on `common.py`'s `ProbeReport` schema and `polite_get()`'s
  retry/timeout behavior (mocked HTTP), since that logic is shared and
  reused later in real source adapters.
- No tests against the live network in CI — probes are run manually/locally
  and their *output* (the findings doc) is what gets reviewed and committed.
- `aggregate.py` gets a test with fixture JSON reports, to confirm the
  findings doc renders correctly regardless of which probes succeeded.

## 7. Success criteria

This task is done when `docs/DATA_RECON_FINDINGS.md` states, with evidence
(not the source docs' claims), for each of the five sources:

1. Reachable, and by what access method.
2. Real field/column names observed in actual sampled data.
3. Approximate volume (count, size) — from index/metadata files, never from
   downloading the corpus.
4. Format(s): PDF text-bearing vs. scanned, JSON, Parquet, HTML.
5. Licence and attribution obligation.
6. A one-line verdict: ready to build an ingestion adapter against now /
   needs more investigation / not viable for Phase 1.

That verdict per source is the direct input to the next spec: the actual
`ingestion/` pipeline and `knowledge/static/` store.
