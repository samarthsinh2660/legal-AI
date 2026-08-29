# Phase 2 --- Query & Retrieval Layer

## Objective

Make the Phase 1 data foundation actually searchable.

> Given a question, can we reliably retrieve the correct legal
> documents/sections/cases?

**Still no multi-agent system.** This phase builds tools and a retrieval
pipeline, not agents that decide when to call them -- that's Phase 3.

------------------------------------------------------------------------

## 1. Retrieval Pipeline

``` text
User Query
    |
    v
Query Processor
    |
    v
Hybrid Retrieval
    +-- Keyword
    +-- Vector
    +-- Metadata
    +-- Graph
    |
    v
Reranker
    |
    v
Evidence
```

Matches the hybrid retrieval architecture in `AI_PROJECT_PROPOSAL.md` §8:
retrieval should consider semantic similarity, exact legal terminology,
Act/section, court, date, jurisdiction, citation, legal entities, and graph
relationships -- not vector search alone.

------------------------------------------------------------------------

## 2. Search Tools

The stable, agent-facing tool contracts -- built against the real schema
Milestone 0 confirmed, not the assumed structure from earlier drafts. Every
tool returns `Evidence` (`src/legal_ai/schemas/evidence.py`), never a raw
string.

``` text
search_india_code()
search_supreme_court()
search_gujarat_hc()
search_judgments()
search_sections()
graph_search()
```

For the two bulk sources (Supreme Court, Gujarat HC), these tools query
**our own ingested store** from Phase 1 -- not a live source. For India
Code and Bharat Courts, a tool may call the live source per query, since
that data is current/query-specific by nature. See
`DATA_LAYER_ARCHITECTURE.md` §6--8 for the static/dynamic distinction this
maps onto.

Fuller tool surface, matching `LEGAL_DATA_SOURCES.md` §27:

``` text
search_statutes(query, jurisdiction?)
get_statute(act_id)
get_section(act_id, section_id)

search_supreme_court(query, date_range?, judge?, citation?)
search_high_court(query, court?, date_range?, judge?)
get_judgment(document_id)
get_order(document_id)

find_citations(document_id)
find_precedent_relationships(document_id)

search_static_knowledge(query)
graph_lookup(entity_or_relationship)
```

------------------------------------------------------------------------

## 3. Milestones

### Milestone 4 (complete)

Court search tools -- the tool contracts above, implemented in
`src/legal_ai/tools/` and `src/legal_ai/sources/` per
`PROJECT_STRUCTURE.md` §6--7.

Built 2026-08-19, per
`docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md`
and `docs/superpowers/plans/2026-08-19-phase2-milestone4-tool-contracts.md`:
a consolidated, backed-only subset of the tool surface above --
`search_statutes`, `get_statute`, `get_section`
(`src/legal_ai/tools/statutes.py`); `search_judgments`, `get_judgment`
(`src/legal_ai/tools/judgments.py`); `find_citations`,
`find_section_citations`, `find_judgment_sections`
(`src/legal_ai/tools/graph.py`). Every tool returns `Evidence`
(`src/legal_ai/schemas/evidence.py`, extended with optional
`document_id`/`title`/`document_type` fields to make results
self-describing). `get_order`, `search_high_court` (as distinct from
`search_supreme_court`), `search_static_knowledge`, and `graph_lookup`
were deliberately left out -- no real backing logic exists for them yet
(`get_order` needs District Courts, deferred -- see Milestone 2's note in
`PHASE_1_DATA_FOUNDATION.md`). 11 tests, all passing, real Postgres/Neo4j
(no mocks).

### Milestone 5 (complete)

Hybrid legal retrieval -- keyword + vector + metadata + graph fan-in,
reranking, and evidence-building (`src/legal_ai/retrieval/` per
`PROJECT_STRUCTURE.md` §8). Sits on top of Milestone 4's tools rather than
replacing them.

Decomposed into four sub-projects (see
`docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md`):

1. **Core fan-in engine -- complete 2026-08-19.**
   `retrieval/keyword.py` (Postgres FTS -- deliberately *not* called BM25,
   because `ts_rank_cd` is not BM25), `retrieval/vector.py`,
   `retrieval/metadata.py` (`MetadataFilters` + exact statutory lookup),
   `retrieval/graph_search.py` (one-hop seed expansion),
   `retrieval/hybrid.py` (Reciprocal Rank Fusion), and
   `retrieval/evidence_builder.py` (now the single home for
   `to_evidence`, consolidating three duplicate copies out of `tools/`).
   Schema: generated `tsvector` column + GIN index, and an HNSW index on
   `embedding` (the table previously had no index but its primary key).
   40 tests, all passing, real Postgres/Neo4j.
