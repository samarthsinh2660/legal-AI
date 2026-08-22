# Phase 3 — Research Agent System — Design

**Status:** approved in discussion, pending user review of this document
**Phase doc:** [`docs/phases/PHASE_3_RESEARCH_AGENTS.md`](../../phases/PHASE_3_RESEARCH_AGENTS.md)
**Depends on:** Phase 2 (complete — hybrid retrieval, reranking, tool contracts)

---

## 1. Goal

> Can AI perform legal research, instead of merely performing search?

Phase 2 built tools that return `Evidence` for a query. Phase 3 builds the
system that decides *what* to search, *when* to search again, judges whether
what came back is enough, and presents a grounded answer.

---

## 2. Three decisions that reshape the phase doc

The phase doc as written is superseded on two points. Both changes are
reductions, and both are recorded here so the divergence is deliberate
rather than accidental.

### 2.1 Split by sub-question, not by data source

`PHASE_3_RESEARCH_AGENTS.md` §1 draws three sub-agents named after the three
data layers. They do not survive contact with what Phase 2 actually built:

| Named agent | What it does | Needs an LLM? |
|---|---|---|
| Static Researcher | `hybrid_search` over the stored corpus | No — it is a query |
| Dynamic Researcher | live fetch from Bharat Courts / Indian Kanoon | No — it is an HTTP call |
| Active Researcher | reads what Phase 6 validation approved | No — and Phase 6 does not exist |

`tools/judgments.py:search_judgments` already checks the database first and
falls through to a live fetch. The static/dynamic split collapses into one
boolean inside one function; two agents would mean two LLMs deciding which
branch of an `if` to take.

Static / dynamic / active is a **data-layer authority taxonomy**. It is
load-bearing in `PROJECT_STRUCTURE.md` §9, where it governs what may be
promoted into authoritative knowledge. It is not an axis to spawn agents on.

**The axis that does justify parallel agents is the sub-question.** A large
legal question genuinely decomposes into distinct angles — for a builder-delay
matter: the RERA remedy, the consumer-forum remedy, limitation, and the
contractual clause. These are different research problems with different
sources and different answers. Splitting there is real division of labour;
splitting by data source was not.

This also delivers the context isolation that §2.1 of the earlier draft said
was not yet needed. It is needed once fan-out exists: `../agents`
(`src/agents/research/deep_researcher.py`) runs each sub-researcher as a
subgraph that ends in `compress_research`, so the supervisor receives **N
summaries, not N x 10 documents**. Without that compression step, fan-out
would put every retrieved document into one window.

**Decision:** a Supervisor that decomposes the question into N angles and
fans out to N research agents, each holding the Phase 2 tools and each
compressing before returning. N is capped by configuration (§5.3).

### 2.2 Active knowledge is a coverage check, not a research step

Two failure modes are conflated in the phase doc:

| Failure | Description | Caught by |
|---|---|---|
| Hallucination | claims something the evidence does not support | groundedness check |
| **Miss** | never retrieved the relevant law at all | **nothing** |

Verification only inspects what was said. Nothing inspects what was *not*
said. Active knowledge — the memory of which authorities mattered for
questions like this one — is the correct answer to the second failure.

It must run **after** research, not before. Before research it anchors the
agent onto previously-taken paths and degrades into replaying old answers.
After research it asks the question nothing else asks:

> Threads resembling this one relied on Section X and *Judgment Y*. This run
> retrieved neither. Deliberate, or missed?

**Decision:** Active is a node in the verification stage, not a researcher.
Milestone 8 therefore builds a real node with a real contract; its
data source is empty until Phase 6 populates it. Until then the same slot
runs a deterministic stand-in (below, §7.3).

---

### 2.3 The supervisor decides angles and depth — nothing else

"When do we do dynamic research?" and "when do we call active?" both dissolve
on inspection. Neither is an orchestration decision.

**Dynamic is a fallthrough inside a tool, already built.**
`tools/judgments.py:search_judgments` checks the database and falls through to
a live fetch on a miss. An agent never chooses to "go dynamic"; it searches,
and the miss is handled beneath it.

The one real choice is `skip_db=True`. Its docstring covers one case — a
cached match that proved to be the wrong document. A second case is not yet
handled: **staleness.** If the corpus holds a 2019 judgment since overruled,
a cache hit is a wrong answer delivered confidently. That is a property of
the *question*, not of any individual search, so the Context Builder sets a
`needs_current_law` flag once and the tools honour it. One decision per
thread, not per search.

