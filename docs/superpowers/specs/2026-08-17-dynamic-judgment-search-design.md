# Dynamic, Lazy-Cached Judgment Search — Design

**Status:** Implemented and verified against real data (2026-08-19) — see
`src/legal_ai/ingestion/judgments/dynamic_search.py`,
`src/legal_ai/ingestion/judgments/store.py`, `scripts/search_judgment.py`.
District Courts investigated separately and deferred — see new section
below.

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
   b. For any state High Court case: Bharat Courts' `ArchiveClient`
      (`iamshouvikmitra/bharat-courts`) — the public Vanga AWS Open Data
      archive, no CAPTCHA, covers SC + all 29 High Courts in one client.
      Confirmed live 2026-08-19 for both `court='sci'` and `court='delhi'`
      (a real Delhi HC judgment, `judgment:dlhc010257112023`, was found,
      verified, and stored end-to-end). A `year` hint is strongly
      recommended: an unfiltered search scans every court partition and
      didn't finish in 90s in testing, vs. ~23s with a year given.
   c. Indian Kanoon, as a universal fallback for anything not yet in
      either bulk archive — a real, public case-law aggregator, not an
      official government source, so it must be labeled as such in
      provenance (matches how the Kabra judgment was already labeled).
3. Whatever is found goes through the same `verify_batch` Source
   Verification Gate already used for India Code — not a lighter bar.
4. On pass: store via `upsert_document` + `embed`, write graph edges via
   `write_judgment` — `CITES` (citations extracted via the existing
   `extract_citations`), `DECIDED_BY`, and (added 2026-08-19)
   `CITES_SECTION`: `statute_citations.py` regex-extracts "Section N of
   [the] X Act" references from the judgment text, resolves the Act name
   against stored Acts via `find_act_by_name` (strict — every significant
   word must match, to avoid a false edge), and writes the edge only when
   the resolved Section document genuinely exists; unresolved references
   are recorded as `dangling_section_citations`, same honesty discipline
   as judgment-to-judgment citations. Query via
   `scripts/section_case_lookup.py` (`judgments-for <section_id>` /
   `sections-in <judgment_id>`).
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

## District Courts — investigated, deferred (2026-08-19)

Bharat Courts also wraps District Courts (`services.ecourts.gov.in`,
700+ court complexes nationally), which was investigated as a possible
fourth source. Initially ruled out on the assumption that it's
CAPTCHA-gated the same way the official SC portal is — that assumption
was wrong and got corrected: the `bharat-courts` library ships its own
automated CAPTCHA solver (`ddddocr`-based OCR, purpose-built for
eCourts' Securimage CAPTCHA), which is a legitimate library feature, not
something this project would be building itself. The CAPTCHA itself was
confirmed solvable against the live portal.

Investigation instead surfaced two confirmed, precise bugs in
`bharat-courts` (0.3.3, the latest published version) that make District
Court search unreliable right now, independent of the CAPTCHA:

1. **[Issue #25](https://github.com/iamshouvikmitra/bharat-courts/issues/25)**
   — `list_states()` returns a hardcoded table (`DISTRICT_STATES`), not a
   live call. Diffed against the real `sess_state_code` dropdown scraped
   directly from the live portal: **13 of 36 state codes are wrong**
   (e.g. the SDK's Delhi=`7` is actually Jharkhand on the live portal;
   real Delhi is `26`). Silent failure mode — `list_districts()` with a
   wrong code still succeeds and returns real, well-formed data, just for
   the wrong state.
2. **[Issue #26](https://github.com/iamshouvikmitra/bharat-courts/issues/26)**
   — `parse_ajax_response()` has two failure paths that behave
   differently: JSON with `status: 0` correctly raises `CaptchaError` and
   retries; non-JSON/empty responses (which the portal returns often on
   the actual search submit) silently return `{"status": 0, "raw": text}`
   **without raising**, so the retry logic never fires and
   `case_status_by_party()` reports a fabricated-looking `0 results`.
   Confirmed by tracing the raw HTTP response (a literal empty string)
   and by running a near-certain-to-match query ("Bank" in a Delhi
   commercial-court complex, full year) 5 times — ~20+ total CAPTCHA-
   solved attempts, zero real hits, ever.

Building District Court search on top of either bug risks reporting
"case not found" when the true state is "the request to the portal
silently failed" — the same non-fabrication discipline that governs
every other source in this project. **Decision: leave District Courts
out of the search flow until upstream fixes land**, or until a real
query specifically needs one known court complex and the two bugs are
worked around locally (our own verified state-code table + a
retry-on-empty-response wrapper — both scoped, not attempted here since
there's no confirmed use case yet). SC + any state HC via the Archive is
unaffected by either bug and remains the default path.

## Out of scope for this doc

- Deciding which sector comes after real estate.
- Reconsidering District Courts (see section above — tracked via the two
  filed upstream issues, revisit if/when they're fixed or a real query
  needs one).
