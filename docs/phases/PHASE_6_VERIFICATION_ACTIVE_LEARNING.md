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

Measured 2026-08-28. **M13 is built and measured. M14 is not started.**

``` text
act sections                 35,601
acts                            860
judgments                     5,826    26 courts; Supreme Court 1,366
document_versions                 0    M14 has not run
```

M13 shipped as a funnel (§2.2): deterministic stages that always run, and a
Verification Agent behind `verification_level`. Measured over 50 frozen
claims, 2 runs on the model chain (§5):

``` text
                    deterministic only    with the agent
exact verdict               0.18                0.94
catch rate                  1.00                0.97
false alarms                0.84                0.00
stage mismatches               0                   0
flip rate                      -                0.06
```

The comparison is the result, not the 0.94. Deterministic checks alone
"catch everything" by flagging 84% of correct claims, which is a checker a
reader learns to ignore within a day.

### 1.1 What is checked, and what is not

| Check | Status |
|---|---|
| Fabricated document id | built, stage 1 |
| Claim cites nothing | built, stage 1 |
| Cited but never retrieved | built, stage 2 |
| Quoted words absent from the cited text | built, stage 3 |
| Cited text does not support the claim | built, stage 6 (agent) |
| Cited text has since been amended | **M14, not started** |
| Judgment overruled / negative treatment | Phase 7 |
| Wrong jurisdiction / court hierarchy | Phase 7 |

`document_versions` is still 0: nothing re-scrapes, so the amendment path
has never run against real data. Treat it as unproven.

------------------------------------------------------------------------

## 2. Milestone 13 --- Support verification

### 2.0 The cardinal rule

> **Never turn "we didn't find it" into "it doesn't exist."**

This governs everything below, and it is written here rather than buried in
an implementation note because every other decision in this phase follows
from it.

Verification is **not a gate that blocks answers.** It is an evidence-quality
layer that says how strongly each claim can be made. A verifier that
suppresses an answer whenever our corpus is thin does not produce a careful
product; it produces a useless one, and it produces a *dishonest* one,
because silence reads to a user as "there is nothing there."

With 4,658 judgments against a live Indian corpus in the crores, absence of
evidence is our normal condition, not an edge case. A design that treats
"not found" as "not so" would be wrong on most queries it ever sees.

So verification **rejects false certainty, not answers.**

### 2.0.1 Four states, not two

`SUPPORTED` / `UNSUPPORTED` is too coarse, and the coarseness is exactly
where the dishonesty enters.

| State | Meaning | Who decides |
|---|---|---|
| `SUPPORTED` | Retrieved evidence establishes the claim | stage 3 or stage 6 |
| `PARTIALLY_SUPPORTED` | Evidence supports part; the claim overstates or narrows | stage 6 |
| `INSUFFICIENT_EVIDENCE` | We did not retrieve material capable of settling this | **retrieval, mechanically** |
| `UNSUPPORTED` | We retrieved relevant material and it does not support the claim | stage 6 |

**`UNSUPPORTED` is not "no data".** One is a finding against the claim; the
other is a gap in our shelf. Presenting a gap as a finding is the same
category of error as presenting a guess as a citation.

### 2.0.2 The guard: who is allowed to say INSUFFICIENT

A four-state scheme has an obvious failure mode --- `INSUFFICIENT_EVIDENCE`
becomes a soft landing where anything awkward gets filed to avoid the
harder verdict, and the checker quietly stops checking.

The guard is that **the model never chooses between `INSUFFICIENT_EVIDENCE`
and `UNSUPPORTED`.** That distinction is a retrieval fact, not a judgement:

``` text
did retrieval return material on this claim's subject?
   |
   +-- no  -> INSUFFICIENT_EVIDENCE      (mechanical, stage 6 never runs)
   |
   +-- yes -> stage 6 decides only between
              SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED
```

Stage 6 is handed only claims whose evidence exists. It is never offered
"I couldn't find anything" as an available answer, so it cannot hide behind
one.

### 2.0.3 Coverage and confidence are different axes

Conflating these is how a system ends up sounding certain about a corner of
the law it never looked at.

``` text
Confidence:  how strongly the evidence we found supports the claim
Coverage:    how much of the relevant source universe we actually searched
```

They move independently, and today they are far apart:

``` text
Confidence: HIGH      the sections and judgments we found do support this
Coverage:   LIMITED   4,658 judgments; 25 High Courts; no district courts
```

Reporting only confidence would be a true statement that leaves a false
impression. Both go in the answer.