**Active is an unconditional node.** "Which authorities mattered in threads
like this?" is a lookup — cheap and deterministic. It always runs, in the
verification stage (§7.3). Nothing decides whether to call it.

What remains for the Supervisor is exactly two judgments: **how many angles,
and go again or stop.** Everything else in the pipeline is fixed.

---

## 3. Orchestration: fixed pipeline, agency confined to the research stage

Rejected: **supervisor-as-router**, where an LLM picks the next *pipeline*
node each turn. The execution path then differs every run, cost is unbounded,
and there is no fixed thing for the harness to measure — which conflicts
directly with the harness-first decision.

Chosen: **a fixed outer pipeline containing one bounded agentic research
stage.** Legal work has a genuinely fixed shape — understand, research,
analyse, check, present. The variability is entirely in *how many angles and
how deep*. The agency goes exactly there.

Note the Supervisor is agentic *within* the research stage — it decides the
decomposition, the fan-out, and whether to go again — but it never decides
whether verification runs. That distinction is what keeps the pipeline
evaluable.

```text
        user question  (+ documents, + case)
                |
        +-------v--------+
        | Document node  |  conditional: only if documents attached
        +-------+--------+  (pass-through until Phase 4)
                |
        +-------v--------+
        | Context Builder|  ThreadContext — built ONCE, read-only
        +-------+--------+  case_id optional; sets court + date filters
                |
        +-------v--------+
        | Clarification? |--- blocking gap (state / date / forum)
        +-------+--------+          |
                |                   +--> ASK USER, then resume
                | no gap
   =============v=====================================  RESEARCH STAGE
   |    +-------v--------+                           |
   |    |   SUPERVISOR   |  decompose into N angles  |
   |    |   (decompose)  |  breadth forced up front  |
   |    +-------+--------+                           |
   |            | fan out, capped at N               |
   |    +-------+-------+-------+                    |
   |    |       |       |       |                    |
   |    v       v       v       v                    |
   |  [RA 1] [RA 2] [RA 3] ... [RA N]  parallel      |
   |    |       |       |       |   each: search     |
   |    |       |       |       |   loop -> COMPRESS |
   |    +-------+---+---+-------+                    |
   |                |                                |
   |    +-----------v----+                           |
   |    |   SUPERVISOR   |  reflect: enough, or      |
   |    |   (reflect)    |  another round?           |
   |    +-----------+----+                           |
   |                |  loop back, capped             |
   |                +------> (up to max iterations)  |
   ==================v==================================
                     |
             +-------v--------+
             |    Analyst     |  structured claims, each carrying
             +-------+--------+  its Evidence id
                     |
             +-------v--------+
             |  VERIFICATION  |  unsupported -> re-research
             |  + coverage    |  HARD CAP: 2 passes
             +-------+--------+
                     |
             +-------v--------+
             |  DRAFT/REPORT  |  DraftAnswer — the UI contract
             +-------+--------+
                     |
                     v
                   user
```

**The full skeleton is built now.** Document, Analyst, Verification and Draft
land as thin pass-through nodes with real schemas, filled in during Phases
4-6. Building only Phase 3's nodes would mean reshaping the orchestration
three times.

---

## 4. Shared thread context

Implements `AI_PROJECT_PROPOSAL.md` §6 unchanged. Built once per thread,
passed read-only to every node.

Rules carried over verbatim from the proposal:

1. Built once per thread, not per agent.
2. Nodes receive it read-only and cannot mutate shared state.
3. A node returns findings; only the pipeline itself promotes a finding into
   `established_findings`.
4. Follow-up questions reuse and extend the context rather than rebuilding.
5. Promoted findings keep provenance, so verification can trace them.
6. Versioned — each promotion produces a new revision, making a thread
   reproducible.
7. Changing jurisdiction, adding a document or correcting a fact revises the
   context and invalidates cached findings that depended on the changed field.

### 4.1 Clarification gate

Research does not start while a missing fact would make it wrong. The gate
asks **only when the gap is blocking**, then proceeds silently otherwise.

Blocking gaps in Indian practice are specific and enumerable: **state** (RERA
is state-wise, stamp duty and rent law vary), the **relevant date** (which
limitation period, which version of the section), and **forum/stage** where
the remedy depends on it. A missing state does not degrade the answer — it
invalidates the whole run, so discovering it after a three-way fan-out wastes
everything.

`../agents` carries this as `allow_clarification` and skips it by default.
For open-web research that is right. For legal it is not.

Non-blocking gaps are assumed, and the assumption is stated in the answer.

### 4.2 Case scope — threads attach later, not up front

