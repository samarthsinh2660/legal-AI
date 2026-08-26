# Phase 5 --- Legal Analysis + Drafting

## Objective

> Can AI reason over the evidence, and turn that reasoning into a
> structured answer?

Phases 1--4 assemble research, documents, and case context. Phase 5 is
where all of it gets synthesized into an actual answer.

------------------------------------------------------------------------

## 1. Architecture

``` text
Research                (Phase 3)
    +
Case Documents           (Phase 4)
    +
Knowledge Graph          (Phase 1)
    |
    v
Analyst Agent
    |
    v
Legal Analysis
    |
    v
Draft Agent
```

------------------------------------------------------------------------

## 2. Analyst Agent

Receives results from all three research flows plus case documents.

``` text
Static Evidence
      +
Dynamic Evidence
      +
Active Evidence
      +
Case Documents
      |
      v
Analyst Agent
```

Answers: *what does all this evidence mean for this case?*

Responsibilities:

- Understand the legal question
- Compare evidence
- Identify relevant facts
- Identify legal issues
- Map facts to legal provisions
- Analyze precedents
- Identify conflicting authorities
- Identify missing information
- Build a structured case analysis

------------------------------------------------------------------------

## 3. Draft Agent

Converts verified analysis into a useful response.

For this phase it primarily generates:

- Legal research answers
- Case summaries
- Issue analysis
- Relevant-law explanations
- Evidence guidance
- Research summaries

Drafting formal pleadings, notices, and petitions is deferred to a later
phase, beyond Phase 7.

------------------------------------------------------------------------

## 4. Milestones

### Milestone 11

Analyst Agent.

### Milestone 12

Draft Agent.

------------------------------------------------------------------------

## 5. Deliverable

> AI can turn retrieved evidence + case facts into structured legal
> analysis.

------------------------------------------------------------------------

## 6. Explicitly not in this phase

``` text
Verification Agent             -> Phase 6
Active knowledge promotion     -> Phase 6
GraphRAG / precedent graph     -> Phase 7
Formal drafting (notices, petitions) -> beyond Phase 7
```

------------------------------------------------------------------------

## 7. What was built (2026-08-26)

### Milestone 11 --- Analyst Agent

`agents/analyst.py`. Retrieved provisions in, separate statements out, each
carrying the identifiers it rests on.

``` text
Claim("a promoter who misses possession must refund with interest",
      ("act:2158:sec-18",))
```

Three things `supervisor.summarise` did not do:

**It splits prose into individually attributable statements.** A summary
ending "Sources: a, b, c" cannot be verified, because nothing says which
sentence rests on which source. That is why the groundedness check built in
Phase 3 had never executed: `if not claims: return` on every single run.

**It validates every identifier against what was actually retrieved.** A
model asked to cite will sometimes emit a plausible id it never saw.
Unknown ids are dropped, which turns a fabricated citation into a visibly
unsupported claim. `AnalysisResult.dropped_ids` counts what the guard
caught -- the number worth watching when the model changes.

**It declines.** Given a question the corpus cannot answer it returns no
claims and says so. Verified live on three impossible questions ("penalty
under the Space Mining Regulation Act 2031"): zero claims, zero fabricated
ids, an explicit statement that the material does not cover it.

Cost is unchanged: this **replaces** the summarise call rather than adding
to it. One model call per question.

It deliberately does not check itself. `check_groundedness` does that with
no model, so the check cannot hallucinate. The Analyst produces; the
verifier judges.

### Milestone 12 --- a renderer, not an agent

`agents/draft.py`, 88 lines, no model call. Its inputs are already
structured, and handing structured data to a model to re-render would only
give it an opportunity to drop a citation.

Calling it a "Draft Agent" oversold it and the framing was wrong. What
earns its place is narrow: **it is the only place the verifier's finding
reaches the user.** Before it the node returned `"[stub answer for: ...]"`,
so a fabricated citation the verifier caught would have reached the reader
in the same font and with the same apparent confidence as a checked one.

Unsupported claims move into `needs_verification` rather than being
deleted -- a reader who cannot see that something was dropped cannot tell a
short answer from an incomplete one.

### Measured: does the model check help or hurt?

`evals/run_analyst.py`. Three objective numbers, no model grading a model:
share of claims grounded, share surviving the groundedness check, and
identifiers the model cited that were never in front of it.

Across four models, ~53 claims:

| model | claims | grounded | fabricated |
|---|---|---|---|
| gemini-3.5-flash-lite | 20 | 100% | 0 |
| gemini-3.6-flash | 8 | 100% | 0 |
| gemma-4-31b-it | 15 | 100% | 0 |
| gemini-flash-lite-latest | 14 | 100% | 0 |

**The citation guard has never fired.** It is ~10 lines and free at
runtime, and on this evidence it is insurance nobody has claimed on. Kept
because the failure it prevents -- a false citation in legal advice -- is
unrecoverable, but it has not yet earned its place and that should not be
claimed.

The more useful finding: `gemini-flash-lite-latest` produced **zero claims
on two of six questions** where every other model produced two to four,
from the same evidence and prompt. A real quality gap between models on the
same task, and the kind of thing that would silently halve answer quality
depending on where the chain landed. Visible only because the eval exists.

### The value claim is tested end to end

Unit tests covered the draft step in isolation; nothing proved that through
the *real* graph an unsupported claim reaches the reader labelled -- which
is the whole point of §12. Two tests now do, with a control:

``` text
fabricated claim -> full graph -> answer text
    "Could not be verified" present
    the claim text survives, not silently deleted
    the invented identifier absent -- not dressed up with a citation
    is_complete False

fully grounded run -> no warning section, is_complete True
```

The control is load-bearing: without it a graph printing the warning
unconditionally would pass the first test.