2. Embeddings provider abstraction + InLegalBERT benchmarking --
   **benchmarked 2026-08-19, and dropped on the evidence.** `PROJECT_STRUCTURE.md`
   §8 proposed benchmarking `law-ai/InLegalBERT` against the general-purpose
   `all-MiniLM-L6-v2`. Measured before building anything:

   | model | query~RERA §18 (correct) | query~sale-of-goods (junk) | separation |
   |---|---|---|---|
   | all-MiniLM-L6-v2 (current) | 0.372 | 0.173 | **+0.198** |
   | InLegalBERT (mean-pooled) | 0.715 | 0.655 | **+0.059** |

   InLegalBERT's higher absolute similarity is an anisotropy artifact --
   mean-pooled BERT vectors cluster in a narrow cone, so everything scores
   ~0.65-0.72, including entirely unrelated provisions. Raw cosine values
   are **not comparable across models**; only separation between a correct
   and an irrelevant document is. By that measure InLegalBERT is 3.4x
   *worse* at discriminating. Not adopted -- switching would also have cost
   a re-embed of all 36,467 documents and a 384->768 dimension migration.

   Caveat: this tests InLegalBERT mean-pooled, which is how a raw BERT
   checkpoint must be used for similarity. A sentence-transformers model
   fine-tuned on legal text (were a good one available) could still beat
   MiniLM; that is a different experiment, not this one.

   **Follow-up benchmark, 2026-08-19/20 -- a model swap IS warranted, just
   not to InLegalBERT.** Rank-based evaluation (rank of the known-correct
   section among a 10,005-document pool of real sections), using natural
   user phrasings that deliberately avoid the sections' own vocabulary:

   First run used only 5 queries and reported MiniLM MRR 0.626 vs mpnet
   0.900 (recall@10 80% -> 100%). **Re-run with 15 queries across contract,
   criminal, property, labour, consumer and arbitration law -- the honest
   numbers are materially smaller:**

   | model | MRR | recall@1 | recall@5 | recall@10 | CPU time /10k docs |
   |---|---|---|---|---|---|
   | all-MiniLM-L6-v2 (current) | 0.600 | 53% | 67% | 73% | 198s |
   | **all-mpnet-base-v2** | **0.694** | 60% | **87%** | **87%** | 2352s |

   mpnet better on 6/15 queries, worse on 4/15. The n=5 result overstated
   the gain roughly threefold -- a caution worth remembering about small
   eval sets.

   Where mpnet wins are exactly the vocabulary-gap cases: IT Act §66D
   ("impersonated" vs statutory "cheating by personation") 55 -> 1, RERA
   §18 ("builder" vs "promoter") 9 -> 1, TPA §54 27 -> 4, BNS §356 4 -> 1.
   Notably a *general-purpose* model closed the legal vocabulary gap that
   the legal-domain model (InLegalBERT) could not.

   Where it regresses: Contract Act §27 (restraint of trade) 52 -> 143,
   plus minor slippage on already-good queries (§138 1->3, §103 1->4,
   RERA §3 1->2). Caveat on §27: the corpus holds a near-duplicate --
   `act:2394:sec-54` (Partnership Act, "Agreements in restraint of trade")
   -- so that ground-truth label is arguably wrong rather than mpnet being
   wrong.

   **Decision basis:** recall@5 (67% -> 87%) matters more than MRR here,
   because retrieval feeds a top-k window to an agent; "the right section
   is in the window" is the property that determines whether a grounded
   answer is possible at all.

   **Longer-context candidates (nomic-embed, gte-multilingual, bge-m3) were
   dropped on hardware grounds, not quality.** They were never measured:
   two runs were killed by the Linux OOM killer (confirmed in the kernel
   log), because an 8192-token context allocates attention buffers larger
   than the free RAM. The deployment target is a CPU-only server with
   4-5GB RAM that also runs Postgres and Neo4j, leaving ~3-3.5GB; bge-m3
   (~3-4GB) and gte (~2.5-3GB) do not fit, and nomic only fits if its
   context is capped to ~1024, which removes the long-context advantage
   that justified testing it. mpnet (~1-1.5GB) fits comfortably.

   **Full-corpus baseline for reference** (36,467 docs, current MiniLM
   embeddings): MRR 0.508, recall@10 60% -- ranks [29, 1, 1, 2, 196].
   Note pool size dominates these numbers: the same five queries score MRR
   0.833 against a 405-document pool, 0.626 against 10k, 0.508 against the
   full corpus. Never compare MRR across different pool sizes.

   **Adopted 2026-08-20.** `all-mpnet-base-v2` is now the default; all
   36,465 documents were re-embedded at 768 dimensions and the HNSW index
   rebuilt (~60 min locally at ~10 docs/s with batched encoding).

   Full-corpus ranks before vs. after, for the five queries where a
   pre-migration baseline exists:

   | query | MiniLM | mpnet |
   |---|---|---|
   | RERA §18 ("builder" vs "promoter") | 29 | **1** |
   | IT Act §66D ("impersonated") | 196 | **5** |
   | BNS §316 | 1 | 1 |
   | RERA §3 | 1 | 2 |
   | Arbitration §11 | 2 | 3 |

   MRR 0.508 -> 0.607, recall@10 60% -> 100% on that set. The two headline
   failures that motivated the whole investigation are fixed; the small
   regressions are all within the top 3 and cost nothing at a top-5 window.

   Honest limitation: migrating overwrote the MiniLM vectors, so the other
   ten queries can no longer be A/B'd at full-corpus scale -- only the
   10k-pool comparison above exists for them.

   `DEFAULT_MAX_DISTANCE` re-measured for mpnet and changed 0.65 -> 0.60
   (mpnet: nonsense 0.664-0.802, real 0.225-0.514; carrying 0.65 over would
   have left only 0.014 of margin). See `retrieval/vector.py`.

   Ground-truth caveat found while verifying: for "someone impersonated me
   online using my identity to cheat people", the system returns BNS §319
   ("Cheating by personation") first, which is arguably a *better* answer
   than the labelled IT Act §66D. Some of the measured "misses" above are
   therefore label noise rather than retrieval failure.

   Reframed scope for this sub-project: rather than the originally-planned
   InLegalBERT benchmark, `embeddings.py` should make the model a
   **swappable config value** instead of a hardcoded string, so a future
   upgrade (GPU box, larger VM) is a config change plus a re-run of this
   benchmark -- not a code rewrite. Small piece of work, real payoff.

   Test-set caveat: n=5 queries. Directionally consistent and both fixes
   land where predicted, but widen the set before treating 0.900 as precise.