`design/UX_FLOWS.md` (§lines 97-100, 162-176) already requires this and it is
binding:

- A thread may belong to no case. A student researching a doctrine never
  needs one, and most threads never get attached.
- An unattached thread offers **Attach to case**; Flow A is chat -> *Save to
  case* -> choose an existing case or create one.
- On attaching, the thread's context is **seeded with that case's parties,
  timeline and already-established findings**.
- One case contains many research sessions.

So `case_id` is **optional and set at any time**, never required at thread
creation. Attaching is a context revision under rule 7 above: it adds the
case's established findings, and invalidates any thread finding whose
jurisdiction or date assumptions the case contradicts.

Building this now costs one optional field plus a findings-by-case lookup.
Retrofitting it later is a data migration.

### 4.3 Filters the context must populate

Phase 2 shipped `retrieval/metadata.py:MetadataFilters` with `court`,
`decision_date_from`, `decision_date_to`, `act_id` and `document_type`.
**Nothing currently populates them.** The Context Builder does:

- **Jurisdiction -> `court`.** A Gujarat matter weights Gujarat High Court
  over Madras. Binding authority is not a ranking preference.
- **Relevant date -> `decision_date_*`.** The law as it stood when the cause
  of action arose may differ from today's.

Every tool call in the thread inherits these. The plumbing exists; this is
wiring, not new machinery.

`serialization.py` matters disproportionately: the context is injected into
every node's prompt, so it needs a compact, stable text form.

---

## 5. The research stage

### 5.1 Supervisor — decompose

Breadth is forced **up front** rather than left to the model to discover.
`../agents` learned this the hard way: its `decompose_subtopics` node exists
explicitly "instead of relying on the model to decide when it has 'enough'"
(README), generating 3-5 angles before the supervisor loop starts.

For legal research the angles are things like: which statutory remedy
applies, which forum has jurisdiction, what limitation period governs, what
the leading precedent holds, what the contract itself says. The Context
Builder's issue list seeds this.

Decomposition is skipped for questions that plainly have one angle. Spawning
four agents to look up one section is waste.

### 5.2 Research agents — plan, execute, validate, compress

**The LLM never calls a tool.** It is invoked at exactly two bounded points
per round, and each produces *data*, not actions:

```text
Orchestrator      decides the research stage runs
      |
      v
Agent call 1      BOUNDED REASONING -- emits a structured plan:
                  [{tool: search_statutes, query: "..."},
                   {tool: get_section, act_id: "act:1978", number: "7"}]
      |
      v
Orchestrator      executes the plan. Control flow lives here.
      |
      v
Tool              Phase 2 contracts, unchanged
      |
      v
Validator         deterministic gate -- see 5.5
      |
      v
State update      only validated Evidence enters state
      |
      v
Agent call 2      BOUNDED REASONING -- "sufficient" or "still missing X"
      |
      v
Orchestrator      loop or stop; the cap is enforced here, not in the prompt
```

The LLM handles ambiguity and judgement. The orchestrator handles control
flow. Keeping that boundary is what makes the stage testable and its cost
knowable in advance.

**Rejected: a ReAct tool loop.** Letting the model choose which of seven
tools to call, up to N times, hands control flow to the LLM. A cap bounds
the damage without changing who drives. Three concrete costs made the
difference:

- **Testability.** A canned plan can be fed to the orchestrator and its
  execution asserted. A ReAct loop cannot be unit-tested that way.
- **Cost is knowable before it is spent.** A four-step plan costs four tool
  calls. A ReAct loop costs *up to* eight, discovered afterwards.
- **API budget.** Two model calls per angle instead of up to eight. On the
  free tier this is the difference between a working day and an exhausted
  quota (§8.1).

**The cost of this choice, stated honestly:** ReAct adapts mid-flight; if
step 1 returns something surprising, it changes step 2. Plan-then-execute
adapts only on the next round. The outer loop, capped at 3, gives two
chances to adapt.

The measured failure mode makes that acceptable. Retrieval's dominant error
is *right Act, wrong section* -- 9 of 11 misses on the 6.1 benchmark returned
the correct Act without the correct section. The adaptation actually needed
is mechanical: having seen the right Act, call `get_section` on it. A plan's
second round handles that.

Tools available to a plan are the Phase 2 contracts, unchanged:

```text
tools/statutes.py    search_statutes, get_statute, get_section
tools/judgments.py   search_judgments, get_judgment
tools/graph.py       find_citations, find_section_citations,
                     find_judgment_sections
```

No tool signature changes in this phase. If a plan needs something these do
not offer, that is a finding to record, not a licence to widen the contract
mid-phase.

