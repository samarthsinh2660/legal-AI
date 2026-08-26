# Phase 6 --- Verification + Currency

> **Renamed.** This phase was "Verification + Active Learning". The active-
> learning half has been redefined; see §3. The old framing --- learn from
> what users ask most --- was dropped deliberately, and §3.1 records why.

## Objective

> Can we make the system trustworthy, and keep it trustworthy as the law
> changes underneath it?

Phase 5 produces an answer with claims attached to evidence ids. Phase 6
asks two questions Phase 5 cannot:

1. Does the cited section actually **say** what the claim says it says?
2. Is the text we cited still **the law**?

Both are failures where every id checks out and the answer is wrong.

------------------------------------------------------------------------

## 1. Where we actually are

Measured 2026-08-26.

``` text
act sections in corpus      36,461
judgments in corpus             37  (was 18 before 2026-08-27 ingest)
document_versions rows           0
```

The verifier that exists (`src/legal_ai/verification/groundedness.py`)
answers exactly one question, without a model, and therefore cannot itself
hallucinate:

- Does `document_id` exist in the corpus?
- Was it in the evidence this thread actually retrieved?

That is a **reference check**. It is not a support check.

`document_versions` is empty. The amendment-archiving path in
`upsert_document` is unit-tested and has never fired against real data,
because nothing re-scrapes. Treat it as unproven.

### 1.1 The gap, stated precisely

| Check | Status |
|---|---|
| Fabricated document id | done (id lookup) |
| Claim cites nothing | done |
| Cited but never retrieved | done |
| **Cited section does not support the claim** | **missing** |
| **Cited text has since been amended** | **missing** |
| Judgment overruled / negative treatment | missing |
| Wrong jurisdiction / court hierarchy | missing |

The two bolded rows are Phase 6.

------------------------------------------------------------------------

## 2. Milestone 13 --- Support verification

### 2.1 The failure this targets

Stanford RegLab's preregistered study of Lexis+ AI, Westlaw AI-Assisted
Research and Ask Practical Law found hallucination rates of 17--33%
*despite* every one of those products being RAG-grounded over a proprietary,
verified corpus. Grounding did not eliminate the failure; it changed its
shape.

The shape it changed into has a name: **misgrounding**. A real case, cited
for a proposition it does not support. RegLab's own characterisation is that
this is more dangerous than an invented case, because it survives exactly
the check we currently run --- the id resolves, the document is real, the
retrieval log confirms we read it.

This is not hypothetical in India. In September 2025 the Delhi High Court
saw a petition withdrawn after opposing counsel found it quoted paragraphs
73 and 74 of a judgment containing 27 paragraphs --- a real, famous case,
invented content. The Bombay High Court in October 2025 quashed an
assessment order of roughly Rs 27.91 crore that rested on three
non-existent precedents. In December 2025 an entire fabricated set of
precedents reached the Supreme Court. The Bengaluru ITAT withdrew a
decision for the same reason.

Our current verifier would catch the wholly-invented citations in those
matters. It would **not** catch the Delhi HC one, where the case was real.

### 2.2 Design --- deterministic first, model last

The instinct to answer misgrounding with "run an LLM over every claim" is
wrong, and the incumbents demonstrate why. Neither Shepard's nor KeyCite is
a language model. They are citation graphs and structured databases, and
Lexis describes its own stack as taxonomies, knowledge graphs, RAG, agentic
RAG, frontier models **and human review** --- the model is one component,
used where semantic judgement is genuinely required, not as the checker of
first resort. Harvey does not verify good-law status with a model either;
it integrates LexisNexis Shepardizing.

So the pipeline is a funnel, and every stage that can be answered by a
lookup or a string comparison must be, before any stage that costs a token:

