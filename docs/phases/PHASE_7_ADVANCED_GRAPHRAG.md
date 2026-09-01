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
| 2 Still good law | Citation context + treatment labels | 79 edges classified | **Built**, running incrementally |
| 3 Conflicting precedent | HC breadth, section links | 4,460 HC / 28 courts, `CITES_SECTION` | **Built** |
| 4 Bench strength | Judges per judgment | 5,861 SC (97%) | **Done** |
| 5 In force at date | `document_versions` | empty | **Blocked** on M14 |
| 6 IRAC | none (assembly) | --- | **Built** |
| M15 benchmark | Judgment retrieval eval set | none | **Missing** |
| Edge relevance | `mentions` on CITES_SECTION | 6,890 edges counted | **Done** |

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

Exposed as `tools.graph.find_leading_authorities(section_id)`, and applied
where the reader actually sees it: `DraftAnswer.key_judgments` was ordered by
`document_id` -- alphabetical order over opaque ids, which put a single-judge
order above the Constitution Bench that settled the point. The draft node now
looks authority up over the graph and orders by it, falling back to id order
if the lookup fails, because a graph that is down must not cost the user
their answer.

### Conflict detection --- `retrieval/conflict.py` + `agents/conflict.py`

Whether two courts disagree cannot be read off the graph: the graph records
that a judgment cites a section, never what it held about it. So this splits
into a cheap half and an expensive one.

The cheap half chooses *which* holdings to compare. One judgment per court
--- two decisions of the same High Court are not a split, at worst that
court's own inconsistency --- and a few courts, not all: fifty judgments is
1,225 pairs, nearly every one of them a court agreeing with itself.

The expensive half is one model call over at most four holdings, asked only
whether they can stand together. It is not asked which side is right; which
court binds this reader is a question about jurisdiction and bench strength
that the graph answers better than a model does.

**Three outcomes, not two.** CONSISTENT and NOT_CHECKED are different facts.
Collapsing them would repeat exactly the defect Phase 6 fixed for
verification: a check that could not run rendering as a check that passed.
The direction matters both ways --- asserting a split that does not exist
makes settled law look open, while missing one leaves the reader no worse off
than before the feature existed.

Runs on `case_model_chain`, the same shape of task as contradiction detection
over case documents, where Gemma measured recall 1.00 against gemini-flash's
0.20 (`evals/run_contradictions.py`, 2026-08-24).

### IRAC --- `agents.draft.render_irac`

Issue / Rule / Analysis / Conclusion, assembled from the verified answer
rather than written by a model. Statutes are the Rule, judgments the
Analysis, the question the Issue and the lede the Conclusion.

The tempting version hands the claims to a model and asks for an IRAC essay.
That would put un-verified prose in front of the reader after the whole
pipeline spent its effort making every sentence checkable, and give the model
a chance to drop a citation on the way. Claims that failed verification are
kept out of Rule and Analysis and listed under their own heading: letting
them in would make IRAC a second door into the answer for what the front door
turned away, and dropping them would leave a short answer indistinguishable
from an incomplete one.

### Edge relevance --- `mentions` on CITES_SECTION

The edge was created from a single regex hit, so it recorded that a judgment
*named* a section, never that it was *about* one. A money-laundering
judgment naming NI Act s.138 once produced the same edge as a cheque
dishonour case that turns on it, and `find_leading_authorities("s.138")`
returned the former first.

The count was already in the text --- `extract_section_references` was
discarding it during de-duplication. Recovering it and requiring two
mentions before a judgment counts as authority on a provision:

```
edges recounted        6,890
  substantive (2+)     2,140
  passing (1)          4,750     69% of the edges were passing mentions
```

Before and after, leading authorities on NI Act s.138:

```
before   Vijay Madanlal Choudhary (PMLA)        <- names s.138 once
         M/S Arif Azim Co.
after    P. Mohanraj v. Shah Brothers Ispat     <- s.138 and the IBC moratorium
         Rajesh Jain v. Ajay Singh              <- presumption under s.139
         N. Harihara Krishnan v. J. Thomas      <- cognizance under s.142
```

### Treatment classification --- `agents/treatment.py`, `retrieval/good_law.py`

Whether a case is still good law is not in the citation: "(2019) 8 SCC 729"
reads the same whether the court followed it or buried it. It is in the
sentence around it, which `ingestion.citations.extract_citation_contexts`
now carries alongside the edge.

Four treatments --- FOLLOWED, DISTINGUISHED, OVERRULED, CONSIDERED --- and a
fifth state that is not a treatment: NOT_CHECKED. The classifier **fails to
NOT_CHECKED, never to FOLLOWED.** Telling a reader a case is good law when
it was overruled is worse than telling them nothing, because it stops them
checking; the reverse leaves them where they started.

DISTINGUISHED is deliberately not negative. A court distinguishing a case
confines it to its facts and leaves it standing; treating that as a
retirement would kill live authority --- the same failure as missing an
overruling, pointed the other way.

`assess_good_law` inverts the usual conservatism: **one unclassified citing
judgment withholds the clean bill**, because the overruling could be hiding
in exactly the edge we did not read. Only a positively identified overruling
returns DOUBTED.