Each agent ends by **compressing** its validated findings before returning.
This is what makes fan-out affordable: an agent's raw retrieval stays in its
own window rather than the supervisor's. Compression must preserve Evidence
ids -- see 5.5, which enforces it rather than trusting it.

### 5.3 Caps

`../agents` ships these defaults (`src/agents/research/configuration.py`):

| Cap | Their default | Ours | Why different |
|---|---|---|---|
| `max_concurrent_research_units` | 5 | **3** | Gemini free tier; 5 x 10 tool calls per round will hit rate limits |
| `max_researcher_iterations` | 6 | **3** | supervisor reflection rounds; legal angles are narrower than open-web topics |
| plan steps per round | 10 (`max_react_tool_calls`) | **8** | a plan may contain at most 8 tool steps |

All configurable, all enforced in code rather than in the prompt. Their
overflow handling is worth copying exactly: calls beyond the cap return a
`ToolMessage` explaining the limit, so the model is told rather than silently
truncated.

**The loop always terminates on the cap.** It never relies on the model
choosing to stop.

### 5.4 Stop rule

Within the caps, the Supervisor judges: it reads the compressed findings and
either declares coverage sufficient or names what is still missing. A fixed
search count wastes calls on easy questions and under-serves hard ones; a
purely coverage-driven rule is only as good as the issue list. The judgment
is honestly a judgment — the caps are what make cost predictable and the loop
testable.

---

### 5.5 The validator — a deterministic gate at the tool boundary

Every tool result passes this before entering state. **No LLM.** It cannot
itself hallucinate, which is the entire point of putting it here rather than
relying on end-of-pipeline verification.

Checks:

- `document_id` is present and resolves to a row in `documents`
- `provenance` is present, with a source name and URL
- the passage is non-empty
- after compression, every Evidence id referenced by a finding still exists
  in the validated set

That last check is the one that matters most. §13 records compression
silently dropping Evidence ids as the phase's highest risk: it makes every
downstream claim ungroundable, and §7.1 then fails **open** -- passing
because there is nothing left to check. End-of-pipeline verification cannot
catch this, because by then the evidence is already gone. The validator
catches it at the boundary, where it happens.

A tool result that fails validation is dropped and recorded, not passed on.
A round whose results are entirely dropped is reported to the agent as a
failed step, so the next round can plan around it.

---

## 6. Analyst — structured claims, not prose

A trap worth naming: if the Analyst emits prose and the Verifier reads that
prose, the Verifier must re-extract claims from text and re-judge them with
an LLM. That is an LLM checking an LLM — expensive, non-deterministic, and
it fails quietly.

**The Analyst emits structured claims, each already carrying the Evidence id
it came from.** `schemas/answer.py` already pushes this way: the UI renders
fields, not free prose (`design/UX_FLOWS.md`).

This makes the groundedness half of verification a lookup rather than a
judgment.

---

## 6.1 Evidence must carry what the source panel renders

`design/UX_FLOWS.md` defines the contract: an inline `[1]` opens a **Source
details** panel showing court, case name, citation, the relevant paragraph
extract, why it matters, and Open / Save actions.

`retrieval/evidence_builder.py:to_evidence` does not supply that today:

```python
Evidence(
    content=doc.full_text,      # the WHOLE document, not the matched passage
    document_id=..., title=..., document_type=...,
    provenance=doc.provenance,  # url is present and real
)                               # no court, no citation, no location
```

| Panel field | Today |
|---|---|
| Open / PDF link | present — `provenance.source.url`, real S3 URLs verified in Phase 2 |
| Case name | present — `title` |
| Court | **missing** — stored in `documents`, never placed on Evidence |
| Citation | **missing** — same |
| Paragraph extract | **missing** — `content` is full text, `location` never populated |
| Why it matters | not an Evidence field; the Analyst produces it per claim |

**The passage problem is the same defect as §5.2.** `vector.best_passages`
already locates the matched chunk for reranking and then discards it —
`build_evidence` re-fetches full text by id. So the panel cannot show an
extract, *and* compression receives a 40,000-character judgment instead of
the passage that actually matched.

### Progressive disclosure — small by default, expand on demand

The fix is not to enrich every result. It is to return **little by default**
and let the caller ask for more. Two of the three tiers already exist:

| Tier | Returns | Who asks | Status |
|---|---|---|---|
| 1 | matched passage + `Location` + court + citation | every search | **6.6** — stop discarding what `best_passages` found |
| 2 | full document text | agent calls `get_section` / `get_judgment` | already built, Phase 2, unchanged |
| 3 | the source PDF | user clicks *Open* in the panel | already built — `provenance.source.url` |

