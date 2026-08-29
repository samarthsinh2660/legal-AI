# Phase 7 --- Advanced GraphRAG & Intelligence

## Objective

> Can the system *weigh* the law, not just find it?

Phases 1--6 built a system that retrieves primary sources, answers from
them, and labels what it could not verify. It finds the law and does not
lie about it. What it cannot do is tell a Constitution Bench followed for
thirty years from a single-judge order nobody has cited. Both come back as
"relevant". Both are printed in the same font.

Phase 7 is that difference: ranking authority, following citation chains,
and surfacing disagreement between courts.

Nothing here is load-bearing for a working pipeline. It is the "make it
better" phase, and it starts only because Phases 1--6 work end to end.

------------------------------------------------------------------------

## 1. What this delivers, in user terms

A user asks: *"Builder didn't give possession on time --- can I get a
refund?"*

Today they get RERA s.18 and five judgments in relevance order, all
looking equally important.

| # | Feature | What changes for the reader |
|---|---|---|
| 1 | **Precedent strength** | "This is the leading authority" vs "this is a minor decision", instead of a flat list |
| 2 | **Still good law?** | A warning when a cited case was later overruled --- the Shepard's/KeyCite function |
| 3 | **Conflicting precedent** | Delhi HC and Bombay HC disagree; both shown, split flagged |
| 4 | **Bench strength** | A five-judge bench binds a two-judge bench, and the answer says so |
| 5 | **In force at the time** | A 2023 amendment does not govern a 2019 contract |
| 6 | **IRAC structure** | Issue / Rule / Analysis / Conclusion --- how lawyers actually read |

------------------------------------------------------------------------

## 2. Data required, and what is actually held

Measured 2026-08-29, after the deep Supreme Court ingest.

| Feature | Data it needs | Held | Status |
|---|---|---|---|
| 1 Precedent strength | `CITES` edges | 3,503 | **Working** |
| 2 Still good law | Citation context + treatment labels | none | **Blocked** on classification |
| 3 Conflicting precedent | HC breadth, section links | 4,460 HC / 28 courts, `CITES_SECTION` | **Ready** |
| 4 Bench strength | Judges per judgment | 5,861 SC (97%) | **Done** |
| 5 In force at date | `document_versions` | empty | **Blocked** on M14 |
| 6 IRAC | none (prompting) | --- | Ready |
| M15 benchmark | Judgment retrieval eval set | none | **Missing** |

### The citation-density problem

The precedent graph is the spine of features 1--3. It was thin for a
structural reason rather than a fixable bug, and two deep Supreme Court
ingests are what moved it.

```
judgments                         10,505
carry a citation of their own      6,046   (SCR; all Supreme Court)
CITES edges                        3,503
references extracted but unresolved   91,485
```

An edge needs *both* endpoints in the corpus, so coverage enters squared:
at 5% of a year, a reference pair resolves 0.25% of the time. Raising
Supreme Court coverage is therefore worth far more than it looks, and
lowering it is worth far less.

**Density is quadratic in coverage**, and measurably better than quadratic
when the ingest is concentrated in a contiguous block of years, because
those judgments cite each other rather than only citing backwards into
years we do not hold:

```
                        citable      CITES
start of the phase        1,367         67
after +1,376 SC           2,743        521    2.0x citable ->  7.8x edges
after +2,502 more SC      6,046      3,503    4.4x citable -> 52.3x edges
```

Edge growth stayed super-quadratic across both passes. 4.4x the citable
corpus produced 52x the edges, against the 19x a pure square law predicts.
Concentrating on a contiguous block of years is what does it: those
judgments cite each other, not only backwards into years we do not hold.

This is the single highest-value data lever in the phase. Breadth across
courts is not: High Court judgments carry no citation of their own in the
archive, so nothing can cite them, and 4,400 of them moved the edge count
by 37.

### The reporter problem

Of 50,729 distinct unresolved citation targets:

```
SCR    30,845      reachable by ingest
SCC    14,334      unreachable --- no algorithmic mapping to SCR
AIR     2,912      unreachable
```

Roughly a third of everything Indian judgments cite is in a reporter whose
volume and page numbers cannot be derived from the SCR numbering our
corpus uses. No amount of crawling closes that gap; it needs a mapping
table. Until one exists, the precedent graph is SCR-only and should say so
rather than presenting partial coverage as complete.

------------------------------------------------------------------------

## 3. Built

### Bench extraction --- `legal_ai.ingestion.bench`

The SCR reporter prints the bench under the parties:

```
[N. V. RAMANA, CJI, HIMA KOHLI AND C.T. RAVIKUMAR, JJ.]
```

Regex, not a model call: the shape is fixed by the reporter's house style,
a model would cost one call per judgment across thousands of documents, and
a *wrong* bench size is worse than a missing one because it silently
reorders authority. What will not parse returns nothing.

Measured over the stored corpus:

```
Supreme Court   5,861 / 6,045   97%
High Courts        81 / 4,460    2%   (per-court formats, not handled)

mean bench 2.20      Constitution Benches (5+): 66
```

The outliers are the validation: the 11-judge bench is *TMA Pai
Foundation*, the 9-judge benches are the 2024 Chandrachud benches. Real
Constitution Benches, correctly counted.