### 2.0.4 What the reader sees

The answer ships either way. What changes is the annotation around it:

``` text
Based on the sources reviewed:
  <the answer>

Relevant authorities:
  <citations>

Coverage limitation:
  No Gujarat High Court authority on this point was found in the
  corpus searched. This part should be independently verified.
```

That is a stronger legal product than either hallucinated certainty or a
refusal, because it tells the reader where the evidence stops --- which is
the thing a lawyer actually needs in order to know what to do next.

------------------------------------------------------------------------

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

### 2.2.2 What routes a claim to stage 6

Batching the residue into one call is right, and the cost saving is real.
But a claim that survives the mechanical stages is not thereby *verified*,
and that distinction decides whether the design works.

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

The size of that residue is unmeasured. If legal answers are mostly
paraphrase, it is large and the saving is small. §5 measures it rather than
assuming it.

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
because it needs a citation graph we do not have: 3,823 citations were
extracted from the corpus and 2 resolved (§7).

### 2.4 Known weakness

Stage 6 is an LLM judge, and LLM judges are measurably unreliable
instruments. "Rating Roulette" documents low self-consistency for the same
input across runs at identical hyperparameters. Position, verbosity and
self-enhancement biases are established. Self-consistency does not
establish factuality --- a model can be consistently wrong, and
self-evaluation amplifies systematic bias rather than correcting it,
because it is AI checking AI with no external ground truth.

Three deliberate consequences:

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

## 4. Verification is a mode the user chooses

Running the full funnel on every query is the wrong default. A student
asking "explain Section 138 simply" does not need semantic claim
verification; a lawyer filing on Monday does. Forcing the expensive path on
both wastes tokens on one and is the right price for the other.

So verification level is a **user-facing research mode**, not a hidden
setting.

``` text
Quick       research -> analyst -> answer
            always-on mechanical checks only

Research    deeper retrieval, more sources
            always-on mechanical checks only

Verified    the above, plus stage 6 semantic verification
            + a verification report
```

### 4.1 The line between always-on and opt-in

Cheap deterministic checks are **never optional.** They cost nothing, and a
fabricated citation reaching a user in "Quick" mode would be indefensible
--- Quick means less verification effort, never *no* integrity.

| Stage | Quick | Research | Verified |
|---|---|---|---|
| 1 citation exists | always | always | always |
| 2 retrieved by this thread | always | always | always |
| 3 quotation matches | always | always | always |
| 4 version current | always | always | always |
| 6 semantic support | -- | -- | **on** |

Every always-on row is SQL or string comparison. The only thing the user is
opting into is model spend.

### 4.2 The mode must not change the answer

A hard invariant, and a testable one:

> The same question over the same evidence produces the **same answer body**
> in Quick and in Verified. Verified adds annotation; it does not rewrite,
> soften or truncate.

If turning verification on changed the substance of the answer, the user
would be choosing between two different opinions of the law based on
budget, which is indefensible in a legal product. Verification is an audit
layer over an answer, not a second author of it.

``` text
QUICK                      VERIFIED
"Here is the answer..."    "Here is the same answer..."
                             + citation verified
                             + section text verified
                             + claim 4 PARTIALLY_SUPPORTED
                             + coverage: limited (1 High Court)
```

§5 tests this invariant directly, because it is the kind of property that
decays silently the moment the two paths diverge in code.

### 4.3 A selected mode must never silently downgrade

If `Verified` is requested and stage 6 cannot run --- quota exhausted, model
chain failing, timeout --- the answer says so. It does not quietly return
Quick output wearing a Verified label.

This is stated explicitly because silent degradation is the single most
common defect found in this project: `.env` never loaded, token caps
starving answers, `_check_db` scanning the corpus, extraction failure
indistinguishable from an empty document. Every one presented a broken
result as a normal one. A verification badge that can appear without
verification having happened would be the worst instance of the pattern,
not the least.

### 4.4 Settings, as built

``` python
verification_level: str = "quick"   # quick | verified
```

On the graph state as well as in config, so one thread can be checked
harder than another without changing a global.

The default is `quick` **because of §5.3**, not to save money: the agent
still approves about one claim in fifty that it should not. Spending on a
check that reduces rather than removes false certainty is the reader's call
to make.

``` python
max_verification_passes: int = 2
```

The loop-back must terminate; an answer that ships with a labelled gap
beats one that never ships.

``` python
MIN_QUOTE_CHARS = 40          # verification/quotes.py
```