3. **Chunking pipeline -- complete.** `retrieval/chunking/statute.py` splits
   on sub-section markers and provisos, never mid-clause;
   `retrieval/chunking/judgment.py` splits on numbered paragraphs and keeps
   the number, because a citation to "paragraph 42" cannot be verified if
   chunking discarded it. Chunks live in `document_chunks`, kept out of the
   canonical `documents` table so they can be rebuilt without touching
   canonical data. 18,031 chunks from 6,654 documents.

   A document is represented in vector search exactly once: short documents
   by their own embedding, long ones by their chunks (parent embedding
   cleared, since a truncated vector misrepresents the document). Acts are
   excluded -- an Act's text is its sections concatenated and those are
   embedded individually.

   **Measured effect.** On the 15-query benchmark chunking is roughly
   neutral (MRR 0.425 -> 0.404, recall@5 67% -> 73%): that benchmark's
   ground truth is mostly short sections that were never truncated, so it
   measures the dilution from 18k extra candidates rather than the benefit.
   Measured on text drawn from *beyond* the old truncation point -- content
   that previously had no representation at all -- mean distance fell
   0.341 -> 0.140, all 12 sampled documents improved, and one (BNS §2, at
   0.883) moved from beyond the relevance floor (unreachable at any rank)
   to 0.280. Kept on that basis: unreachable text is a correctness problem,
   a small ranking dilution is not.