``` text
claims + evidence_ids
      |
      v
[1] citation exists?          <- SQL. exists today.
      |
      v
[2] retrieved by this thread? <- set membership. exists today.
      |
      v
[3] quotation matches?        <- string comparison. NEW, no model.
      |
      v
[4] version current?          <- document_versions. NEW, needs M14.
      |
      v
[5] authority still good?     <- precedent graph. Phase 7, not here.
      |
      v
[6] semantic support?         <- MODEL. one batched call for whatever
      |                          stages 1-5 could not settle.
      v
approved | unsupported -> re-research (capped) -> ship labelled
```

Stages 1--5 can only **reject**. Stage 6 can only **add** rejections; it may
never overturn stages 1--5. A model that can approve is a model that can
hallucinate an approval, which would place a hallucination-checker in the
business of laundering hallucinations.

This is the composition pattern the guardrails frameworks converged on ---
Guardrails AI chains validators, NeMo Guardrails composes input/output
rails --- with the legal-domain constraint that the cheap deterministic
validator is authoritative in the negative direction and the expensive
probabilistic one is not authoritative in the positive direction.

### 2.2.1 Stage 3 is the one that earns its place

Quotation matching is deterministic, costs nothing, and catches the exact
Indian failure in §2.1. The Delhi HC petition quoted paragraphs 73 and 74
of a judgment containing 27 paragraphs. No model is required to catch that
--- the paragraph does not exist in the retrieved text, and a string
comparison says so with certainty a model could never offer.

Every judgment we store keeps its `full_text`. We already have what stage 3
needs.

### 2.2.2 What routes a claim to stage 6 --- and a correction

The suggested routing was "8 claims verified mechanically, 2 uncertain ones
go to the model". The batching is right and the cost saving is real. The
word **verified** is not, and the distinction decides whether this design
works.

**Misgrounding passes every mechanical check.** Real id, genuinely
retrieved, correct section number, current version, still good law --- and
the claim still does not follow from the text. That is the entire finding
in §2.1. Stages 1--5 are rejection filters, not verifiers: a claim that
survives them is *un-rejected*, not confirmed.

So routing cannot be by a confidence score, because the dangerous claims
are the confident ones. Route by the **form of the claim** instead:

| Claim form | Settled by | Model? |
|---|---|---|
| Quotes the section | stage 3, decisively | no |
| Cites a repealed/amended section | stage 4, decisively | no |
| Cites a fabricated or unretrieved id | stages 1--2, decisively | no |
| **Characterises or paraphrases** | nothing mechanical can settle it | **yes** |

Paraphrase is the residue, and it is where misgrounding lives. Everything
else drains out of the funnel for free.

An honest consequence: the 8/2 split is a hoped-for ratio, not a measured
one. If our answers are mostly paraphrase --- which, for legal analysis,
they may well be --- the residue is large and the saving is small. §5 adds
**residue rate** to the metrics so we find out rather than assume.

### 2.3 What stage 6 actually does

Per surviving claim, one bounded judgement against the retrieved text of
each cited document:

``` text
SUPPORTED   -- the section states this, or it follows directly
PARTIAL     -- related but the claim overstates or narrows it
UNSUPPORTED -- the section does not address this proposition
```

Batched: one call for all surviving claims in an answer, not one call per
claim.

This is textual entailment. The published work is unambiguous about the
method: NLI/entailment formalises support as entailment / contradiction /
neutral; ALCE introduced NLI-based citation recall and precision; FActScore
decomposes an answer into atomic facts; AttrScore and RAGAS judge support
with entailment or LLM judges; VerifAI decomposes an answer into atomic
claims and validates each against retrieved evidence with a fine-tuned NLI
engine. Phase 5's Analyst already produces the atomic claims, so the
decomposition step is done --- M13 is only the judging step.

### 2.3.1 Two problems, not one

A lesson worth stating separately, because conflating these produces a
checker that does neither well:

> **"Is this citation real and does it support the claim?"** and
> **"Is this authority still valid?"** are different problems.

Shepard's/KeyCite-style treatment tracking answers the second. Entailment
answers the first. In this phase they are M13 (stage 6) and M14 (stage 4)
respectively, and stage 5 --- precedent treatment --- is deferred to Phase 7
because it needs a citation graph we do not have at 37 judgments.

