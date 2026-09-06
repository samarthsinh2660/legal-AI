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
drafting card have been driven in a browser and a client demo ran against
the deployed app. Still unverified by eye: the provenance badges, the four
evidence blocks, the graph's hover-dim and drag, the confirm dialogs, and
every focus state.

Those are verified by test and by API and by nothing else. The run-stream
rewrite (2026-09-05) is in the same position on the browser side: the
component is covered by tests against a real SSE stream, and the whole
path was driven live through the API, but nobody has watched the reopened
thread reattach on a screen.

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

- **Cancellation.** A reader who has gone still spends the full model
  budget. Python cannot interrupt the blocking call, but a worker can
  decline to start the next node. The seam already exists: the worker
  checks between nodes for a run that has been deleted, and a cancel flag
  is the same check reading a different column. Phase 4, alongside the
  checkpoint that seam also carries.
- **A worker killed mid-run leaves its row saying "running".** The graceful
  path is covered -- SIGTERM drains, verified live 2026-09-05 -- but a
  `kill -9` or a lost machine strands the row, and the thread waits on an
  answer that is not coming. The reaper in Phase 4 is what closes it:
  `heartbeat_at`, swept.
- **The images still carry torch, though nothing running uses it.** The
  models now live in two TEI containers and a worker is 148 MB resident,
  but `sentence-transformers` stays a dependency because unsetting
  `LEGAL_AI_EMBED_URL` must still work -- that is the local path the tests
  and a laptop use. Dropping it from the service images would take ~1 GB
  off each and make the model servers mandatory. Worth doing; it is a
  decision about whether the in-process path is still supported, not a
  refactor.
- **One worker is the honest number, and the model key is why.** Three
  workers took 62 rate-limited responses between them in 45 minutes of QA,
  because they share one free-tier key. The queue scales; the quota does
  not. Raise the key before the worker count -- and when you do, add
  threads to one worker before adding containers: a warm worker is 1.17 GB
  resident, almost all of it models that threads share and processes do
  not.
- **A warm turn is 18-40s, and the biggest single piece is the CPU
  reranker, not a model call.** Measured: retrieval 43% of the turn, and
  97% of retrieval is one cross-encoder, run twice (once per phrasing).
  On this machine's GPU the same model over the same shortlist takes 0.61s
  instead of 5.12s, with an identical ranking -- so it is the one speed
  lever that costs no accuracy. Now that the reranker is its own container,
  it needs `nvidia-container-toolkit` on the host (not installed) and the
  CUDA TEI tag with a device reservation -- one GPU for every worker rather
  than one each.
  The rest is ~7s planning and ~7s analysing on a free-tier key.
  `HF_HUB_OFFLINE=1` would cut the worker's 26s startup to 6s, but it fails
  outright on an empty model cache, which is a bad default for a first
  deploy.
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