4. **Cross-encoder reranking -- complete.** `retrieval/rerank.py`, opt-in via
   `hybrid_search(..., rerank=True)`.

   | | MRR | recall@1 | recall@5 | recall@10 | ms/query |
   |---|---|---|---|---|---|
   | no reranking | 0.433 | 27% | 73% | 73% | -- |
   | ms-marco-MiniLM-L-6 | 0.471 | 27% | 80% | 87% | 1272 |
   | **ms-marco-MiniLM-L-12** (default) | **0.577** | **40%** | **87%** | 87% | 2474 |

   Largest gains are mid-shortlist reordering: Contract §25 32 -> 3, TPA §54
   23 -> 3, BNS §103 18 -> 4. `RERANK_CANDIDATES = 50` is deliberately
   generous -- a shorter shortlist would never show the reranker the deep
   documents that produce those gains.

   Confirmed limit: reranking reorders, it never recovers recall. Contract
   §27 sits at rank 546, outside any practical shortlist, and is unchanged.

   One consistent regression in both models: BNS §356 (defamation) 4 -> 21,
   most likely MS MARCO's web-search training not matching legal phrasing.

   Model is swappable via `RERANK_MODEL` (L-6 registered for when latency
   matters more than ranking quality). Latency above is a development
   laptop and should be re-measured on the CPU-only server.

**Relevance floor removed (`retrieval/vector.py`).** An earlier
`DEFAULT_MAX_DISTANCE = 0.60` was derived from a flawed measurement: it
compared each query's *top hit* distance against nonsense queries, not the
distance to the *correct* answer. Measured properly, correct answers span
0.31-0.76 while nonsense bottoms out at 0.66 -- the ranges overlap, so no
cut-off separates them. Chunking tightened the overlap further, since a
short passage sits near almost any query. The 0.60 floor was discarding 3
of 15 correct answers outright; a floor loose enough to keep them filtered
nothing. Removed rather than left as an inert knob.

This also explains, and retracts, an earlier claim that the keyword/metadata
fan-in was net-negative. That comparison ran vector-only with no floor
against the full fan-in *with* the 0.60 floor -- it measured the floor, not
fusion. The fan-in is not the problem.

**End-to-end result on the 15-query benchmark, full corpus:**

| configuration | MRR | recall@1 | recall@5 | recall@10 |
|---|---|---|---|---|
| fan-in only | 0.299 | 13% | 67% | 73% |
| **fan-in + rerank** | **0.530** | **40%** | **87%** | **87%** |

Reranking is therefore load-bearing, not optional polish, and is **on by
default**. It costs roughly 1-3s per query on CPU; `rerank=False` or
`RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2` trade quality for
latency where that matters.

> **Superseded 2026-08-28.** These figures were measured when the corpus
> held 18 judgments. It now holds 7,200+, and the same 50-question set
> measures **MRR 0.325, recall@10 56%** --- 0.469 / 78% when retrieval is
> restricted to sections. The mechanism is judgment dilution, and part of
> the drop is the dataset rather than the system: `expected` lists only
> statute ids, so genuinely leading judgments outranking a section score
> as failures. See `PHASE_7_ADVANCED_GRAPHRAG.md` §4.

### Re-measured 2026-08-20, on a versioned benchmark

The 15-query set above was never committed to the repository, so those
numbers cannot be reproduced. Phase 3 milestone 6a rebuilt the benchmark as
`evals/`, with the questions and their ground-truth document ids under
version control:

    .venv/bin/python -m evals.run
    .venv/bin/python -m evals.run --no-rerank

This is a **different question set**, so the figures are not expected to
match the table above and identical numbers would be coincidence. What
carries over is the finding that justified turning reranking on.

**50 questions, full corpus, limit=10:**

| configuration | MRR | recall@1 | recall@5 | recall@10 |
|---|---|---|---|---|
| fan-in only | 0.345 | 16% | 60% | 74% |
| **fan-in + rerank** | **0.467** | **32%** | **64%** | **78%** |

(The fan-in row predates two ground-truth corrections and understates that
configuration slightly; the reranked row is current.)

**The reranking decision holds, but its measured benefit is smaller than
the original set implied.** MRR improves by ~0.12 and recall@1 by 16 points,
against the +0.231 MRR the 15-query set reported. Reranking is still clearly
worth its cost -- it nearly doubles the rate at which the correct provision
lands at rank 1 -- but "0.299 to 0.530" overstated the effect, most likely
because a 15-question set is too small for a stable MRR.

Note also that reranking moves ordering, not membership: recall@5 is
identical either way. Its whole contribution is pushing the right answer
towards the top of a list it was already in.

An intermediate 14-question run measured MRR 0.574 vs 0.400 and showed
recall@10 *regressing* under reranking, 93% to 86%. That regression did not
survive the move to 50 questions (74% to 78%), and was a single question
moving a small denominator -- recorded here as a caution against reading
per-question movements on a small set as findings.