The agent expanding a passage is the same action as a user clicking "show
more", and it needs no new tools: `tools/statutes.py:get_section` and
`tools/judgments.py:get_judgment` already return whole documents by id.

This fixes compression by construction. An agent holding four search results
holds four passages, not four whole judgments — so §5.2's compression step
has far less to discard, and far less opportunity to drop provenance while
discarding it.

Scope of 6.6 is therefore narrow: carry the matched passage and its
`Location` through fan-in, and add `court` and `citation` to `Evidence`.
Nothing else changes.

### 6.2 Dynamic fetches already persist correctly

No work needed, recorded so it is not re-litigated.
`tools/judgments.py:search_judgments` defaults to `store=True`, and
`ingestion/judgments/store.py:store_judgment` upserts, embeds, **chunks**,
and writes CITES / CITES_SECTION / DECIDED_BY — gated on
`verification_gate.py` passing. A judgment fetched live today is a
first-class corpus member afterwards; the corpus grows by being used.

This is not a layer violation under `PROJECT_STRUCTURE.md` §9. That rule
guards against *inferred* knowledge — feedback, guessed relationships —
becoming authoritative. A real judgment retrieved from an official source is
`source_type="primary"`. Fetching is not inferring.

---

## 7. Verification

Three checks, in increasing cost order. The cheap deterministic ones run
first and can fail the answer without ever invoking a model.

### 7.1 Groundedness — deterministic

No LLM. For every claim:

- does it carry an Evidence id?
- does that document exist in the store?
- if a paragraph is cited, does that paragraph exist?

Cannot itself hallucinate, which is precisely why it goes first.

`../agents` proves the pattern works: its `final_report_generation`
cross-checks every cited URL against the actual research findings before the
report ships. Ours is stricter — it checks against the store, not just
against notes.

### 7.2 Legal correctness

Partly graph queries, partly LLM: is the section still in force, is the
judgment overruled, does the jurisdiction match, are there conflicting
authorities.

### 7.3 Coverage — the "AI missed something" check

Phase 6 onward: query the active layer for authorities that mattered in
similar threads and were not retrieved here.

**Until Phase 6 exists**, the same slot runs a deterministic stand-in: if the
answer cites a Section, does its parent Act contain closely-related sections
that were never retrieved? A graph query against edges that already exist,
no LLM, works today.

### 7.4 When the loop is exhausted

Hard cap of 2 re-research passes. On exhaustion with claims still
unsupported: **answer, with the unsupported claims explicitly flagged** in
the "what needs verification" field the UX already defines. Not a silent
drop — a user cannot distinguish a short answer from an incomplete one.

---

## 8. Model configuration

**Gemini**, via `langchain-google-genai`. `GEMINI_API_KEY` is already
present in `.env`; the free Flash tier suits a loop that makes many calls
per question.

Model choice lives in `config/` behind a single accessor, following
`open_deep_research`'s `configuration.py` convention, so the supervisor model
and the drafting model can diverge later without touching node code.

### 8.1 Retry policy — 503 and 429 are not the same failure

Measured on 2026-08-20 against the live free tier:

| Condition | Meaning | Correct response |
|---|---|---|
| `503 UNAVAILABLE` | transient overload; frequent | retry with backoff |
| `429 RESOURCE_EXHAUSTED` | daily free-tier cap | **fail fast, never retry** |
| `404 NOT_FOUND` | model retired | fall back to a working model |

Working models are `gemini-flash-latest` and `gemini-3.5-flash`.
`gemini-2.0-flash` and `gemini-2.5-flash` both return 404 -- no longer
available.

**Retrying a 429 the way a 503 is retried destroys the day's budget.** This
was learned the hard way: a probe that caught the exception type without
reading its message treated quota exhaustion as transient overload and
retried it ten times per question. Distinguishing the two is a requirement
on the client wrapper, not a runtime discovery.

This compounds with fan-out. Three angles at eight plan steps is already
~24 tool executions per question; the plan-then-execute design in §5.2 keeps
*model* calls to two per angle per round, which is what makes the free tier
viable at all.

**Rate-limit fallback is required, not optional.** Fan-out multiplies calls,
and the free tier will throttle. `../agents` handles this with a
`fallback_model` in `configuration.py` that every model call falls back to
when the primary is rate-limited; adopt the same pattern.

---

## 8.2 Measured: query rewriting is the largest lever found so far

