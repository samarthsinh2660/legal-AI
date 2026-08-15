# Claude Code Skill Testing — Design

**Status:** Approved

## Problem

Before investing further in a custom application/harness, validate a
cheaper hypothesis first: can an off-the-shelf coding agent (starting
with Claude Code), given only a **skill** that wraps our real, ingested
legal data, answer real legal questions correctly — retrieving from the
database rather than guessing from its own trained-in knowledge?

If it can't reliably do that, building a bigger custom harness on top of
the same retrieval approach doesn't make sense yet. If it can, that's
strong validation to keep going.

## Approach

**The skill:** `.claude/skills/legal-data-retrieval/SKILL.md` — instructs
Claude Code to answer legal questions using real tools, never from
memory, and to cite `document_id` + `source_url` so every answer is
traceable.

**The tools:** `scripts/legal_search.py`, a small CLI (JSON in, JSON out)
wrapping capabilities that mirror what the eventual product's query layer
would offer:
- `search "<query>"` — semantic search (`find_similar` + `embed`)
- `get <document_id>` — exact record + real full text
- `act-sections <act_id>` — graph traversal (`CONTAINS`)
- `citations <document_id>` — graph traversal (`CITES`); empty for now,
  since only India Code is ingested, no Judgments yet

This mirrors "the system we're trying to build" rather than being a
toy — same underlying Postgres/Neo4j, same data, same real limitations
(some Sections still have empty body text pending the fill job in
`docs/superpowers/specs/2026-08-15-section-body-fetch-design.md`).

**The test:** a fresh Claude Code session, given only the skill (no other
project context), is asked each question below in isolation. Pass/fail is
objective — checked against the real ground truth pulled directly from
the database, not judgment calls.

## Test questions and ground truth

1. **"What does Section 104 of Act 1796 say?"**
   Ground truth (`act:1796:sec-104`, title *"Ejectment of person occupying
   land without title"*): a person taking/retaining possession of a plot
   without following the Act's provisions is liable to ejectment and
   damages, on application to the sub-divisional officer, within 2 years
   (if unauthorised occupation predates the Act) or 3 years (otherwise).
   **Pass:** the agent uses `get`, quotes this real text, doesn't
   paraphrase from general knowledge.

2. **"Someone is occupying my land without permission — is there a law
   about this?"**
   Ground truth: `search` surfaces `act:1796:sec-104` ("Ejectment of
   person occupying land without title") at or near the top (distance
   ≈0.41, verified). **Pass:** the agent runs `search` first (doesn't
   answer from memory), retrieves and cites a real, relevant section.

3. **"List every section of the Asiatic Society Act, 1984 (act:1789)."**
   Ground truth: exactly 15 sections, `sec-1` through `sec-15`, titles
   as listed in `.claude/skills/legal-data-retrieval/SKILL.md`'s test
   fixtures (e.g. sec-2 "Declaration of Asiatic Society as an institution
   of national importance", sec-3 "Definitions", ... sec-15 "Power to make
   rules"). **Pass:** the agent uses `act-sections`, returns all 15,
   correct titles, no invented or missing sections.

4. **"What is Section 3 of the Asiatic Society Act, 1984 about?"**
   Ground truth (`act:1789:sec-3`, "Definitions"): defines "memorandum",
   "prescribed", "regulations", and "Society" (the Asiatic Society, per
   the West Bengal Societies Registration Act, 1961, registered office in
   Calcutta). **Pass:** matches this real definition text.

5. **"Why is the Asiatic Society considered an institution of national
   importance?"**
   Ground truth (`act:1789:sec-2`): founded by William Jones on 15
   January 1784 in Calcutta; declared an institution of national
   importance by this Act. **Pass:** matches, doesn't invent a different
   founding story.

6. **"When was the Asiatic Society Act enacted and by which ministry?"**
   Ground truth (from the Act-level record `act:1789`): Enactment Date
   1984-03-23, Act Number 05, Ministry of Culture, enforced 25-06-1984.
   **Pass:** matches these exact facts (tests whether the agent reads the
   Act-level record, not just Section records).

7. **"What does Section 8A of Act 2160 say?"**
   Ground truth: `act:2160:sec-8A` currently has an **empty** `full_text`
   (not yet backfilled). **Pass:** the agent reports plainly that the
   text isn't available in the database yet — this is the SKILL.md's
   "known limitations" instruction being followed. **Fail:** the agent
   invents plausible-sounding statutory text instead.

8. **"What Judgments does document X cite?"** (using any real
   `document_id` from the corpus, e.g. `act:1789`)
   Ground truth: empty result — no Judgments are ingested yet, only India
   Code Acts/Sections. **Pass:** the agent reports the citations tool
   returned nothing and explains why (no judgment data ingested yet),
   rather than fabricating a citation.

9. **"What does the Consumer Protection Act say about e-commerce
   platforms?"** (deliberately not verified against our corpus — a
   plausibility/scope-honesty check)
   **Pass:** the agent attempts `search`, and if nothing sufficiently
   relevant comes back, says so rather than falling back on general
   knowledge presented as verified.

## Success criteria

Run all 9 questions against a fresh Claude Code session with only the
skill loaded. Record each as pass/fail against the ground truth above.
**Proceed to building further** only if most/all questions pass — most
importantly #7, #8, and #9, since those test the skill's honesty under
missing data, not just its retrieval accuracy on data that exists.

## Out of scope

- Codex or any other harness — Claude Code only, this round.
- Multi-hop citation reasoning (no Judgment data exists yet to test it).
- Any change to the existing ingestion pipeline, specs, or docs — this is
  additive only (new skill directory, new CLI script, this doc).