### 2.4 Known weakness, recorded up front

Stage 6 is an LLM judge, and LLM judges are measurably unreliable
instruments. "Rating Roulette" documents low self-consistency for the same
input across runs at identical hyperparameters. Position, verbosity and
self-enhancement biases are established. Self-consistency does not
establish factuality --- a model can be consistently wrong, and
self-evaluation amplifies systematic bias rather than correcting it,
because it is AI checking AI with no external ground truth.

Three consequences we accept deliberately:

1. Stage 6 is **advisory downward only** (§2.2). Its unreliability can cost
   us a correct claim; it cannot buy a false one past stages 1--5.
2. It must be measured, not asserted. See §5.
3. Disagreement between runs is a signal worth surfacing, not smoothing
   away. A claim that flips verdict across runs is exactly the claim a
   human should look at.

### 2.5 Cost

Published figures for agentic verification loops: 5--15 LLM calls per query
versus one for naive RAG, 4--8s latency versus sub-second, $0.06--$0.31 per
query versus $0.001--$0.005. Our free-tier quota is 20 requests/day/model.

The funnel is what keeps this affordable: stages 1--5 are SQL and string
comparison, and stage 6 is **one batched call for the residue**, not one
call per claim. A ten-claim answer costs one model call, not ten --- and if
the residue is empty it costs none.

------------------------------------------------------------------------

## 3. Milestone 14 --- Currency

**Redefined.** This milestone is no longer about learning from usage.

### 3.1 Why the original definition was dropped

The original M14 promoted knowledge from usage signals: repeatedly useful
citations, repeated research paths, frequently retrieved authorities. The
guarding rule was already that usage may never auto-promote to
authoritative --- which, followed honestly, leaves a pipeline that collects
signals it is forbidden to act on, feeding a read side (Phase 3's Active
Researcher) that has no users. Frequency is not authority, and a design
whose central rule is "ignore the thing this pipeline computes" is not
worth building.

### 3.2 What replaces it

> The law moves. Our copy does not.

Government amends a section. Our stored text is the old text. A user asks;
we answer from the old text --- real id, correctly quoted, properly cited,
and wrong. Every check in M13 passes, because M13 checks the claim against
what we stored, not against what is in force.

India Code publishes consolidated Acts with amendments incorporated and
amendment history in footnotes, and runs roughly six months behind. So the
authoritative current text is fetchable; we simply never re-fetch it.

### 3.3 Incremental synchronisation

Not a full re-scrape. Re-downloading 36,461 sections to find the handful
that moved is wasteful and needlessly rude to a government server, and it
is not what the incumbents do --- Lexis runs continuous editorial updating
and alerting, Shepard's tracks new treatment as it appears. The pattern is
**incremental sync with change detection, plus a slower full reconciliation
to catch what the incremental pass missed.**

India Code exposes enactment and date metadata over its search interface,
so new and recently-changed Acts can be identified without fetching every
Act.

| Source | Incremental | Full reconciliation |
|---|---|---|
| Court judgments | daily--weekly (new documents) | monthly |
| India Code statutes | weekly (changed/new Acts) | monthly |

Reconciliation exists because change detection fails silently: a source
that stops publishing update metadata, or a scrape that quietly returns
stale HTML, looks exactly like "nothing changed". The monthly pass is the
control that distinguishes those. Without it, the most likely failure of
this milestone is that it reports "no amendments" forever and nobody
notices --- the same silent-degradation shape that has produced most of the
bugs in this project.

``` text
scheduled incremental sync
      |
      v
changed/new since last run?     <- source metadata, not a full fetch
      |
      v
fetch only those documents
      |
      v
diff against stored full_text
      |
      +--> formatting-only  -> stop, do not archive
      |
      v
classify: AMENDED | REPEALED | RENUMBERED?
      |
      v
archive old version          <- exists today, never yet fired
      |
      v
stamp the knowledge graph    <- does not exist
      |
      v
impact report                <- the deliverable

      (monthly: full reconciliation over the corpus)
```

