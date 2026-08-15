---
name: legal-data-retrieval
description: Use when answering any question about Indian Central Acts or their Sections. Retrieves real, verified data from the project's own database instead of relying on trained-in knowledge, which may be outdated, incomplete, or wrong for legal text.
---

# Legal Data Retrieval

Answer legal questions using **real, ingested data** — never from memory or
general knowledge. This project has scraped and verified 845 real India
Code Central Acts and their Sections into a database; your job is to
retrieve from it, not to recall or guess.

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

- `search "<query>" [--limit N]` — semantic search. Use this first when you
  don't already know the exact document id — it finds Sections/Acts whose
  *meaning* is close to the query, ranked by distance (lower = closer).
- `get <document_id>` — fetch a document's exact stored record, including
  its real `full_text` and the original `source_url` it came from. Use
  this after `search` to get the actual text to quote/answer from — never
  answer from `search`'s title alone.
- `act-sections <act_id>` — list every Section a real Act contains (via
  the knowledge graph's `CONTAINS` relationship). Use this for "what does
  this Act cover" or "list the sections of X" questions.
- `citations <document_id>` — list Judgments a given Judgment cites (via
  the graph's `CITES` relationship). Only meaningful for `judgment`-type
  documents; the current corpus is India Code only, so this will return
  an empty list for now.

## Workflow

1. If you don't know the exact `document_id`, start with `search`.
2. Take the most relevant result(s) and call `get` to retrieve the real
   `full_text` — this is what you quote from, not the search title.
3. For "what sections does this Act have" style questions, use
   `act-sections` directly with the Act's `document_id`.
4. Always cite the `document_id` and `source_url` in your answer, so the
   claim is traceable back to a real, verifiable source.
5. If the tools return nothing relevant, say so plainly — do not fall
   back to unverified general knowledge and present it as if it came from
   this database.

## Known limitations (real, not hidden)

- Not every Section has real body text yet — some Acts are still being
  backfilled (see `docs/superpowers/specs/2026-08-15-section-body-fetch-design.md`).
  If `get` returns an empty `full_text` for a real section, say that
  plainly rather than inventing content.
- Only India Code Central Acts are in this corpus right now — no Supreme
  Court or High Court judgments yet, so `citations` will be empty.
