# Phase 7 --- Advanced GraphRAG & Intelligence

## Objective

> Can we make the whole system significantly smarter, once the trustworthy
> foundation from Phases 1--6 is proven?

This phase only starts after Phases 1--6 work end to end. It's explicitly
the "make it better," not "make it exist" phase -- nothing here is load-
bearing for a working, trustworthy research pipeline.

------------------------------------------------------------------------

## 1. Legal Knowledge Graph Expansion

- Expand the legal graph beyond Phase 1's initial version
- Extract legal entities at scale
- Extract citation relationships at scale
- Precedent graph
- Statute graph
- Temporal legal graph -- was an authority in force at the relevant time?
- Graph-aware retrieval
- GraphRAG

Reference architecture: `LEGAL_DATA_SOURCES.md` §20--23 (the IBM Knowledge
Graph work, NyOn ontology, and the Domain-Partitioned Hybrid RAG and
Falkor-IRAC papers) -- these are the closest published references to what
this phase builds.

------------------------------------------------------------------------

## 2. Advanced Legal Reasoning

- Conflicting-precedent analysis
- Bench-strength reasoning
- IRAC-structured reasoning (Issue / Rule / Analysis / Conclusion, per
  Falkor-IRAC)
- Precedent strength / citation-chain analysis
- Advanced multi-agent research planning, parallel and iterative research
  loops beyond Phase 3's baseline

------------------------------------------------------------------------

## 3. Evaluation

- Indian legal benchmarks
- Hallucination evaluation
- Retrieval evaluation
- End-to-end legal reasoning evaluation

Research/evaluation datasets from `LEGAL_DATA_SOURCES.md` §16--19 (ILDC,
NyayaAnumana, InLegalBERT, LawSum) belong here -- benchmarking only, never
production knowledge, per `LEGAL_DATA_SOURCES.md` §29.

------------------------------------------------------------------------

## 4. Milestone

### Milestone 15

End-to-end legal research benchmark, using `src/legal_ai/evals/` per
`PROJECT_STRUCTURE.md` §14.

------------------------------------------------------------------------

## 5. Deliverable

> A measurably smarter, benchmarked system, built on a foundation that was
> already trustworthy before this phase started.
