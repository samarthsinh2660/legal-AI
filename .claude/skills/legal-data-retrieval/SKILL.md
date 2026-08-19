---
name: legal-data-retrieval
description: Use when answering any question about Indian Central Acts/Sections, or Supreme Court/High Court judgments. Retrieves real, verified data from the project's own database instead of relying on trained-in knowledge, which may be outdated, incomplete, or wrong for legal text.
---

# Legal Data Retrieval

Answer legal questions using **real, ingested or freshly-verified data** —
never from memory or general knowledge. This project has:

- Scraped and verified 860 real India Code Central Acts (845 regular +
  14 Spent Acts) and their ~35,600 Sections into a database.
- A working fetch-verify-store pipeline for Supreme Court and any state
  High Court judgment: given a case name or citation, it checks the
  database first, then searches the Bharat Courts archive and Indian
  Kanoon live, verifies whatever it finds, and stores it — so a judgment
  you ask about may already be there, or get added for real, on demand.

Your job is to retrieve from this, not to recall or guess.

## Why this matters

Legal text is exact: a wrong word, wrong section number, or wrong Act
changes the answer's correctness entirely. Trained-in knowledge can be
outdated (Acts get amended), incomplete (this corpus may have text a
general model was never trained on), or simply wrong. If you answer
without using these tools, you are guessing — say so explicitly rather
than presenting a guess as verified fact.

## Tools

All commands are run via Bash: `.venv/bin/python -m scripts.legal_search <subcommand> ...`
(run from the repository root). Every subcommand prints JSON.

- `search "<query>" [--limit N]` — semantic search over every ingested
  document (Acts, Sections, and any already-stored Judgments). Use this
  first when you don't already know the exact document id — it finds
  documents whose *meaning* is close to the query, ranked by distance
  (lower = closer).
- `get <document_id>` — fetch a document's exact stored record, including
  its real `full_text` and the original `source_url` it came from. Use
  this after `search` to get the actual text to quote/answer from — never
  answer from `search`'s title alone.
- `act-sections <act_id>` — list every Section a real Act contains (via
  the knowledge graph's `CONTAINS` relationship). Use this for "what does
  this Act cover" or "list the sections of X" questions.
- `search-judgment "<case name or citation>" [--year YYYY]` — find,
  verify, and store a real Supreme Court or High Court judgment. Checks
  the database first (no network call if already there); if not, searches
  the Bharat Courts archive (covers SC + any state HC) then Indian Kanoon
  as a fallback, verifies the result, and stores it for future lookups.
  `--year` is strongly recommended — without it the underlying search can
  be much slower. Prints `{"found": false}` (exit code 1) if nothing real
  turns up anywhere — do not fabricate a judgment when this happens.
- `citations <judgment_id>` — list Judgments a given Judgment cites (via
  the graph's `CITES` relationship, resolved from real reporter citations
  like "(2019) 8 SCC 729" found in its text). Only resolves to a citation
  if the cited judgment is *also* stored in this database — an empty list
  can mean either "cites nothing" or "cites things not yet stored here,"
  not necessarily "cites nothing at all."
- `section-citations <section_id>` — list Judgments that cite a given Act
  Section (via the graph's `CITES_SECTION` relationship, resolved from
  references like "Section 18 of the Real Estate (Regulation and
  Development) Act, 2016" found in judgment text). Use this for "which
  cases have applied this section" questions.
- `judgment-sections <judgment_id>` — the reverse: list the Act Sections a
  given Judgment cites. Use this for "what statutory provisions did this
  case turn on" questions.

## Workflow

1. For statute questions, if you don't know the exact `document_id`,
   start with `search`. For a specific judgment you know the name/citation
   of, use `search-judgment` directly instead — it's verify-and-store,
   not ranked search, so give it your best single query rather than
   treating it like `search`.
2. Take the most relevant result(s) and call `get` (or read
   `search-judgment`'s own output directly, it already includes
   `full_text`) — this is what you quote from, never a search title alone.
3. For "what sections does this Act have" style questions, use
   `act-sections` directly with the Act's `document_id`.
4. For "which cases apply this section" or "what did this case turn on"
   questions, use `section-citations` / `judgment-sections`.
5. Always cite the `document_id` and `source_url` in your answer, so the
   claim is traceable back to a real, verifiable source.
6. If the tools return nothing relevant (or `search-judgment` returns
   `{"found": false}`), say so plainly — do not fall back to unverified
   general knowledge and present it as if it came from this database.

## Known limitations (real, not hidden)

- Not every Section has real body text yet — a small number of Acts are
  still being backfilled (see
  `docs/superpowers/specs/2026-08-15-section-body-fetch-design.md`). If
  `get` returns an empty `full_text` for a real section, say that plainly
  rather than inventing content.
- Judgments are lazy-cached, not bulk-ingested — the database only has
  judgments someone has already looked up via `search-judgment`. A
  judgment not yet in the database is not "not real," it just hasn't been
  fetched yet; `search-judgment` will fetch it live if it exists.
- `citations`/`section-citations`/`judgment-sections` only resolve edges
  between documents *already stored* in this database — a real citation
  to something not yet stored won't show up as an edge. This is an
  honest gap, not a fabrication risk: it undercounts, it never invents.
- District Court data is deliberately not available through this skill
  yet — investigated and found to depend on two confirmed bugs in the
  underlying `bharat-courts` library (wrong state codes; search failures
  silently reported as "0 results" — filed as
  [bharat-courts#25](https://github.com/iamshouvikmitra/bharat-courts/issues/25)
  and [#26](https://github.com/iamshouvikmitra/bharat-courts/issues/26)).