**The deliverable is the report, not an auto-correction.** "Section 18 of
act:2158 changed on <date>; here is the diff; 7 judgments and 3 case files
cite it; their reasoning is now suspect." A human decides what follows.

Keeping the old version is what lets the system answer both questions a
lawyer actually asks:

``` text
Section 18
  |-- version observed 2025  <- archived: what the court was reading
  \-- version observed 2026  <- current: what the law is now
```

The no-auto-promotion rule from `DATA_LAYER_ARCHITECTURE.md` §12 survives
the redefinition, with a better justification than before: we do not
silently rewrite the ground a stored analysis stood on.

### 3.4 Why the graph must be stamped

`graphdb/ingest.py` is `MERGE`-only. Nothing is ever deleted or marked. So:

> A judgment has `CITES_SECTION -> act:2158:sec-18`. Section 18 is amended.
> The edge is unchanged. Retrieval returns that judgment as authority on
> the *current* text of s.18, but the court was reasoning about the *old*
> text. We present a real case as support for a proposition it never made.

That is misgrounding (§2.1) produced by our own storage layer rather than
by the model, and M13 cannot catch it --- both documents are real and both
were retrieved. `Section` nodes need an amendment stamp, and
`CITES_SECTION` edges need to record which version the citing judgment saw.

This is also what Phase 7 §1 calls the "temporal legal graph --- was an
authority in force at the relevant time?". Skipping Phase 6 does not remove
this work; it relocates it into Phase 7.

### 3.5 Scope limit: renumbering

Amended and repealed are exact --- text differs, or the section is gone.
**Renumbering is not.** India Code does not state "old s.34 is now s.36";
it must be inferred from text similarity across scrapes, and a wrong
mapping is worse than no mapping, because it silently redirects every
citation to a different provision.

Renumbering ships as a **flagged suspicion for human review, never an
automatic rewrite.** If that cannot be made reliable, it is dropped rather
than shipped confident.

------------------------------------------------------------------------

## 4. Configuration

Each setting exists because a measurement or a constraint forced it, not
for configurability's own sake.

``` python
verification_mode: str = "mechanical"   # mechanical | full
```
`mechanical` runs stages 1--4 only --- zero model calls, and already more
than we ship today (stage 3 quotation matching and stage 4 currency are
both new and both free). `full` adds the stage 6 batched semantic call.

Default stays `mechanical` until §5 produces a number. Shipping an
unmeasured checker on by default is precisely how the vendors in §2.1 came
to make claims the RegLab study falsified.

``` python
verification_scope: str = "statute"    # statute | all
```
`statute` checks only claims citing Act sections. Section text is short,
self-contained and states rules directly, so entailment is tractable.
Judgment entailment needs the ratio separated from obiter --- Phase 7's
IRAC work, not this milestone's.

``` python
verification_strictness: str = "strict"   # strict | lenient
```
`strict` treats `PARTIAL` as unsupported; `lenient` accepts it. Genuinely
two different products: a research query tolerates an overbroad claim
flagged for follow-up; a document headed for filing does not.

``` python
verification_max_passes: int = 2
```
Unchanged from Phase 3. The loop-back must terminate; an answer that ships
with a labelled gap beats one that never ships.

``` python
verification_quote_min_chars: int = 40
```
Stage 3 threshold. Below this a "quotation" is a common phrase that will
string-match by coincidence, which would convert a free decisive check into
a free wrong one.

Currency is a separate job, not part of query serving:

``` python
currency_sync_statutes: str = "weekly"
currency_sync_judgments: str = "daily"
currency_reconcile_full: str = "monthly"
currency_diff_min_ratio: float = 0.02   # below this, treat as formatting
```

------------------------------------------------------------------------

## 5. Evaluation --- required before M13 ships

M13 without a labelled set is the citation guard's situation again: built,
plausible, never proven to fire correctly. `evals/datasets/` gains a
support set of ~30 claim/section pairs:

- ~10 genuinely supported
- ~10 **misgrounded** --- right Act, wrong section; or the section is real
  and relevant but the claim overstates it (the RegLab failure mode, and
  the only rows that actually discriminate)