Below this a "quotation" is a common phrase that matches by coincidence,
which would turn a free decisive check into a free wrong one.

Currency (M14) is a separate job, not part of query serving, and is not
built:

``` python
currency_sync_statutes    weekly
currency_sync_judgments   daily
currency_reconcile_full   monthly
```

### 4.5 Where the code lives

``` text
schemas/verification.py       Claim, Verdict, ClaimVerdict, VerificationReport
verification/groundedness.py  stages 1-2   SQL, no model
verification/quotes.py        stage 3      string compare, no model
agents/verifier.py            stage 6      the only part that reasons
verification/pipeline.py      stage order and routing
graph/nodes/__init__.py       verification() -- wires it into the graph
```

The agent sits in `agents/` with the other roles that call a model; the
lookups stay in `verification/`. That split is the boundary between
checking by looking something up and checking by reading it.

------------------------------------------------------------------------

## 5. Evaluation --- what was measured

`evals/datasets/verification.json`, `evals/run_verification.py`.

### 5.1 Why the answers are frozen

The 50 claims are fixtures written against the **real stored text** of the
sections they cite. Answers are not generated at eval time, so the verifier
is the only variable: the inputs are deterministic, the run is cheap to
repeat across the model chain, and the number is attributable to the
checker rather than to whichever model happened to write the answer.

``` text
SUPPORTED             17
UNSUPPORTED           17
PARTIALLY_SUPPORTED   14
INSUFFICIENT_EVIDENCE  2
```

Nine carry an `expected_stage`: a claim a string comparison can settle must
not cost a model call, and that is checkable rather than assumed.

### 5.2 Results --- 50 cases, 2 runs, model chain

``` text
                    deterministic only    with the agent
exact verdict               0.18                0.94
catch rate                  1.00                0.97
false alarms                0.84                0.00
residue rate                0.00                0.82
stage mismatches               0                   0
flip rate                      -                0.06
```

- **False alarms 0.84 -> 0.00.** Every flag the agent raises is deserved.
  This is what the model stage buys, and without the baseline column it
  would look like an unearned 0.94.
- **Stage mismatches 0.** All nine quote and reference cases settled before
  the model, including the Delhi HC failure shape (`quote-04`: real
  section, invented words) caught by string comparison at zero cost.
- **Flip rate 0.06.** Low enough to default `verified` on. The
  LLM-as-judge literature (§2.4) predicted this might not hold; it did.

### 5.3 The failure that remains

Roughly **one claim in fifty is approved that should not be, and which one
varies between runs**:

``` text
run 1   uns-09    "the Centre must consist of at least seven members"
                  -> SUPPORTED, from a section stating no number
run 2   part-03   an overstated claim read as SUPPORTED
```

A false statement of law presented as checked is the failure this phase
exists to prevent, so it is recorded rather than averaged into the 0.94.
Verified mode **reduces false certainty; it does not remove it**, and no
product surface may claim otherwise.

The direction is at least the safer one: of the misses, all but these err
toward over-flagging, which costs a reader a second look rather than
misleading them.

### 5.4 Residue is 0.82, not small

The funnel's cost argument assumed most claims would drain out before the
model. They do not: legal claims are overwhelmingly paraphrase, so 41 of 50
reached it. The saving is real but comes from **batching**, not from
draining -- one call per answer rather than one per claim.

### 5.5 The dataset's real limitation

One author wrote both the claims and the labels. Two labels were wrong
(`sup-06`, `sup-15` -- both dropped a condition the section imposes) and
were found only because the agent disagreed; they are corrected and
relabelled `part-11` and `part-12`, with the reason recorded in the file.

That cuts both ways: there may be labels where the agent agreed with a
mistake and neither party noticed. **50 statute-only cases from one author
is a floor, not a verdict.** A set written independently, or drawn from
judgments rather than sections, would be a materially stronger test.

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

## 7. Dependency note --- the precedent graph

Judgment-to-judgment citation resolution is the gate on every Phase 7 item
built from citation chains. It does not work yet, and the reason is
coverage rather than parsing.

### 7.1 Citation resolution

`extract_citations` covers SCC, SCR, INSC, AIR and GLR, matching on a
normalised key (`normalise_citation`) because the source PDFs print the
same case as `S.C.R.`, `S C R` and `SCR`, sometimes within one document.
`scripts/rebuild_citation_edges.py` recomputes edges corpus-wide, which is
required because `write_judgment` resolves only against judgments already
stored --- during a sequential ingest an edge can otherwise point only
backwards.