Stored as `documents.judges` / `documents.bench_size`, added additively so
the canonical upsert --- which statutes also travel through --- is
untouched. `bench_size` is NULL when unparsed; NULL means *unknown* and
must never be read as *small*, since an unparsed Constitution Bench
outranks everything.

High Court bench parsing is deliberately not attempted. The formats differ
per court and share no common shape, so it needs 28 patterns and its own
measurement. Bench strength ships Supreme-Court-only, which covers the
binding-precedent cases that matter most.

### Authority ranking --- `legal_ai.retrieval.authority`

Two signals, deliberately not blended into one number:

- `citation_count` --- how many stored judgments cite this one.
  *Influence*: what practitioners follow. Soft, and it moves with corpus
  coverage, so it measures our shelf as much as the law.
- `bench_size` --- how many judges sat. *Binding force*, a hard rule
  rather than a popularity signal.

Ranked lexicographically, citations first with bench as tie-breaker.
Ordering by bench first would put an uncited five-judge bench above the
two-judge decision the profession actually follows on the question asked.
Bench is surfaced on every result so a caller can say "and this one binds"
--- the honest way to show it.

Exposed as `tools.graph.find_leading_authorities(section_id)`.

------------------------------------------------------------------------

## 4. Measured, and what it settled

### Graph expansion stays off

`hybrid_search(expand_graph=...)` was left off in Phase 2 with an explicit
instruction to re-measure before switching it on. Re-measured at 521 edges,
50 retrieval questions:

```
                       MRR    r@1   r@5   r@10
expand_graph=False    0.325   22%   50%    56%
expand_graph=True     0.318   20%   48%    60%
```

No measurable effect, for ~0.5s per query. It stays off.

Caveat worth keeping: every question in that dataset expects a statute
section, so a judgment-citation graph has nothing to win there. The
benchmark is the right instrument for detecting *harm* --- it found none
--- and the wrong one for measuring precedent-graph value. That needs the
judgment eval set listed as missing above.

### Retrieval has regressed and the recorded figure is stale

```
                       MRR    r@1   r@5   r@10
Phase 2 recorded      0.530   40%   87%    87%
now, all types        0.325   22%   50%    56%
now, sections only    0.469   32%   64%    78%
```

recall@10 fell from 87% to 56%: for nearly half the questions the correct
provision no longer appears in the top 10. Filtering to sections recovers
most of it, which identifies the mechanism --- **judgment dilution**. The
judgment corpus grew from 18 to 7,200+ and the retrieval benchmark was
never re-run.

It is not simply "worse". On the RERA question the four judgments outranking
s.18 are *Laureate Buildwell*, *Ireo Grace*, *Newtech Promoters* --- the
actual leading authorities on builder possession. Retrieval surfaced real
law; the benchmark scores it as failure because `expected` only ever listed
statute ids. Part of the drop is genuine regression and part is the dataset
measuring the wrong thing, and the two cannot be separated with this
dataset.

A residual 0.469 vs 0.530 on sections alone remains unexplained.

**The 0.530 in `PHASE_2_QUERY_RETRIEVAL.md` and in the `hybrid_search`
docstring now overstates the system.**

------------------------------------------------------------------------

## 5. Known limits

**Citation counts are tens, not hundreds.** The top of the corpus now
separates cleanly --- *Indore Development Authority* at 95, *Pranay Sethi*
at 45, *Innoventive* at 33 --- and on arbitration the ranking returns
*Vidya Drolia*, *In Re: Interplay* (7 judges), *Chloro Controls* and *Cox
and Kings* (5 judges), which is the correct answer. Below roughly ten
citations the ordering is still noise, so the ranking is trustworthy at
the head of a list and not at its tail.

**`CITES_SECTION` means "mentions", not "is about".** A PMLA judgment that
cites NI Act s.138 in passing enters the candidate set for s.138 and can
rank above cases genuinely on the point. Ranking the candidates does not
fix a polluted candidate set; that needs a relevance filter on the edge.

**Feature 2 is the valuable one and the furthest away.** Detecting that A
overruled B needs both a dense graph and treatment classification over the
citing passage. Neither exists. A system that says "still good law" while
missing overrulings is worse than one that says nothing, so this ships only
when it can be measured.

------------------------------------------------------------------------

## 6. Milestone 15

End-to-end legal research benchmark, per `PROJECT_STRUCTURE.md` §14.

Prerequisite, not deliverable: a judgment-retrieval eval set. Without it
nothing in this phase is measurable, including whether authority ranking
helps at all. Research datasets from `LEGAL_DATA_SOURCES.md` §16--19 (ILDC,
NyayaAnumana, InLegalBERT, LawSum) are benchmarking only, never production
knowledge, per §29.

------------------------------------------------------------------------

## 7. Reference architecture

`LEGAL_DATA_SOURCES.md` §20--23 --- the IBM Knowledge Graph work, the NyOn
ontology, and the Domain-Partitioned Hybrid RAG and Falkor-IRAC papers ---
are the closest published references to what this phase builds.

------------------------------------------------------------------------

## 8. Deliverable

> Authority ranking and conflict surfacing on an SCR-only precedent graph,
> with its coverage stated rather than implied --- and the currency and
> overruling questions left explicitly open instead of answered badly.
