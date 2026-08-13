# Phase 1 --- Indian Legal Research & Case Analysis AI

## Objective

Build a focused AI system that can answer Indian legal questions by
combining:

-   A trusted static legal knowledge base
-   Dynamic research over court and legislation sources
-   An initial active-learning/evidence layer
-   Legal analysis
-   Citation verification

The Phase 1 product is a **legal research and case-analysis chatbot**,
not a full legal platform.

------------------------------------------------------------------------

## 1. Phase 1 Scope

``` text
                    USER QUESTION
                          |
                          v
                   Query Analyzer
                          |
                          v
              THREAD CONTEXT BUILDER
                          |
             (built once, passed read-only
              to every agent below)
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
       STATIC          DYNAMIC          ACTIVE
      RESEARCH        RESEARCH         RESEARCH
          |               |               |
          +---------------+---------------+
                          |
                          v
                    ANALYST AGENT
                          |
                          v
                     DRAFT AGENT
                          |
                          v
                VERIFICATION AGENT
                          |
                          v
                    FINAL ANSWER
```

Every agent in this diagram is initialized with the **shared thread
context** defined in `AI_PROJECT_PROPOSAL.md` §6 — the normalized question,
jurisdiction, case facts, active documents and findings already established
in this thread. No agent re-derives that understanding for itself.

------------------------------------------------------------------------

## 2. Static Research Flow

The static flow contains high-confidence information that can be reused
across legal questions.

### Initial data

``` text
Constitution
India Code
Acts
Sections
Rules
Regulations
High-confidence Supreme Court judgments
Selected High Court judgments
Verified citations
```

### Pipeline

``` text
Source
  |
  v
Ingestion
  |
  v
Parsing / normalization
  |
  v
Legal entity extraction
  |
  v
Citation extraction
  |
  v
Knowledge graph + vector index
  |
  v
Static Research Tool
```

### Static Research Agent tools

``` text
search_static_law()
get_section()
search_static_judgments()
find_precedent()
find_citation_relationship()
graph_query()
```

------------------------------------------------------------------------

## 3. Dynamic Research Flow

Dynamic research is performed for the current question.

### Sources

-   Supreme Court
-   Gujarat High Court
-   Other High Courts as the system expands
-   District Courts where accessible
-   India Code
-   Other verified legal sources

### Tool layer

``` text
search_supreme_court()
search_high_court()
search_district_court()
search_legislation()
get_judgment()
get_order()
find_citations()
```

Potential implementation sources include:

-   Bharat Courts
-   Official court repositories
-   India Code
-   Indian Kanoon API where permitted

The next technical task is to inspect each source's actual search
behavior, returned metadata, document links, freshness, and terms before
making it a production dependency.

------------------------------------------------------------------------

## 4. Active Research Flow

The active layer is introduced in Phase 1 only as a foundation.

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

No automatic promotion to authoritative static knowledge is allowed.

------------------------------------------------------------------------

## 5. Analyst Agent

The Analyst Agent receives results from all three research flows.

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

Responsibilities:

-   Understand the legal question
-   Compare evidence
-   Identify relevant facts
-   Identify legal issues
-   Map facts to legal provisions
-   Analyze precedents
-   Identify conflicting authorities
-   Identify missing information
-   Build a structured case analysis

------------------------------------------------------------------------

## 6. Document Agent

The Document Agent understands uploaded legal documents.

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

Its output becomes evidence for the Analyst Agent.

------------------------------------------------------------------------

## 7. Case Agent

The Case Agent operates at the case level.

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

A **research session** answers one question. A **case** is a persistent
workspace that accumulates everything about one real legal matter:

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
case — parties, established facts, prior findings — which is exactly what
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

## 8. Draft Agent

The Draft Agent converts verified analysis into a useful response.

For Phase 1 it should primarily generate:

-   Legal research answers
-   Case summaries
-   Issue analysis
-   Relevant-law explanations
-   Evidence guidance
-   Research summaries

Drafting formal pleadings and notices is deferred to a later phase.

------------------------------------------------------------------------

## 9. Verification Agent

Every important generated legal claim should be checked.

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

The verifier should detect:

-   Hallucinated cases
-   Wrong citations
-   Unsupported propositions
-   Misinterpretation of a section
-   Outdated authorities
-   Conflicting judgments
-   Wrong jurisdiction

------------------------------------------------------------------------

## 10. Example Query

User:

> Someone is occupying my land without permission. How can I prove
> ownership and what legal options may be available?

### Step 1 --- Query analysis

Identify:

``` text
Property / land
Ownership
Possession
Encroachment
Evidence
Jurisdiction
Potential remedies
```

### Step 2 --- Static research

Retrieve:

``` text
Relevant legislation
Relevant sections
Known important precedents
```

### Step 3 --- Dynamic research

Search:

``` text
Recent Supreme Court judgments
Relevant Gujarat High Court judgments
Relevant district-court material where available
```

### Step 4 --- Active research

Check:

``` text
Previously validated useful authorities
Commonly successful research paths
Relevant feedback-derived candidates
```

### Step 5 --- Analysis

Determine:

``` text
What law applies?
What facts matter?
What evidence is generally relevant?
Which authorities support each proposition?
Are there conflicting authorities?
What information is missing?
```

### Step 6 --- Verification

Verify each major legal proposition and citation.

### Step 7 --- Response

Return:

``` text
Short answer
Relevant law
Relevant cases
Evidence considerations
Potential legal routes
Important assumptions
Citations
Disclaimer
```

------------------------------------------------------------------------

## 11. Phase 1 Deliverables

### Milestone 1

Static India Code knowledge base.

### Milestone 2

Supreme Court historical corpus.

### Milestone 3

Court search tools.

### Milestone 4

Hybrid legal retrieval.

### Milestone 5

Thread Context Builder.

The shared context object (`AI_PROJECT_PROPOSAL.md` §6) plus its versioning
and invalidation rules. This lands **before** the researchers, because every
agent after it depends on being initialized from it.

### Milestone 6

Static Researcher + Dynamic Researcher.

### Milestone 7

Initial Active Researcher.

### Milestone 8

Analyst / Case Agent.

### Milestone 9

Draft Agent.

### Milestone 10

Citation Verification Agent.

### Milestone 11

End-to-end legal research benchmark.

------------------------------------------------------------------------

## 12. Phase 1 Success Criteria

The phase is successful when the system can take a real Indian legal
question and:

1.  Identify the relevant legal domain.
2.  Find relevant legislation.
3.  Find relevant judgments.
4.  Explain why those authorities are relevant.
5.  Preserve source provenance.
6.  Provide accurate citations.
7.  Detect insufficient evidence.
8.  Avoid unsupported legal claims.
9.  Clearly distinguish facts from legal analysis.
10. Produce repeatable research results.

The goal is **not** to build the most autonomous agent.

The goal is to build a **trustworthy legal research pipeline** that
later phases can safely make more agentic.