- ~10 unsupported --- section does not address the proposition

Metrics:

- **precision and recall on UNSUPPORTED** --- does the checker catch
  misgrounding without rejecting good claims?
- **flip rate** --- how often the same pair changes verdict across three
  runs of the same model. This is the direct measurement of the
  self-inconsistency in §2.4, and it decides whether
  `verification_mode = "full"` can be defaulted on.
- **residue rate** --- what fraction of claims survive stages 1--5 and
  reach the model. §2.2.2 assumes this is small; if legal claims are
  mostly paraphrase it will not be, and the funnel's cost saving
  evaporates. Measure it before claiming it.
- **stage attribution** --- which stage caught each rejection. If stage 3
  catches nothing on the misgrounded rows, quotation matching is not
  earning its place and should be cut.

Run across the model chain, as with the contradictions benchmark. Reference:
contradiction detection moved 0.20 -> 0.95 recall between models on the same
28-case set, so the model choice, not the design, may dominate the result
here too.

------------------------------------------------------------------------

## 6. How others do this

Ten searches plus a direct read of NyayAssist, 2026-08-26. Sources in §8.

**Nobody solves it; everybody layers.** The consistent finding is that
retrieval grounding reduces fabrication and does not eliminate
misgrounding. RegLab measured 17--33% hallucination on tools built over
curated proprietary corpora, and specifically falsified LexisNexis's
"100% hallucination-free linked legal citations" and Thomson Reuters's
claim to avoid hallucination by relying on trusted content. The lesson we
take is about **claims**, not architecture: the vendors' failure was
asserting a guarantee they had not measured.

**Harvey** layers structured metadata extraction, embedding search, and
LLM binary document matching, plus a Knowledge Source Identification system
for fuzzy matching against millions of documents with partial or ambiguous
citations. Notably it does **not** verify good-law status itself --- it
integrates LexisNexis Shepardizing for that. Their own guidance still says
every citation must be verified against a primary database before entering
work product.

**Westlaw/CoCounsel** ground in the Westlaw corpus and cite the underlying
material on every answer, with KeyCite supplying treatment flags --- and
KeyCite's Overruling Risk signal is the closest published analogue to §3.4:
it flags a case as suspect because something it *relies on* was overruled,
i.e. staleness propagating along citation edges. That is the mechanism we
need for statutes, applied to precedent.

**Anthropic's Citations API** chunks documents to sentences and has the
model cite spans directly, reporting up to 15% recall improvement over
prompt-based citation and one adopter going 10% -> 0% on source
hallucination. Relevant to us as a cheaper alternative for stage 6:
sentence-level attribution at generation time rather than claim
verification after it. Worth testing against M13 as a baseline.

**Research consensus** is settled on the method (NLI/entailment over atomic
claims: ALCE, FActScore, AttrScore, RAGAS, VerifAI) and equally clear on
its limits (LLM judges are self-inconsistent measurement instruments).
Both halves are in the design: §2.3 takes the method, §2.4 takes the
caveat.

**Guardrails frameworks** (Guardrails AI validators, NeMo Guardrails rails)
supply the composition pattern in §2.2. Neither knows anything about law;
they are plumbing.

### 6.1 India-specific

**Manupatra** has shipped a **Citation Verifier** --- validating whether a
citation exists and is accurate. That is our stage 1, sold as a standalone
product --- a fair signal that stage 1 has real value, and also that stage 1
is where the Indian market currently stops.

**CaseMine** offers Parallel Search: conceptually similar precedents
without keyword overlap, which matters in India where one principle
surfaces across hundreds of rulings in different terminology. That is a
retrieval capability, not verification, and it is close to what our
case-discovery work is reaching for.

The practitioner rule of thumb --- if a case is not in SCC Online,
Manupatra or SCR, it does not exist --- is stage 1 with a human corpus.

### 6.2 NyayAssist (nyayassist.ai)