```
79 edges classified over 40 calls
  CONSIDERED     55
  FOLLOWED       20
  DISTINGUISHED   4
  OVERRULED       0
```

Rebuilt 2026-09-01 after the 2015 deepening, over the reporter tables
rather than the model:

```
3,256 edges treated (3,851 judgments carry a table)
  CONSIDERED     2543
  FOLLOWED        624
  DISTINGUISHED    87
  OVERRULED         2
```

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

### Judgment dilution, and the baseline that was misread

An earlier note in this document reported a serious regression, comparing
today's numbers against **MRR 0.530 / recall@10 87%**. That comparison was
wrong. Those figures come from the 15-query set that `PHASE_2` explicitly
records as unreproducible and *a different question set*. The versioned
50-question benchmark --- the one `evals.run` actually runs --- recorded:

```
                       MRR    r@1   r@5   r@10
Phase 2 recorded      0.467   32%   64%    78%
sections only, today  0.469   32%   64%    78%
```

**Section retrieval has not regressed.** It measures today exactly what it
measured then.

What is real is dilution. Over the whole corpus, with judgments competing
for the same ten slots:

```
                       MRR    r@1   r@5   r@10
whole corpus          0.282   20%   42%    54%
+ type interleaving   0.333   20%   52%    68%
```

The judgments doing the crowding are not junk --- on the RERA question the
ones outranking s.18 were *Laureate Buildwell*, *Ireo Grace* and *Newtech
Promoters*, the leading authorities on builder possession. The defect is
one-sidedness: a reader asking what the law says needs the provision *and*
the cases, and was getting only cases.

`retrieval/type_floor.py` interleaves the two kinds below rank 1, which the
strongest result keeps whatever it is. That recovers +0.05 MRR and 14 points
of recall@10 without an intent classifier on the hot path --- deliberately,
because a misclassified intent removes a whole category from the answer, and
most legal questions genuinely want both.

A gap to 0.469 remains. Closing it further would mean ranking statutes above
judgments, and since every question in this dataset expects a statute, that
would be tuning to the benchmark rather than to the reader. It needs the
judgment eval set listed as missing above.

### Everything here is optional

Phase 7 does not change what the system is. It is a layer over an answer
that was already correct, so it is configurable the way verification is.

Most of it needs no switch at all: `find_court_split`, `render_irac`,
`find_leading_authorities` and `is_still_good_law` have **no automatic
caller**. They run when something asks and cost nothing otherwise, which is
the cheapest kind of optional.

Two behaviours change every answer, so they carry a documented default:

```
LEGAL_AI_RANK_BY_AUTHORITY=false        key_judgments back to id order
LEGAL_AI_INTERLEAVE_RESULT_TYPES=false  retrieval back to raw relevance
```

Both default **on**, on measurement rather than preference. Interleaving is
+0.05 MRR and +14 points of recall@10; authority ordering replaces
alphabetical order over opaque identifiers, which has nothing to recommend
it. Off restores exactly what shipped before this phase -- not an
approximation, since a flag that leaves the system in a third state nobody
measured is worse than no flag.

### Treatment classification, scored

150 cases, ground truth from the reporter's own Case Law Reference table.
The classifier never sees it: passages come from body prose before the
headnote block, so this measures reading law rather than reading a label.

```
exact agreement with the reporter    0.92   (138/150)
returned NOT_CHECKED                 0.00
reached for OVERRULED (suppressed)   0

FOLLOWED        66/72   0.92
CONSIDERED      67/72   0.93
DISTINGUISHED    5/6    0.83
```

Every error is an adjacent-class confusion, 9 of 12 of them FOLLOWED against
CONSIDERED -- the "adopted it or merely noted it" boundary. Nothing became
OVERRULED.

**This partly contradicts the reason OVERRULED was taken away from the
model.** That rule came from two observed failures; across 150 clean
passages the model reached for OVERRULED zero times. Both original failures
came from bad inputs rather than an eager model -- a phantom edge from the
citation collision, and a reference list where the cited case was marked
"affirmed" while a different case on the same line was overruled. The
suppression stays, but as cheap insurance costing nothing measurable, not as
a correction to a model that over-reaches.

**What this cannot measure:** the dataset holds no OVERRULED case, because
the corpus contains no reporter-labelled overruling where the overruled
judgment is also held. The label whose errors are worst is unscored. The
classifier is shown not to invent overrulings; it is not shown to catch one.

------------------------------------------------------------------------

## 5. Known limits

**Citation counts are tens, not hundreds.** The top of the corpus now
separates cleanly --- *Indore Development Authority* at 95, *Pranay Sethi*
at 45, *Innoventive* at 33 --- and on arbitration the ranking returns
*Vidya Drolia*, *In Re: Interplay* (7 judges), *Chloro Controls* and *Cox
and Kings* (5 judges), which is the correct answer. Below roughly ten
citations the ordering is still noise, so the ranking is trustworthy at
the head of a list and not at its tail.

