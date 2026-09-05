# What is not built yet

Ordered by how much each would change the product. Everything here is
decided but unstarted; anything still being argued about says so.

---

## 1. The research-run ledger — designed and approved, not started

**Why.** Three layers answer three different questions, and only two exist:

    audit_events        who accessed or changed something
    messages.answer     what the system finally said, and on what evidence
    research_runs       HOW it got there            <- missing

A lawyer's question is the third one. *"Why did you use these three
judgments? Did you consider anything else?"* Today that is unanswerable:
the runtime computes the plan, the discarded evidence and each verdict's
reasoning, and throws all of it away.

**This adds no agent and changes no chat flow.** The information already
exists at runtime; the ledger preserves it instead of dropping it.

    plan_research()  -> Angle(angle, query)             discarded after searching
    ResearchResult   -> .evidence and .dropped          .dropped carries reasons
    ClaimVerdict     -> (claim, verdict, reason, stage) only the bucket survives

### Schema

A parent with structured children, deliberately not one JSON blob -- the
questions worth asking are relational:

    research_runs
      id, user_id, case_id, message_id
      original_question, resolved_question
      mode, status, error
      started_at, completed_at, duration_ms, model

    research_run_plans          run_id, angle, subquestion, queries
    research_run_evidence       run_id, evidence_id, query, rank,
                                retrieved, selected, discard_reason,
                                source (corpus | discovery)
    research_run_verifications  run_id, claim_id, stage, reason, verdict

    messages.research_run_id

`source` on the evidence row is not in the original sketch and is worth
keeping: `_discover` fetches from Indian Kanoon at a different provenance
tier than corpus retrieval, and "did retrieval fail or did the model choose
wrong" stays answerable only if the two are distinguishable.

### Decisions

- **Write point.** The controller `INSERT`s the run *before* the graph
  starts, then `UPDATE`s it with the children on completion, or with
  `status=failed, error=...` on the way out. Graph nodes stay pure -- no DB
  writes inside them. Persisting only after a successful return would lose
  the ledger exactly when something crashed, which is when it is most
  wanted.
- **Volume.** Store every retrieved and discarded row. Roughly 30-50 per
  question, so ~50k per thousand questions. No retention policy in this
  change; measure first.
- **Privilege.** This holds the resolved question and every retrieved
  passage, so it is client matter data -- unlike `audit_events`, which
  deliberately holds none. Same `user_id` scoping and the same deletion
  cascade as a case.
- **No agent tool yet.** `get_research_run(run_id)` would let the AI answer
  "why did you choose this judgment?" in conversation. Build the ledger
  correctly first.

### Scope

Backend: schema, capture through the controller, `messages.research_run_id`,
`GET /research-runs/{id}`.

Frontend: a **View research details** affordance under an answer, opening
the chain -- question, angles planned, queries run, evidence retrieved,
evidence rejected *with its reason*, each claim's verdict and why. A ledger
nobody can open cannot be checked, which is most of its value.

### Tests to write first

- a run is created even when the research execution fails
- a failed run still records whatever plan it got to before dying
- a run links to exactly one message
- discarded evidence retains its reason, and `retrieved` is distinguishable
  from `selected`
- a verification `reason` and `stage` survive the round trip through
  Postgres -- the four buckets already persist, these are the new part and
  the ones a reader actually reads
- user and case isolation
- deleting a case removes its research-run rows

---

## 2. Most of the UI has still never been looked at

Partly closed. The dashboard, a research thread, the composer and the
drafting card have now been driven in a browser and a client demo ran
against the deployed app. Still unverified by eye: the provenance badges,
the four evidence blocks, the graph's hover-dim and drag, the confirm
dialogs, and every focus state.

Those are verified by test and by API and by nothing else.

---

## 2b. Citation edges do not reach the newly ingested codes

Measured 2026-09-03:

    NI Act   207 judgments cite its sections
    IPC        0
    BNS        0

`CITES_SECTION` edges are written when a judgment is ingested, matching
against the Acts held at that moment. The IPC, CrPC and Evidence Act
arrived afterwards, and the BNS was never linked either -- so a judgment
about murder has no edge to IPC s.302 or BNS s.103, and the graph's statute
views for those Acts draw unconnected nodes.

Of 36,887 sections in the graph, **2,295** are cited by a judgment we hold.
The graph screen now reports the slice total and says why a slice may draw
no edges, rather than showing loose dots.

`scripts/rebuild_citation_edges.py` does **not** fix this -- it recomputes
judgment-to-judgment `CITES` only, and says so. The fix is a new pass doing
for `CITES_SECTION` what that script does for `CITES`: re-extract section
references from all 13,130 stored judgments against the current Act list.
Nothing else depends on it: retrieval does not use these edges, and
`find_act_by_name` already resolves the new codes for future ingests.

## 3. Corpus gaps

**State-made rules.** None held -- the corpus is central legislation only.
This is why the system cannot give a homebuyer the prescribed interest
rate: RERA's parent Act gives the framework, and each state's rules give
the number. `retrieval/coverage.py` now says so rather than answering as if
it knew.

**Most High Court decisions.** ~13k judgments, overwhelmingly Supreme Court.

**Evidence Act s.65B ranks 12th**, below its own s.65A and its BSA
counterpart. Retrievable but poorly ranked -- flagged during ingestion, not
tuned.

---

## 4. Smaller, known

- **Live progress after a reconnect.** A reopened tab gets the answer but
  not the steps. The answer is safe and the thread now says "Still
  researching" rather than claiming the run failed; what is missing is the
  progress itself, because the event queue is created per HTTP connection,
  holds no history and is addressable by nothing.

  Phase 1 of `docs/RELIABILITY_ARCHITECTURE.md` is the fix: `run_events`
  with a sequence number, replayed on `Last-Event-ID`. Shared storage, not
  an in-process registry -- a registry finds nothing when the reconnect
  lands on the other worker.

- **Cancellation, and surviving a deploy.** A disconnect no longer loses
  the answer, but nothing stops the run either -- a reader who has gone
  still spends the full model budget, and an in-memory task dies with the
  process on every rebuild. Both are Phase 2 of
  `docs/RELIABILITY_ARCHITECTURE.md`; Python cannot interrupt the blocking
  call, but a worker can decline to start the next step.
- **No landing page.** An unauthenticated visitor gets the login screen
  with no explanation of what the product is.
- **Account recovery.** No password change, reset or email verification. A
  forgotten password needs a DBA.
- **Open registration.** Anyone reachable can create an account and spend
  model budget.
- **28 Acts still on the dead India Code host** (648 sections). Their
  titles do not match the new site exactly and were deliberately not
  fuzzy-matched -- our *Tribunals Reforms Act, 2021* sits beside the site's
  *2026*, a different Act.
- **`cheque bounce` still misses s.138.** "Bounce" appears nowhere in the
  Act and no rewrite recovered it.

---

## Running now

`scripts/reembed_titles.py --judgments` -- embedding each judgment chunk
with its case name, as sections already are. 363,854 chunks at ~25/s.
Resumable; an interruption costs nothing.