The closest positional competitor: an Indian AI legal workspace bundling
case management, research, drafting, document storage, translation, a
meeting assistant, a legal library, calendar, and a WhatsApp bot.

The feature overlap with Phases 4--5 is substantial --- case workspace,
document upload, research, drafting. The read is that our phase ordering
matches what an Indian legal workspace is expected to contain.

**What it does not disclose.** It claims "citation-backed" results from a
"refined Indian legal library" and "human-verified intelligence", but
publishes no corpus size, no update frequency, no data sources, no
grounding mechanism, and no hallucination methodology. No number anywhere.

Two conclusions:

1. **Where we can differentiate.** Given RegLab, unmeasured trust claims
   are the industry norm and are falsifiable. Publishing what we measured
   --- including that our citation guard has never fired, and that
   `document_versions` is empty --- is a position none of these products
   currently occupy. Our answer format already distinguishes verified from
   `Could not be verified`.
2. **Where we are behind, and it is not verification.** They have a
   library; we have 18 judgments. No verification layer compensates for a
   corpus that cannot answer the question.

------------------------------------------------------------------------

## 7. Dependency note --- corpus size

M13 stage 6 is scoped to statute (§4) and works today: 36,461 sections.

M14 currency works today for statutes.

Everything *past* Phase 6 does not. Precedent graphs, citation-chain
analysis, conflicting-precedent reasoning, bench-strength reasoning and the
M15 end-to-end benchmark are all built from judgments citing judgments. At
37 judgments there is no chain to analyse and no conflict to detect.

**Growing the judgment corpus is a prerequisite for Phase 7 and is not a
Phase 6 milestone.** Phase 4's case discovery is the mechanism (one query
moved judgments 9 -> 14 and CITES_SECTION edges 24 -> 53). Sustained
crawl rate against the source is unmeasured; measure it on one Act before
promising a number.

------------------------------------------------------------------------

## 8. Sources

Research, 2026-08-26.

