# India Code Section Body Fetch — Design

**Status:** Approved (pilot scope)

## Problem

The 845-Act India Code ingestion (see
`docs/superpowers/plans/2026-08-15-ingestion-core-india-code-plan.md`)
stored 35,386 real Sections, but every Section's `full_text` is empty.
India Code loads section body text client-side via JavaScript, which the
original scraper (a plain HTTP fetch) never executes.

## Discovery

Live inspection of the real site found the actual mechanism:

- Each Act page's section link carries an `actid` (the Act's internal
  DSpace item id, e.g. `AC_CEN_37_85_00001_201618_1517807328460`) and a
  numeric `sectionId` (e.g. `3579`) in its `href` query string.
- The real body text comes from a separate endpoint:
  `GET /SectionPageContent?actid=<actid>&sectionID=<sectionId>`,
  returning JSON: `{"content": "<html fragment>", "footnote": "<html fragment>"}`.
- Confirmed against a real section (Aadhaar Act, Section 1): returns the
  real statutory text plus its amendment footnotes.

## Approach

**Resumability by construction, not by tracking state.** The unit of work
is *"Sections currently in Postgres with an empty `full_text`"* — a
query, not a separate progress log. A crash mid-run loses only time, not
progress: re-running picks up exactly where it left off, and a
successfully-filled Section is simply excluded from the next run's query.
This directly applies the lesson from the original ingestion run, where
an all-or-nothing batch design lost 100% of progress to one SSL timeout.

**Flow, per Act:**
1. Query Postgres for empty-body Sections, grouped by `act_id`, joined to
   that Act's already-stored `provenance.source.url`.
2. Fetch the Act's page once (reusing `legal_ai.sources.http.polite_get`,
   which already retries transient failures) and extract each Section's
   `actid` + `sectionId` from its link — a new, small parser helper. This
   does **not** modify `parse_act`, whose contract is already tested and
   consumed elsewhere; the new helper does its own independent
   `BeautifulSoup` pass over the same HTML.
3. For each of that Act's empty Sections: call `SectionPageContent`,
   strip the returned HTML fragments (`content` + `footnote`) to plain
   text via `BeautifulSoup(...).get_text(" ", strip=True)`, join them
   with a blank line.
4. Update the Section's row through the existing
   `legal_ai.knowledge.static.store.upsert_document` — this recomputes
   `content_hash` and, since `full_text` is no longer empty, generates a
   real embedding this time (the original run stored `embedding=None` for
   empty Sections).
5. Per-section failures (network, missing ids) are logged and skipped,
   not fatal — the Section just stays empty and is retried on the next
   run.

## Scope

**Pilot only, this round:** run against a single real Act (a few dozen
Sections, ~1-2 minutes) to verify (a) the `actid`/`sectionId` extraction
is correct, (b) the fetched text looks right, and (c) re-running is a
true no-op (nothing left empty, no duplicate work). The pilot script is
disposable — not part of the permanent codebase.

**Explicitly deferred, pending pilot results:** the full run over all
35,386 Sections (~10 hours at the existing 1 req/sec/host rate limit).
That decision, and whether it needs a production script (with tests,
following the `writing-plans` TDD process like the original ingestion
plan), is made after the pilot, not now.

## Testing

The pilot itself is the test for this round — run it against one real
Act and inspect the result directly (DB row before/after, text content,
no HTML tags leaking through, idempotent re-run). No new production
code/tests are written until the full run is decided on.

## Out of scope

- The full 35k-section production run and its script (future decision).
- Any change to the original `ingest_india_code` pipeline or its tests.
- Anything related to the deferred Supreme Court / Gujarat HC ingestion.
