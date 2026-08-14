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