- [Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools --- Stanford RegLab](https://reglab.stanford.edu/publications/hallucination-free-assessing-the-reliability-of-leading-ai-legal-research-tools/) ([preprint PDF](https://arxiv.org/pdf/2405.20362))
- [What the Stanford hallucination study actually revealed](https://auryth.ai/en/blog/stanford-hallucination-study-legal-ai/) --- misgrounding
- [Phantom Precedents: The Rise Of AI-Generated Case Law In Indian Courts --- LiveLaw](https://www.livelaw.in/articles/phantom-precedents-ai-generated-case-law-indian-courts-526665)
- [Delhi HC junks plea crafted by ChatGPT with fake quotes & cases --- ThePrint](https://theprint.in/judiciary/delhi-hc-junks-plea-crafted-by-chatgpt-with-fake-quotes-cases-what-it-said-pulling-up-erring-lawyer/2751518/)
- [AI-hallucinated case law: how fake citations are getting lawyers sanctioned in India --- iPleaders](https://blog.ipleaders.in/ai-hallucinated-case-law-fake-citations-india/)
- [Accelerating Legal Work With AI for Legal Research --- Harvey](https://www.harvey.ai/blog/ai-for-legal-research-guide)
- [Harvey: Scaling AI Evaluation for Legal AI Systems --- ZenML LLMOps Database](https://www.zenml.io/llmops-database/scaling-ai-evaluation-for-legal-ai-systems-through-multi-modal-assessment)
- [Accuracy in AI: Reducing hallucinations at work --- Thomson Reuters](https://www.thomsonreuters.com/en/insights/articles/accuracy-in-ai)
- [Westlaw tip: Checking Cases with KeyCite --- Thomson Reuters](https://legal.thomsonreuters.com/blog/westlaw-tip-of-the-week-checking-cases-with-keycite/)
- [Introducing Citations --- Anthropic](https://anthropic.com/news/introducing-citations-api) ([analysis](https://simonwillison.net/2025/Jan/24/anthropics-new-citations-api/))
- [Rating Roulette: Self-Inconsistency in LLM-As-A-Judge Frameworks](https://arxiv.org/html/2510.27106v1)
- [A Survey on LLM-as-a-Judge](https://arxiv.org/pdf/2411.15594)
- [Do LLM Attribution Metrics Transfer? Auditing RAG Evaluation](https://arxiv.org/html/2606.23915) --- ALCE, FActScore, AttrScore, RAGAS
- [CLATTER: Comprehensive Entailment Reasoning for Hallucination Detection](https://arxiv.org/html/2506.05243v1)
- [ClaimVer: Explainable Claim-Level Verification and Evidence Attribution Through Knowledge Graphs](https://arxiv.org/html/2403.09724)
- [Guardrails AI and NVIDIA NeMo Guardrails --- a comprehensive approach](https://guardrailsai.com/blog/nemoguardrails-integration)
- [Agentic RAG: production architecture guide](https://tianpan.co/blog/2026-02-11-agentic-rag-architecture-production-guide) --- cost/latency figures
- [Manupatra AI Launches 'Citation Verifier' --- The Wire](https://m.thewire.in/article/ptiprnews/manupatra-ai-launches-citation-verifier-to-tackle-fake-and-inaccurate-legal-citations-in-the-age-of-ai)
- [Best Legal Research Tools in 2026 for Indian Lawyers --- CaseMine](https://www.casemine.com/blog/best-legal-research-tools-2026-india-ai)
- [AI in Legal Research for Indian Lawyers: How to Search, Verify, and Cite --- BharatLaw](https://www.bharatlaw.ai/post/ai-in-legal-research-for-indian-lawyers-how-to-search-verify-and-cite-like-a-pro)
- [KeyCite --- Westlaw](https://legal.thomsonreuters.com/en/products/westlaw/keycite)
- [Lexis+ with Protege --- legal research](https://www.lexisnexis.com/en-us/products/lexis-plus-protege/legal-research.page)
- [The Legal AI Journey: From Task-Specific Tools to Integrated Intelligence --- LexisNexis](https://www.lexisnexis.com/community/pressroom/b/news/posts/the-legal-ai-journey-from-task-specific-tools-to-integrated-intelligence)
- [Shepard's Coverage --- LexisNexis Support](https://supportcenter.lexisnexis.com/app/answers/answer_view/a_id/1087952/~/shepards-coverage)
- [NyayAssist](https://nyayassist.ai/)
- [India Code --- Digital Repository of All Central and State Acts](https://services.india.gov.in/service/detail/india-code-digital-repository-of-all-central-and-state-acts)

------------------------------------------------------------------------

## 9. Milestones

### Milestone 13 --- Support verification

Build the funnel of §2.2 in stage order, cheapest first:

1. **Stage 3, quotation matching** --- deterministic, free, catches the
   Delhi HC failure mode. Ship this before anything involving a model.
2. **Stage 6, batched entailment** --- gated behind `verification_mode`,
   shipped only with the §5 labelled set, a measured flip rate and a
   measured residue rate.

Stages 1--2 exist. Stage 4 arrives with M14. Stage 5 is Phase 7.

### Milestone 14 --- Currency

Incremental synchronisation with change detection, monthly full
reconciliation, diff, amendment classification, graph stamping, impact
report. Renumbering flagged for human review only.
`knowledge/active/` per `PROJECT_STRUCTURE.md` §9 is repurposed to hold
this.

------------------------------------------------------------------------

## 10. Deliverable

> A claim is checked against what its cited section actually says, not just
> that the section exists --- and when the law changes, we know which
> stored answers it undermines.

------------------------------------------------------------------------

## 11. Explicitly not in this phase

``` text
Judgment entailment (ratio vs obiter)   -> Phase 7 (IRAC)
Overruled / negative-treatment detection-> Phase 7 (precedent graph)
GraphRAG / precedent graph              -> Phase 7
Conflicting-precedent reasoning         -> Phase 7
Indian legal benchmarks                 -> Phase 7
Growing the judgment corpus             -> prerequisite for Phase 7, not a
                                           Phase 6 milestone (§7)
```
