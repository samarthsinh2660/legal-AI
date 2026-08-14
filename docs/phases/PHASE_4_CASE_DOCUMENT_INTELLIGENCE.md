# Phase 4 --- Document + Case Intelligence

## Objective

> Can AI understand *this user's* case, not just Indian law in general?

Phases 1--3 make the system able to research Indian law. Phase 4 introduces
the user's own material -- uploaded documents and the persistent case that
holds them -- as a second kind of evidence alongside research.

------------------------------------------------------------------------

## 1. Architecture

``` text
                  Case
                   |
             Document Agent
                   |
       Facts / Parties / Dates /
       Issues / Claims / Evidence
                   |
             Research Agent        (Phase 3)
                   |
              Case Agent
```

------------------------------------------------------------------------

## 2. Document Agent

Understands uploaded legal documents:

``` text
PDF / DOCX
    |
    v
Document Agent
    |
    +--> Parties
    +--> Facts
    +--> Dates
    +--> Clauses
    +--> Sections
    +--> Claims
    +--> Issues
    +--> Contradictions
```

Handles:

- petitions
- notices
- agreements
- judgments
- orders

Its output becomes evidence for the Analyst Agent (Phase 5).

------------------------------------------------------------------------

## 3. Case Agent

Operates at the case level, combining documents, research, and legal
knowledge:

``` text
Documents
   +
Research
   +
Legal Knowledge
   |
   v
Case Agent
   |
   +--> Timeline
   +--> Facts
   +--> Issues
   +--> Arguments
   +--> Applicable law
   +--> Precedents
   +--> Missing facts
```

The Case Agent is therefore different from the Document Agent:

> Document Agent = understands documents.

> Case Agent = understands the legal case using documents + research.

### A case is a container, not a question

A **research session** (Phase 3) answers one question. A **case** is a
persistent workspace that accumulates everything about one real legal
matter:

``` text
CASE
 |
 +-- Case details (number, court, jurisdiction)
 +-- Parties
 +-- Documents
 +-- Timeline
 +-- Issues
 +-- Research sessions        <-- many
 +-- Authorities
 +-- Arguments
 +-- Notes
```

One case therefore contains **many** research sessions:

``` text
Case: Patel v. Shah
       |
       +-- Research: "Can adverse possession apply?"
       +-- Research: "What proves ownership?"
       +-- Research: "Relevant Gujarat HC judgments"
       +-- Research: "Limitation period"
```

A research session may exist with no case at all. When it is attached to
one, its thread context (`AI_PROJECT_PROPOSAL.md` §6) is seeded from the
case -- parties, established facts, prior findings -- which is exactly what
lets the Case Agent answer questions the Research Agent cannot:

``` text
"Based on the documents in this case and the authorities we have
 researched, what are the key legal issues?"

"Which facts in our documents support the ownership claim?"

"Which cases are most relevant to our facts?"
```

Two entry points must both be supported:

``` text
Flow A                          Flow B
------                          ------
New research                    Create case
   |                               |
Ask question                    Enter case information
   |                               |
Get answer                      Upload documents
   |                               |
Save to case                    Case workspace
   |                               |
Choose existing / create new    Start research
```

------------------------------------------------------------------------

## 4. Milestones

### Milestone 9

Document Agent.

### Milestone 10

Case Agent.

------------------------------------------------------------------------

## 5. Deliverable

> AI understands both Indian law AND the user's particular case.

------------------------------------------------------------------------

## 6. Explicitly not in this phase

``` text
Analyst Agent / Draft Agent    -> Phase 5
Verification Agent             -> Phase 6
Active knowledge promotion     -> Phase 6
GraphRAG / precedent graph     -> Phase 7
```