**The dominant failure mode is right Act, wrong section: 9 of 11 misses
returned the correct Act inside the top 10 without returning the correct
section.** Retrieval is not lost on these questions -- it reaches the right
statute and then fails to discriminate between sections that share its
vocabulary. That is the expected shape of the problem with 35,601 sections
embedded, and it is the failure a research agent is meant to close, since
`get_section(act_id, number)` can navigate within an Act once the Act is
known.

Two ground-truth labels were corrected after inspecting the misses: BNS s.86
("cruelty" defined) now also accepts s.85, which it explicitly cross-refers
to, and the online-impersonation question accepts BNS s.319 alongside IT Act
s.66D. Both were single-label errors on questions with two correct answers.

The remaining hard cases are genuine retrieval failures, not labelling errors.
Contract Act §27 (restraint of trade) misses under both configurations: the
question says *employment contract* and *competitor* while the section says
*restrained from exercising a lawful profession, trade or business*. The
Partnership Act §54 near-duplicate flagged earlier concerns partners on
dissolution, not employees, so §27 remains the correct label.

**Measured retrieval quality after sub-project 1 (honest baseline, not a
success claim).** For the query *"builder failed to give possession on
time refund"* against the real corpus:

- Keyword search returns exactly the right two real-estate delay/refund
  judgments -- the strongest signal here.
- Vector search returns five irrelevant sections -- effectively noise.
- **RERA §18 ("Return of amount and compensation"), the single most
  on-point provision, does not surface at all**, even at limit=20.

Root cause, diagnosed rather than assumed: the statute says *"promoter
fails to complete or is unable to give possession"* while users say
*"builder"*, so keyword search cannot bridge the vocabulary gap, and the
general-purpose `all-MiniLM-L6-v2` embedding is too weak to bridge it
semantically. This is the same RERA §18 gap the earlier real-estate pilot
found, now precisely root-caused -- and it is exactly what sub-projects 2
(legal-domain embeddings) and 4 (reranking) exist to fix. The fan-in
plumbing is correct; ranking quality is the open problem.

**Over-engineering review (2026-08-19), prompted by the question "was the
missing index the whole problem, and is a new system justified?"** Each
piece was measured against the pre-existing Phase 1 vector search:

| Piece | Earns its place? | Evidence |
|---|---|---|
| HNSW index | Speed only, **not** relevance | 72ms -> 1.8ms, but byte-identical results. It never could have fixed retrieval quality -- speed and relevance were two separate problems, and the index only addressed one. |
| Keyword signal | Yes | Surfaced the Ireo Grace and Kabra judgments, which vector-only search missed entirely. |
| Metadata exact lookup | Yes | Vector-only failed to return RERA §18 even when the query literally spelled out "Section 18 of the Real Estate (Regulation and Development) Act, 2016". |
| Fusion (RRF) | Yes | ~30 lines; required to combine the above. |
| Graph expansion | **Not yet** | Added six documents: one relevant (RERA §31), five noise. Kept and tested, but **defaults to off** -- with six judgments the graph is too sparse. Flip `expand_graph=True` and re-measure once the corpus grows. |

Net: 3 of 5 tested queries improved over the pre-existing vector search.
The vocabulary gap ("builder" vs. "promoter") remains genuinely unfixed by
any of this, and is the target of sub-project 2.

**Backlog item identified 2026-08-19, deferred to this milestone:**
`search_judgments` is deliberately a "find and verify one specific case"
tool (0 or 1 result), not a "browse related case law on a topic" one --
the Bharat Courts archive returns up to 3 candidates internally but only
`results[0]` is kept, and Indian Kanoon search only ever takes its top
hit. A `search_related_judgments(topic, limit=N)` tool -- take all N
candidates, verify each, store and return all as `Evidence` -- is the
natural way to get more than one relevant case per query, and belongs
here rather than in Milestone 4's single-case-lookup tools.

------------------------------------------------------------------------

## 4. Deliverable

> Given a question, we can reliably retrieve the correct legal
> documents/sections/cases.

------------------------------------------------------------------------

## 5. Explicitly not in this phase

``` text
Supervisor / Research Agent    -> Phase 3
Document Agent / Case Agent    -> Phase 4
Analyst Agent / Draft Agent    -> Phase 5
Verification Agent             -> Phase 6
GraphRAG / precedent graph     -> Phase 7
```
