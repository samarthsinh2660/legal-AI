# Phase 6 --- Verification + Active Learning

## Objective

> Can we make the system trustworthy, and let it improve without
> compromising that trust?

Phase 5 produces an answer. Phase 6 checks it before a user sees it, and
turns usage into learning without ever letting that learning silently
become law.

------------------------------------------------------------------------

## 1. Verification Agent

Every important generated legal claim is checked before the answer ships.

``` text
Generated Claim
      |
      v
Find supporting authority
      |
      v
Verify source
      |
      v
Verify cited section / paragraph
      |
      v
Check precedent status
      |
      v
Check jurisdiction/date
      |
      +----> unsupported -> research again
      |
      v
Approved claim
```

The verifier detects:

- Hallucinated cases
- Wrong citations
- Unsupported propositions
- Misinterpretation of a section
- Outdated authorities
- Conflicting judgments
- Wrong jurisdiction

This is distinct from the **Source Verification Gate**
(`DATA_LAYER_ARCHITECTURE.md` §4), which runs once per ingested batch in
Phase 1, before data ever enters the static store. The Verification Agent
here runs per generated *answer*, at query time, checking the claims that
answer makes against evidence already in the system.

------------------------------------------------------------------------

## 2. Active Learning Loop

The **write side** of the active layer -- the Active Researcher's read
side (retrieving already-validated patterns) is Phase 3, not here.

### Signals

``` text
Repeatedly useful citations
Repeated research paths
User feedback
Corrections
Verification results
Frequently retrieved authorities
Frequently associated sections
```

### Flow

``` text
Research interaction
       |
       v
Observation
       |
       v
Candidate knowledge
       |
       v
Validation
       |
       v
Confidence + provenance
       |
       v
Approved active knowledge
```

**Critical rule, carried from `DATA_LAYER_ARCHITECTURE.md` §12:** no
automatic promotion to authoritative static knowledge is allowed. A
frequently used citation does not become legally correct simply because
users use it often. Promotion requires evidence and validation, run by a
human-reviewable validation pipeline, not usage counts.

------------------------------------------------------------------------

## 3. Milestones

### Milestone 13

Citation Verification Agent.

### Milestone 14

Active knowledge validation and promotion pipeline
(`src/legal_ai/knowledge/active/` per `PROJECT_STRUCTURE.md` §9).

------------------------------------------------------------------------

## 4. Deliverable

> Every answer's claims are checked before the user sees them, and the
> system can learn from usage without usage ever becoming legal authority
> on its own.

------------------------------------------------------------------------

## 5. Explicitly not in this phase

``` text
GraphRAG / precedent graph          -> Phase 7
Conflicting-precedent reasoning     -> Phase 7
Indian legal benchmarks             -> Phase 7
```