**Treatment classification covers 79 of 3,503 edges.** `is_still_good_law`
therefore answers NOT_CHECKED for nearly everything, which is the honest
state and not a bug. Classification runs incrementally against a free-tier
quota; the machinery is complete and the coverage is not.

No overruling has been found yet. In 79 edges that is expected --- the base
rate is low --- but it means the DOUBTED path has been exercised only by
tests, never by real data.

**Feature 2 is the valuable one and the furthest away.** Detecting that A
overruled B needs both a dense graph and treatment classification over the
citing passage. Neither exists. A system that says "still good law" while
missing overrulings is worse than one that says nothing, so this ships only
when it can be measured.

------------------------------------------------------------------------

## 6. What is left

Nothing below blocks using what is built. Ordered by how much each would
change the product.

### Measurement gaps

**No OVERRULED case in the treatment eval.** The 150-case eval set holds
no reporter-labelled overruling, so the model's recall on the label whose
errors are worst is still unscored. The classifier is shown not to *invent*
overrulings; it is not shown to *catch* one. This is narrower than it was
--- see below, the corpus now holds two --- but two pairs are not an eval
set, and the model is barred from the label anyway, so what is unscored is
a path nothing in production takes.

**Closed 2026-09-01: the DOUBTED path now runs on a real negative.**
Deepening 2015 Supreme Court coverage (60 -> 700 judgments) landed the
first overruled pair whose *both* ends we hold:

```
PRAKASH & ORS. v. PHULAVATI & ORS.        [2015] 12 SCR 579
  overruled by VINEETA SHARMA v. RAKESH SHARMA   (coparcenary)
TOMASO BRUNO & ANR. v. STATE OF U.P.
  overruled by ARJUN PANDITRAO KHOTKAR            (s.65B certificates)
```

Both came from the reporter's own Case Law Reference table, not the model.
`is_still_good_law` returns DOUBTED for each, `is_a_warning` is true, and
the reader line names the overruling judgment. Before this the DOUBTED
branch had only ever been asserted about a synthetic tuple; the seam
between a Neo4j edge and the badge was untested. `tests/tools/`
`test_tools_graph.py` now pins it over a real edge.

**Authority ranking is unscored.** It returns the right cases by inspection
-- P. Mohanraj on NI Act s.138, Vidya Drolia on arbitration -- but there is
no judgment-retrieval eval set, so there is no precision figure. Every
retrieval question in `evals/datasets/retrieval.json` expects a statute.

**Milestone 15 is not started.** See §7.

### Blind features

**Conflict detection returns CONSISTENT for the wrong reason.** Run against
MV Act s.166 (9 courts) and Arms Act s.27 (8 courts) it answered CONSISTENT
both times, correctly reasoning that the judgments address different legal
issues. That is the problem: `CITES_SECTION` gathers courts ruling on
different questions that happen to cite the same provision. `MIN_MENTIONS`
helped ranking but the candidate set still is not issue-aligned. This needs
per-section High Court depth, and probably an issue filter on the edge.

### Coverage gaps

**High Court bench parsing sits at 2%.** The SCR format is one house style;
the 28 High Courts share no common shape, so this needs per-court patterns
and its own measurement. Bench strength is Supreme-Court-only today.

**High Court judgments carry no citation of their own** in the archive, so
nothing can cite them and they cannot enter the precedent graph. 4,400 of
them moved the edge count by 37. This is a source limitation, not a bug.

**Roughly a third of citations are unreachable** -- 14,334 SCC and 2,912 AIR
targets whose volume and page numbers have no algorithmic mapping to SCR.
No amount of crawling closes it; it needs a mapping table.

**Treatment for judgments without a reporter table** still needs
`scripts/classify_treatments.py` and model budget. The table covers 3,847
Supreme Court judgments; High Court judgments have none.

### Deferred by decision

**In-force-at-date (feature 5)** remains blocked on Milestone 14 currency,
which was deliberately skipped. `document_versions` is empty and nothing
re-scrapes, so a 2023 amendment is quoted at a 2019 dispute without comment.

**The API layer** lives in a worktree with dependencies in a local `.deps/`.
Before merging: `pip install -e '.[dev]'` and delete that directory. See
`docs/API.md`.

------------------------------------------------------------------------

## 7. Milestone 15

End-to-end legal research benchmark, per `PROJECT_STRUCTURE.md` §14.

Prerequisite, not deliverable: a judgment-retrieval eval set. Without it
nothing in this phase is measurable, including whether authority ranking
helps at all. Research datasets from `LEGAL_DATA_SOURCES.md` §16--19 (ILDC,
NyayaAnumana, InLegalBERT, LawSum) are benchmarking only, never production
knowledge, per §29.

------------------------------------------------------------------------

## 8. Reference architecture

`LEGAL_DATA_SOURCES.md` §20--23 --- the IBM Knowledge Graph work, the NyOn
ontology, and the Domain-Partitioned Hybrid RAG and Falkor-IRAC papers ---
are the closest published references to what this phase builds.

------------------------------------------------------------------------

## 9. Deliverable

> Authority ranking and conflict surfacing on an SCR-only precedent graph,
> with its coverage stated rather than implied --- and the currency and
> overruling questions left explicitly open instead of answered badly.
