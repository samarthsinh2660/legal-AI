# Phase 3 --- Research Agent System

## Objective

> Can AI perform legal research, instead of merely performing search?

Phase 2 built tools that return evidence for a query. Phase 3 introduces the
agent that decides *what* to search, *when* to search again, and how to
combine what comes back -- turning retrieval into research.

------------------------------------------------------------------------

## 1. Agent Architecture

``` text
                 Supervisor
                     |
              Research Agent
                     |
       +-------------+-------------+
       |             |             |
       v             v             v
    Static        Dynamic        Active
   Researcher    Researcher     Researcher
```

The Research Agent can:

- create research tasks
- call the Phase 2 search tools
- call sub-agents
- run searches in parallel
- combine evidence
- identify gaps
- perform follow-up research

------------------------------------------------------------------------

## 2. Shared Thread Context

Every sub-agent below is initialized from a single `ThreadContext`
(`AI_PROJECT_PROPOSAL.md` §6) -- the normalized question, jurisdiction,
case facts, active documents, and findings already established in this
thread. It is built **once** per thread and passed read-only; no agent
re-derives that understanding for itself.

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
```

------------------------------------------------------------------------

## 3. Static Researcher

Queries the trusted knowledge graph and vector index built in Phase 1,
through the Phase 2 tools.

### Initial data it draws on

``` text
Constitution
India Code
Acts
Sections
Rules
Regulations
High-confidence Supreme Court judgments
Selected Gujarat High Court judgments
Verified citations
```

------------------------------------------------------------------------

## 4. Dynamic Researcher

Performs live/query-specific research for the current question.

### Sources

``` text
Supreme Court
Gujarat High Court
Other High Courts as the system expands
District Courts where accessible
India Code
Other verified legal sources
```

Implementation sources confirmed in Milestone 0
(`DATA_RECON_FINDINGS.md`):

``` text
Bharat Courts        -- list_recent_judgments() works, no CAPTCHA
India Code            -- scrape-only, no API
Indian Kanoon API      -- where permitted
```

------------------------------------------------------------------------

## 5. Active Researcher

Retrieves already-validated historical observations, feedback-derived
candidates, and learned research patterns -- the **read side** of the
active layer. The **write side** (turning a new observation into a
validated, promotable candidate) is Phase 6, not this phase.

### Signals it reads

``` text
Previously validated useful authorities
Commonly successful research paths
Relevant feedback-derived candidates
```

No automatic promotion to authoritative static knowledge happens here --
this agent only reads what Phase 6's validation pipeline has already
approved.

------------------------------------------------------------------------

## 6. Milestones

### Milestone 6

Thread Context Builder. Lands **before** the researchers below, because
every agent depends on being initialized from it.

### Milestone 7

Static Researcher + Dynamic Researcher.

### Milestone 8

Initial Active Researcher (read side only).

------------------------------------------------------------------------

## 7. Deliverable

> AI can perform legal research instead of merely performing search.

------------------------------------------------------------------------

## 8. Explicitly not in this phase

``` text
Document Agent / Case Agent    -> Phase 4
Analyst Agent / Draft Agent    -> Phase 5
Verification Agent             -> Phase 6
Active knowledge promotion     -> Phase 6
GraphRAG / precedent graph     -> Phase 7
```