Run 2026-08-21 on the 6.1 benchmark, 50 questions, full corpus. One model
call rewrites the user's grievance into statutory vocabulary, then the
existing Phase 2 pipeline searches that instead.

| configuration | MRR | recall@1 | recall@5 | recall@10 |
|---|---|---|---|---|
| plain | 0.467 | 32% | 64% | 78% |
| plain + rewrite, fused by RRF | 0.584 | 44% | 82% | 88% |
| **rewrite only** | **0.670** | **56%** | **86%** | **90%** |

**One model call is worth more than the entire reranking mechanism**
(+0.20 MRR against reranking's +0.12). It closes the vocabulary gap Phase 2
diagnosed and could not fix: *"builder failed to give possession"* becomes
*"promoter failure to give possession return of amount"*, and RERA s.18
moves from rank 3 to rank 1.

**Fusing the original with the rewrite was tried and is worse.** The
hypothesis was that rewriting rescues failed searches while damaging good
ones -- 6 of the 8 regressions were already at rank 1-2 -- so keeping both
signals should preserve the wins. It does not: the original query's weaker
results drag the fused ranking down. The rewrite is not a second opinion to
blend, it is simply a better query. Recorded because the hypothesis was
reasonable and the measurement refuted it.

### Where rewriting lives: the planner, not retrieval

The gain shows up in retrieval, so the tempting move is to put the rewrite
inside `hybrid_search`. It does not belong there.

Rewriting is ambiguity resolution -- deciding what a person actually means in
legal terms. That is the LLM's job. `hybrid_search` is a **tool**, and tools
stay deterministic. A model call inside it would mean every search costs
quota and roughly a second of latency including searches that need neither,
retrieval would stop being unit-testable without an API key, and once the
planner also rewrites there would be two places doing it.

**Phase 2 is therefore unchanged.** The finding lands as a requirement on the
planner prompt in §5.2 -- emit queries in statutory vocabulary, not the
user's -- which de-risks 7.1 rather than adding work to it.

### The bar 7.1 must clear

**MRR 0.670 / recall@5 86%**, not the 0.467 plain-retrieval baseline. A full
plan-execute-validate loop that cannot beat a single rewrite call is not
worth its cost, and the honest response would be to ship the rewrite alone.

---

## 8.3 Measured: the research agent does not beat a single rewrite call

Run 2026-08-21, milestone 7.1, same 50-question benchmark.

| configuration | MRR | recall@1 | recall@5 | recall@10 |
|---|---|---|---|---|
| plain retrieval | 0.467 | 32% | 64% | 78% |
| **single rewrite call** | **0.670** | **56%** | **86%** | **90%** |
| agent -- concatenate, no rerank | 0.338 | 24% | 46% | 58% |
| agent -- rerank, search limit 15 | 0.376 | 32% | 48% | 52% |
| agent -- rerank, search limit 40 | 0.366 | 32% | 44% | 48% |

Three configurations, all below plain retrieval and far below the bar.
Tuning stopped there deliberately: continuing would be fitting to the
benchmark rather than learning from it.

**Why it loses.** The planner's queries are good -- *"promoter failure to
give possession return of amount interest"* is better than the rewrite
prompt produces. The loss is structural. `hybrid_search` already fuses three
signals and reranks ~50 candidates, then truncates to `limit`. The agent
issues two or three such searches, receives already-truncated slices, unions
them, and reranks again. A union of good queries is noisier than one good
query through a tuned pipeline, and the second ranking runs over a pool most
of whose candidates were already discarded.

**The more important limitation is the benchmark, not the agent.** All 50
questions have exactly one correct answer in one Act. This is a
**single-provision lookup** benchmark. The agent exists for *multi-angle*
research -- decomposing "builder delayed possession" into the RERA remedy,
the consumer forum and limitation. **No question in the set has more than
one angle, so the benchmark structurally cannot show the agent's value.**

The fair reading is therefore not "the agent is bad" but:

- on single-provision lookup, rewriting wins decisively and should ship
- on multi-angle research, the agent is **unproven**, because nothing has
  tested it

### Consequences

1. **Ship the rewrite.** It is the largest measured gain in the project and
   does not depend on the agent.
2. **Do not build 7.2 (supervisor fan-out) on this evidence.** Fan-out
   decomposes into angles; a benchmark with no multi-angle questions cannot
   tell whether decomposition helps. Building it would be building blind --
   the failure mode this project has rejected since Phase 2.
3. **A multi-angle dataset is the prerequisite for 7.2.** Questions whose
   correct answer is a *set* of provisions across different Acts, scored on
   whether all of them were found. That is a different evaluator from
   `first_relevant_rank` and is new work, not a tweak.

---

## 9. Harness — built before the agents

Built first, not last. Without it, every agent change is guesswork — the
failure mode explicitly rejected in Phase 2.

```text
evals/
├── datasets/
│   ├── retrieval/       question -> which authorities should be retrieved
│   ├── citation/        answer -> are all citations real and correct?
│   └── hallucination/   questions with no good answer — must decline
├── evaluators/
│   ├── groundedness.py       is every claim supported by cited evidence?
│   ├── citation_accuracy.py
│   ├── retrieval_recall.py
│   └── structure.py          does the answer match the DraftAnswer contract?
└── run.py
```

The Phase 2 benchmark (n=15) seeds `retrieval/` but is far too small to
judge an agent; expanding the question set is part of the harness milestone,
not an afterthought.

`hallucination/` is the most important dataset in the project: questions the
corpus genuinely cannot answer, where the correct behaviour is to decline.

---

## 10. File structure

Follows `PROJECT_STRUCTURE.md` §1–§6 and `langchain-ai/open_deep_research`
conventions: `src/` layout, root `langgraph.json`, per-module `state.py` /
`configuration.py` / `prompts.py`.

New in this phase:

```text
langgraph.json                    graph entrypoints, python version, env

src/legal_ai/
├── config/                       model + runtime configuration
├── context/
│   ├── models.py                 ThreadContext, QueryContext, CaseContext,
│   │                             DocumentRef, EstablishedFinding
│   ├── builder.py                build_thread_context(...)
│   ├── revisions.py              versioning; new revision per promotion
│   ├── invalidation.py           which cached findings die on a field change
│   └── serialization.py          compact prompt rendering
├── graph/
│   ├── state.py                  ResearchState — the graph channel
│   ├── build.py                  assemble & compile the StateGraph
│   ├── edges.py                  conditional routing incl. the verify loop
│   ├── checkpoint.py             persistence across restarts
│   ├── configuration.py          caps (§5.3), models, fallback model
│   ├── nodes/                    document, context_builder, supervisor,
│   │                             analyst, verification, draft
│   └── subgraphs/
│       └── researcher.py         one angle: search loop -> compress,
│                                 invoked N-way in parallel
├── agents/
│   ├── base.py                   cannot construct an agent without a
│   │                             ThreadContext — §6 enforced in code
│   ├── supervisor.py             decompose, fan out, reflect
│   ├── research.py               one angle; plan -> execute -> compress
│   ├── planner.py                plan schema; the orchestrator executes it
│   └── validator.py              deterministic gate at the tool boundary
│   └── prompts/                  system/ (one .md per agent), fragments/,
│                                 registry.py (hash prompts for traces)
└── schemas/
    ├── research.py               ResearchRequest, ResearchFinding, Claim
    └── answer.py                 DraftAnswer — the UI contract
```

Prompts are reviewable Markdown, not inline strings. `registry.py` hashes
them so a trace records which prompt version produced a result; without
that, an eval regression is untraceable.

---

## 11. Milestones

| # | Deliverable | Verified by |
|---|---|---|
| 6.1 | Harness: `evals/` datasets + evaluators, 50 questions | **done** -- baseline MRR 0.467; with LLM rewrite 0.670 |
| 6.2 | `ThreadContext` + `case_id` + filters | **done** -- 17 tests |
| 6.3 | Graph skeleton, caps, `langgraph.json` | **done** -- 11 tests; compiles and runs end to end |
| 6.4 | **Document Agent**: extract parties, dates, clauses, cited sections, issues into the context | a large upload yields structure, never raw text, into `ThreadContext`; the researcher never sees the document body |
| 6.5 | Clarification gate | a question missing a state asks; a complete one does not |
| 6.6 | Tier-1 `Evidence`: matched passage + `Location` + court + citation | the source panel renders every field `UX_FLOWS.md` specifies |
| 7.1 | Researcher subgraph: plan-then-execute, validator gate, compress | a canned plan executes with no model call; invalid results are dropped; **must beat MRR 0.670** |
| 7.2 | Supervisor: `ConductResearch` fan-out, reflect loop, overflow | a one-angle question spawns 1 agent; caps hold under an over-broad question |
| 8 | Verification: groundedness + coverage stand-in + bounded re-research | ungrounded claims caught; loop terminates; exhaustion flags rather than drops |

Milestone numbering is project-wide: Phase 1 ran 0--3, Phase 2 ran 4--5,
Phase 3 begins at 6.

7.1 and 7.2 are build order, not competing designs. There is no split-versus-
single mode: the Supervisor holds one `ConductResearch` tool, and how many
times it calls it in a turn *is* the answer. Calling it once **is** the
single-agent case, and per §5.3 that is the expected common case. 7.1 builds
the thing that gets called; 7.2 builds the caller.

What the harness watches here is therefore a **cost** regression, not a
quality one: agents-spawned-per-question, with simple questions expected to
stay at 1.

Analyst and Draft stay pass-throughs with real schemas until Phase 5.

---

## 12. Explicitly not in this phase

```text
Document clause analysis        -> Phase 4  (extraction into context is 6.4)
Contradiction detection         -> Phase 4
Documents screen                -> Phase 4
                                   separate agent by design: it spends its
                                   own window on a large file and returns
                                   STRUCTURE into ThreadContext, never raw
                                   text — the §5.2 isolation pattern applied
                                   to one big document instead of many
                                   results. PHASE_4 §1: Document Agent ->
                                   Research Agent.
                                   Known gap: CHUNKABLE_TYPES is
                                   ("section","judgment"); uploaded
                                   petitions will not chunk until Phase 4
                                   adds their type.
Analyst / Draft internals       -> Phase 5  (nodes exist, bodies are stubs)
Active knowledge write side     -> Phase 6
Active-layer coverage data      -> Phase 6  (stand-in ships here)
GraphRAG / precedent graph      -> Phase 7
Three graphs (document, case)   -> Phase 4-5; only the research graph now
Nested sub-sub-agents           -> not planned; one fan-out level only
```

---

## 13. Known risks

- **The benchmark is n=15.** Directional, not precise. Expanding it is
  milestone 6.1 work and gates every later measurement.
- **The corpus is young.** Judgment coverage is thin, so a research agent may
  legitimately fail to find authority that exists in the real world. The
  harness must distinguish "the agent searched badly" from "the corpus lacks
  it", or every eval result is ambiguous.
- **Free-tier rate limits.** A bounded loop still makes many calls per
  question; the caps in §5 are as much a rate-limit defence as a cost one.
- **Compression can silently break verification.** If a sub-agent's summary
  drops Evidence ids, every downstream claim becomes ungroundable and §7.1
  fails open rather than closed. This needs a test of its own, not just an
  eval.
- **Passage plumbing touches the fan-in path.** `best_passages` and
  `build_evidence` are Phase 2 code with passing tests; widening `Evidence`
  must not change existing retrieval behaviour. Phase 2's suite is the
  regression gate.
- **Fan-out may not pay for itself yet.** On a young corpus, four angles may
  retrieve the same handful of documents four times. Milestone 7.2 exists to
  measure this rather than assume it.
- **The clarification gate can become a nag.** Asking on non-blocking gaps
  makes the product tiresome and trains users to ignore it. The blocking list
  in §4.1 stays short and enumerated, never "ask if unsure".
- **Coverage stand-in is weak.** Same-Act sibling sections is a crude proxy
  for "what was missed" and will produce false prompts. It is a placeholder
  for Phase 6, and should be judged as one.

---

## 14. Reference implementation

`../agents` — the user's fork of `langchain-ai/open_deep_research`, adapted
for the PACE Uttarakhand hackathon. Patterns adopted here:

| Pattern | Where it lives there |
|---|---|
| Supervisor with `ConductResearch` fan-out + `asyncio.gather` | `src/agents/research/deep_researcher.py` |
| Overflow beyond the cap returns an explanatory `ToolMessage` | same, ~line 473 |
| `decompose_subtopics` forcing breadth before the loop | same, ~line 281 |
| `compress_research` per sub-agent | same, ~line 668 |
| Caps as configuration, enforced in code | `src/agents/research/configuration.py` |
| `fallback_model` for free-tier rate limits | same |
| Citation cross-check before the report ships | `final_report_generation` |

Not adopted: Tavily and open-web search (we have a curated corpus and the
Phase 2 tools), and the outreach graph. Their `allow_clarification` default
of skipping the gate is inverted here, for the reason in §4.1.

**NyayAssist** (<https://nyayassist.ai/>) — an Indian legal workspace:
case management, citation-backed research over Indian acts and judgments,
drafting, storage, translation, meeting transcription, calendar, WhatsApp
bot; ISO 27001 / SOC2 / DPDPA. Most of that is product surface with no
bearing on orchestration.

The one architectural point taken from it: **the case, not the thread, is
where work accumulates** — their pitch is that users build on previous work.
That reinforces `UX_FLOWS.md` and is why §4.2 lands in this phase rather than
Phase 4.
