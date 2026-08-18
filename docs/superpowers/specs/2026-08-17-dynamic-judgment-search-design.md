# Dynamic, Lazy-Cached Judgment Search — Design

**Status:** Approved (design only — no code written yet)

## Decision

Supersedes Milestone 2 of `docs/phases/PHASE_1_DATA_FOUNDATION.md` as
originally written ("bulk ingestion" of the full Supreme Court + Gujarat HC
corpus). Team decision (2026-08-17): the static knowledge graph covers
**Acts, Sections, and the Penal Codes only** (India Code — already done,
845/846 Acts including the Bharatiya Nyaya Sanhita 2023 and Bharatiya
Nagarik Suraksha Sanhita 2023). Supreme Court and High Court judgments are
**not** bulk-ingested ahead of time.

**Scope broadened from "Gujarat HC" to any state High Court** (team
decision, same day): under bulk ingestion, picking one state HC first made
sense — it bounded how much had to be downloaded and verified up front.
Under lazy-cached dynamic search, nothing is downloaded until a real query
needs it, so hardcoding a single state would just mean redoing this design
the moment a case from another state comes up. The source for this is
Bharat Courts (`iamshouvikmitra/bharat-courts`, multi-state HC coverage),
not the original Gujarat-specific Vanga bucket.

## Why not bulk ingestion

The Vanga Supreme Court bulk corpus is ~35,000 English judgments, ~52GB.
Committing to ingesting all of it now, before the harness has proven which
sectors/queries actually need case law, is exactly the kind of speculative
work this project has otherwise avoided (see: the real-estate-first pilot
approach, not "ingest everything then figure out what's useful").

## Why not pure dynamic (fetch, never store)

Considered and rejected: re-fetching and re-parsing a judgment from
scratch on every query is slow, and — more importantly — it throws away
the graph. `CITES` edges, cross-judgment relationships, and "we've
verified this text passed the gate" only accumulate if something gets
stored the first time it's found. Pure ephemeral search would mean the
knowledge graph never grows from real usage.

## The approach: lazy-cached dynamic search

Already proven manually for a real case during the real-estate pilot
(`judgment:sc-2026-ca-6936-2023`, *M/S. Kabra And Associates & Ors. v.
Rekha Rajkumar Hemdev & Ors.*) — this design formalizes that pattern into
a reusable tool.

**Flow, per judgment lookup:**
1. Check the DB first (`get_document` / `search`) — if it's already there,
   done, no network call.
2. If not found, search live sources in order:
   a. For Supreme Court cases: the validated Vanga SC bulk archive
      (`metadata/parquet/year=YYYY/`) — real primary source, but has a
      coverage gap (2026 data currently starts 01-04-2026; earlier
      judgments in the current year may be missing).
   b. For any state High Court case: Bharat Courts
      (`iamshouvikmitra/bharat-courts`) — **not yet probed**; needs the
      same one-time recon treatment every other source in this project
      got (`scripts/recon/probe_*.py` pattern) before first real use, to
      confirm its real schema, reachability, and licence, the same way
      the Vanga buckets were confirmed in Milestone 0.
   c. Indian Kanoon, as a universal fallback for anything not yet in
      either bulk archive — a real, public case-law aggregator, not an
      official government source, so it must be labeled as such in
      provenance (matches how the Kabra judgment was already labeled).
3. Whatever is found goes through the same `verify_batch` Source
   Verification Gate already used for India Code — not a lighter bar.
4. On pass: store via `upsert_document` + `embed`, write graph edges via
   `write_judgment` (citations extracted via the existing
   `extract_citations`), exactly like every other document in this
   project.
5. On failure to find anything from any source: report that plainly to
   the caller — no fabrication, same discipline as the India Code work.

**What this looks like as a skill tool:** a new subcommand on
`scripts/legal_search.py` (or a sibling script) — e.g.
`search-judgment "<case name or citation>"` — that runs this flow and
returns the same JSON shape as the existing `search`/`get` commands, so
the `legal-data-retrieval` skill can use it the same way.

## Scope boundary

- Any state HC via Bharat Courts: same lazy-cached approach — a
  particular state's case is only fetched when a real harness query
  actually needs it, not pre-downloaded for any state speculatively.
- The official SC search portal (`scr.sci.gov.in`) remains explicitly
  out of scope — it is CAPTCHA-protected and this project does not build
  CAPTCHA-solving tooling, regardless of source priority ordering. The
  bulk archive and Indian Kanoon are sufficient real, accessible sources.

## Out of scope for this doc

- Probing Bharat Courts (needs its own recon pass before the tool can
  rely on it — same discipline as every other source this project uses).
- Building the actual tool (a follow-up implementation task, likely via
  `writing-plans` given it touches the graph writer and verification
  gate — real production code, not a disposable script).
- Deciding which sector comes after real estate.
