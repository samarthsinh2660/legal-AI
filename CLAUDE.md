# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Project conventions — Pramāṇa AI

Learned on this codebase. These are specific to it and outrank the generic
advice above where they conflict.

## 1. Docstrings carry the decision, not the code

Every module explains *why* it is the way it is, usually with the
measurement or the failure that settled it. `bench.py` says why it is a
regex and not a model call. `type_floor.py` carries the MRR numbers that
justify interleaving. Comments that restate the code are noise; comments
that record why an alternative was rejected are the point.

When you change behaviour on evidence, put the evidence in the docstring
with its date.

## 2. "We could not check" is never "we checked and it is fine"

The signature defect of this system is silent degradation, and every
subsystem has an explicit third state to prevent it:

```
verification   UNSUPPORTED  vs  INSUFFICIENT_EVIDENCE
treatment      OVERRULED    vs  NOT_CHECKED
conflict       CONFLICT     vs  NOT_CHECKED
good law       DOUBTED      vs  NOT_CHECKED
```

A check that could not run must never render like a check that passed.
Failing closed means falling to the state that withholds reassurance, not
the state that is easiest to code.

## 3. Never claim more than the corpus supports

The corpus is a fraction of Indian law. Reader-facing text says *"no
negative treatment among the N judgments citing it that we hold"*, never
"good law". Where a count is a statement about our shelf rather than about
the law, say so in the same sentence.

## 4. Deterministic before model

Reach for a lookup, a regex or the source's own metadata first; a model
last. Two examples worth knowing: the law reporter prints its own treatment
table, which beat the model outright and cost nothing; bench composition is
a regex over the header, because a *wrong* bench size silently reorders
authority while a missing one does not.

A model may only be trusted with a label after it has been measured on that
label. The treatment classifier is barred from returning OVERRULED for
exactly this reason.

## 5. Build for a caller that exists

Most of Phase 7 has no automatic caller and needs no config switch. Only
behaviour that changes every answer gets a flag, and the flag's default is
set by measurement, with the numbers in `settings.py`.

## 6. Tests

Test files are named for what they cover, never for a phase or milestone.
They live in `tests/<package>/` mirroring `src/legal_ai/`, except
`tests/common/` for tests whose assertions are about the seam between two
subsystems; those name the domains they span in their first lines.

Write the failing test first and run it. The full suite takes ~45 minutes
and needs Postgres and Neo4j on `localhost:5433` / `7688`.

## 7. Long-running work

Corpus jobs run for hours. Start them detached, wait on the PID, and never
hold a database transaction open across a model call — doing so once queued
an `ALTER TABLE` behind it and froze every reader for half an hour.

## 8. Git

The user handles all git operations. Do not commit unless explicitly asked,
and never add a `Co-Authored-By` line.