``` text
judgments                      4,658
carrying a citation of their own 199
CITES edges                       11
unresolved references          8,276
```

### 7.2 Why corpus growth did not help

The corpus grew from 415 to 4,658 judgments across 26 courts. `CITES`
stayed at 11, and the count of citable documents stayed at 199.

**High Court judgments carry no citation of their own.** The archive's High
Court parquet has no citation column (nor petitioner/respondent columns).
An HC judgment can therefore cite others, but nothing can ever cite *it* --
it has no identity to be cited by. Every one of the 4,243 judgments added
was an HC judgment, so none of them became citable.

The 199 citable documents are the Supreme Court set, which carries SCR
citations.

### 7.3 What the unresolved references are

``` text
SCC        no judgment in the corpus carries an SCC identity
SCR        cites to Supreme Court cases we do not hold
AIR / GLR / INSC
```

Two problems, only one of which is a parsing problem:

- **Cases absent from the corpus.** Acquirable. The unresolved list is a
  ranked **target list**: the authorities our own judgments reach for most
  often. This is what citation-guided ingest consumes.
- **SCC references.** Cannot resolve by string matching at all. SCC and SCR
  are different reporters with unrelated volume and page numbers and no
  formula between them. This needs a parallel-citation table -- data
  acquisition, not parsing.

### 7.4 Consequence for Phase 7

Judgment *count* is not the binding constraint; which judgments are held,
and whether they carry a citable identity, is. Bulk High Court ingest
cannot move the precedent graph by any amount.

Phase 7's precedent work depends on:

1. **Supreme Court depth before 2016** --- SC judgments are citable and are
   what the unresolved SCR references name.
2. **Citation-guided ingest** --- fetch the ranked targets, rebuild, repeat.
3. **SCC/SCR parallel-citation mapping** --- for the references string
   matching can never reach.

None is a Phase 6 milestone; all three are Phase 7 prerequisites.

This is also §2.0 as an engineering fact rather than a principle: absence of
evidence is the normal condition here, and a verifier reading "not found"
as "not so" would be wrong on nearly every citation in this corpus.

### 7.5 Text quality

The ingest gate (`_text_check`) requires both a length floor and a minimum
alphabetic ratio. Length alone admitted two failure modes: PDFs with a
broken font encoding map, which extract as mojibake rather than failing,
and scanned judgments whose only text layer is the registrar's e-signature.
Both were stored, embedded and chunked, and competed for slots in vector
search against real judgments.

``` text
alphabetic ratio    real judgment prose   0.60 - 0.80
                    mojibake              0.00 - 0.12
threshold           MIN_ALPHA_RATIO       0.15
```

`scripts/purge_unreadable_judgments.py` selects by the same predicate the
gate applies to new documents, so what it removes is exactly what would be
refused today, and writes a report before deleting.

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
- [Authority Matters: Cite Checking & Verification in the AI Era --- LexisNexis](https://www.lexisnexis.com/community/infopro/b/researchtip/posts/authority-matters-cite-checking-verification-in-the-ai-era)
- [Using Shepard's BriefCheck on Lexis](https://supportcenter.lexisnexis.com/app/answers/answer_view/a_id/1090314/~/using-shepards-briefcheck-on-lexis)
- [AI Traceability and Verification: The New Standard --- LexisNexis](https://www.lexisnexis.com/community/insights/professional/b/industry-insights/posts/ai-traceability)
- [NyayAssist](https://nyayassist.ai/) --- [research](https://nyayassist.ai/research), [case management](https://nyayassist.ai/case-management)
- [India Code --- Digital Repository of All Central and State Acts](https://services.india.gov.in/service/detail/india-code-digital-repository-of-all-central-and-state-acts)

------------------------------------------------------------------------

## 9. Milestones

### Milestone 13 --- Support verification  **DONE**

Built: four-state verdicts with the retrieval-decides guard; quotation
matching; the Verification Agent; the funnel; `verification_level`; 50-case
labelled eval. Measured in §5. 51 tests.

Two invariants are enforced by test rather than by documentation:

- **Answer stability** -- the same question over the same evidence produces
  the same answer body in both modes. Verification annotates; it never
  rewrites, softens or removes.
- **No silent downgrade** -- a `verified` run that cannot verify raises
  rather than returning quick output wearing a verified label.

Not built, and deferred deliberately: stage 4 (version currency) arrives
with M14; stage 5 (authority status) needs a citation graph the corpus
cannot yet support (§7).

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
