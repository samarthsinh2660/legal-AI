# Phase 4 --- Document + Case Intelligence

## Objective

> Can AI understand *this user's* case, not just Indian law in general?

Phases 1--3 make the system able to research Indian law. Phase 4 introduces
the user's own material -- uploaded documents and the persistent case that
holds them -- as a second kind of evidence alongside research.

------------------------------------------------------------------------

## 1. Architecture

``` text
                  Case
                   |
             Document Agent
                   |
       Facts / Parties / Dates /
       Issues / Claims / Evidence
                   |
             Research Agent        (Phase 3)
                   |
              Case Agent
```

------------------------------------------------------------------------

## 2. Document Agent

Understands uploaded legal documents:

``` text
PDF / DOCX
    |
    v
Document Agent
    |
    +--> Parties
    +--> Facts
    +--> Dates
    +--> Clauses
    +--> Sections
    +--> Claims
    +--> Issues
    +--> Contradictions
```

Handles:

- petitions
- notices
- agreements
- judgments
- orders

Its output becomes evidence for the Analyst Agent (Phase 5).

------------------------------------------------------------------------

## 3. Case Agent

Operates at the case level, combining documents, research, and legal
knowledge:

``` text
Documents
   +
Research
   +
Legal Knowledge
   |
   v
Case Agent
   |
   +--> Timeline
   +--> Facts
   +--> Issues
   +--> Arguments
   +--> Applicable law
   +--> Precedents
   +--> Missing facts
```

The Case Agent is therefore different from the Document Agent:

> Document Agent = understands documents.

> Case Agent = understands the legal case using documents + research.

### A case is a container, not a question

A **research session** (Phase 3) answers one question. A **case** is a
persistent workspace that accumulates everything about one real legal
matter:

``` text
CASE
 |
 +-- Case details (number, court, jurisdiction)
 +-- Parties
 +-- Documents
 +-- Timeline
 +-- Issues
 +-- Research sessions        <-- many
 +-- Authorities
 +-- Arguments
 +-- Notes
```

One case therefore contains **many** research sessions:

``` text
Case: Patel v. Shah
       |
       +-- Research: "Can adverse possession apply?"
       +-- Research: "What proves ownership?"
       +-- Research: "Relevant Gujarat HC judgments"
       +-- Research: "Limitation period"
```

A research session may exist with no case at all. When it is attached to
one, its thread context (`AI_PROJECT_PROPOSAL.md` §6) is seeded from the
case -- parties, established facts, prior findings -- which is exactly what
lets the Case Agent answer questions the Research Agent cannot:

``` text
"Based on the documents in this case and the authorities we have
 researched, what are the key legal issues?"

"Which facts in our documents support the ownership claim?"

"Which cases are most relevant to our facts?"
```

Two entry points must both be supported:

``` text
Flow A                          Flow B
------                          ------
New research                    Create case
   |                               |
Ask question                    Enter case information
   |                               |
Get answer                      Upload documents
   |                               |
Save to case                    Case workspace
   |                               |
Choose existing / create new    Start research
```

------------------------------------------------------------------------

## 4. Milestones

### Milestone 9

Document Agent.

### Milestone 10

Case Agent.

------------------------------------------------------------------------

## 5. Deliverable

> AI understands both Indian law AND the user's particular case.

------------------------------------------------------------------------

## 6. Explicitly not in this phase

``` text
Analyst Agent / Draft Agent    -> Phase 5
Verification Agent             -> Phase 6
Active knowledge promotion     -> Phase 6
GraphRAG / precedent graph     -> Phase 7
```

------------------------------------------------------------------------

## 7. What was built (2026-08-24)

### Milestone 9 --- Document Agent

Landed in Phase 3 as milestone 6.4, because `ThreadContext` is defined to
hold case facts and something had to produce them. Phase 4 completed the
wiring: the `document` graph node no longer passes through, it reads each
`document_id` from the canonical store and extracts structure. Facts
already on the channel are used as given, which is the path a caller who
has pre-extracted takes and what keeps the graph runnable without an API
key.

### Milestone 10 --- Case Agent

``` text
legal_ai/case/models.py      Case, CaseAnalysis, TimelineEntry
legal_ai/case/store.py       cases, case_documents, case_findings,
                             case_sessions -- the only writer
legal_ai/case/timeline.py    date parsing, deterministic
legal_ai/case/session.py     Flow A and Flow B
legal_ai/agents/case.py      the agent
```

Split the same way every other agent here is:

| output | how |
|---|---|
| timeline | deterministic. A model that invents a date loses a limitation point |
| facts | assembled from `DocumentFacts`, each traced to a document id |
| applicable law / precedents | Evidence ids copied, never generated |
| issues, missing facts | one model call, both together |

Issues and missing facts share a call because both need the documents and
the law weighed at once -- the same merge `plan_research` made in Phase 3
when four calls became one.

`missing_facts` is the output with no counterpart in a research session.
Twelve years' possession required, eight evidenced: that gap is only
visible holding the legal test and the document facts together. Searching
public law cannot find what is absent from a private file.

### Why the Case Agent is not a node in the research graph

The graph runs per question. A case outlives every question in it, and its
analysis is a derived view the case workspace requests -- not something to
recompute on every research run. The graph consumes a case (seeding its
context from what the case established); it does not contain one.

### Dates are observation times, not legal dates

`TimelineEntry.parsed` is None whenever a date could not be read, and the
entry is kept anyway. "Within 30 days" is a real event with no resolvable
date, and dropping it would show a confident timeline with holes in it.

Numeric dates are read **day-first** and month-first is not accepted at
all. Indian legal documents are day-first throughout; allowing both would
make every ambiguous date a coin toss, and 03/04/2021 read as 4 March
moves a limitation date by a month.

------------------------------------------------------------------------

## 8. Fixed on the way in

Three defects found while sizing this phase, all pre-existing:

**`.env` was never loaded.** `python-dotenv` was a declared dependency
that nothing called. `llm/client.py` reads `os.environ` directly, so
without exporting the key by hand every model call raised, `plan_research`
returned its fallback, and the agent silently became plain retrieval --
no error, just a worse score. Any benchmark run before this date may have
had no model behind it. Now loaded once in `legal_ai/__init__.py`, with
`override=False` so a deliberately exported variable still wins.

**Statute text was destroyed on re-ingestion.** `documents` was
overwrite-in-place, so an amendment lost the text it replaced. Added
`document_versions`: the old row is archived before being overwritten, and
`get_text_as_on` returns the wording on record at a past date -- which is
what governs, since the law that applies is the law as it stood when the
cause of action arose.

Two limits worth stating. The timestamps are **observation times**, not
commencement dates -- India Code does not give us one, so a version
brackets a change to within our polling interval and claims nothing more.
And nothing re-runs ingestion on a schedule yet, so the mechanism is
correct but dormant until a periodic re-scrape exists.

**`_check_db` pulled the whole judgment corpus to compare titles.** It
selected every judgment id and re-read each row in full, including
`full_text`. Invisible at nine stored judgments, impossible at fifty
thousand. Now computed in SQL.

------------------------------------------------------------------------

## 9. Not built, and why

**Case-law discovery by issue.** Asked "which Supreme Court cases concern
drugs", nothing here answers. Measured facts behind that:

- The Vanga archive index is metadata only -- `court`, `year`, `judge`,
  `party`, `citation`, `cnr`. No subject, no headnote, `description`
  empty. The word "drugs" appears nowhere in it, so topical search against
  the archive is impossible rather than slow.
- The lazy fetch path was built for lookup by name or citation, and its
  docstring says so. It therefore only ever caches cases someone already
  named, converging on "the cases our users already knew about".
- `CITES_SECTION` has 24 edges from 9 stored judgments, so
  section -> cases returns nothing today.

The design agreed for it, not yet implemented: retrieve the sections
first, then find cases against **both** the section and the rewritten
query, fused. Measured on "bail in drug cases", the two signals barely
overlap -- the rewrite returned Tofan Singh and Noor Aga, the section
query returned Kerala v Rajesh and Rattan Mallik -- so neither replaces
the other. The section's distinct contribution is that it is grounded in a
provision that exists and gives a graph key, so what is fetched caches as
`CITES_SECTION` edges and answers locally next time.

**Bulk Supreme Court ingest.** Sized, not run: 12,993 judgments 2010-2026,
~2.5 hours, ~3.4 GB cache. It is an accelerator for the `CITES_SECTION`
cold start, not a prerequisite -- and it can never cover the High Courts,
where Delhi alone filed 8,465 in 2023.

**Indian Kanoon robots blocklist.** `robots.txt` carries 9,292 disallow
rules under `User-Agent: *`, almost all specific `/doc/<id>/` paths --
judgments ordered de-indexed, typically victim-privacy matters.
`_search_indian_kanoon` fetches any doc id it finds and checks none of
them. This must land before any discovery path that fetches more.

**Arguments.** Listed as a Case Agent output in §3, but generating them is
the Analyst and Draft Agents' job in Phase 5. Building a field nothing
writes would be speculative.

------------------------------------------------------------------------

## 10. Upload path, clauses, claims, contradictions (2026-08-24)

### The front door

`PDF / DOCX` is the first box in §2's own diagram and it did not exist.
`extract_document_facts` took *text*; nothing produced text from a file, so
every `DocumentFacts` in the system was hand-built. The case container
worked and the front door did not.

``` text
case/files.py    case_files table; pdf, docx, txt, md -> text
case/upload.py   file -> text -> store -> attach -> DocumentFacts
```

**Uploaded files are deliberately NOT in `documents`.** `hybrid_search`
reads that table, so a client's pleading placed there would come back as
*authority*, and could surface for a different user's query. Keeping
private material out of the corpus table is a stronger guarantee than
remembering to filter at every retrieval path, and there are several. A
test asserts an uploaded file appears in neither `documents` nor
`document_chunks`.

That decision also meant `DocumentType` stayed `act | section | judgment`.
Petitions never enter that table, so nothing had to widen.

Verified on real files: a DOCX whose table content survives (legal
agreements put payment schedules in tables) and a 34,470-character Delhi
High Court PDF.

### Extraction failure is now distinguishable from an empty document

A 503 across the whole model chain returned exactly what a document with no
parties returns -- empty tuples, no error. A case view would have reported
"no parties found" when the truth was "nothing read it". This is the same
class as the `.env` defect in §8: silent degradation that a passing test
suite cannot see.

`DocumentFacts.extraction_failed` is set only when *every* window failed;
one failed window out of six is degraded, not failed, and its siblings'
results are real and kept. The Case Agent renders such a document as
`NOT YET READ (extraction failed)` rather than presenting an empty record
as a read one.

### Clauses and claims

Added to the Document Agent's existing call, no extra cost. A clause is
what the document *says* -- a possession date, a penalty, a notice period.
An issue is what it puts in *dispute*. The clause is usually what decides
the dispute, so blending them lost the operative term. A claim is what a
party asserts, which is the direct input to the Analyst Agent in Phase 5.

### Contradictions belong to the Case Agent, not the Document Agent

The Document Agent reads one file at a time and that isolation is the
reason it exists. A contradiction is *between* files, so it is folded into
`analyse_case` -- still one model call for issues, missing facts and
contradictions together.

Two guards: it runs only when the case holds more than one document, and
the prompt requires naming both conflicting document ids. Rendering
`clauses` and `claims` into the case prompt is what makes the task possible
at all -- most conflict signal is in the terms one document sets against
what another asserts.

### Measured: recall 0.20, control precision 1.00

`evals/run_contradictions.py`, 8 cases -- 5 with planted conflicts, 3
negative controls. Graded on **document ids, not prose**: asking whether
the model's sentence means the same as the label's is itself a judgement
call, and scoring a model with a model gives a number nobody can check.

``` text
planted conflicts   5
detected            1     recall 0.20
false alarms        0
controls clean      3/3   precision 1.00
models used         {'gemini-3.6-flash': 8}     one model, no fallthrough
```

Conservative, not eager -- which is the better failure to have, and the
opposite of what was expected. It did not manufacture conflict from mere
difference.

The four misses share a pattern. It caught the one case where two sentences
directly negate each other in plain language, and missed every case needing
a **value or a date** compared across documents: a registration number
against its denial, a memo received before it was dated, an instalment
accepted after termination, two different rents for one tenancy.

Plausible cause: the prompt's closing instruction that "inventing a
conflict is worse than reporting none" buys the control precision and costs
the recall. **Not acted on.** Eight cases with five planted conflicts move
recall in steps of 0.20, so this dataset cannot detect any change that is
not one-case noise -- exactly the mistake §8a records about the 0.670 MRR
figure. A larger dataset weighted toward date and value conflicts comes
first, then a prompt change measured across several runs.

Issues and missing facts have no eval on purpose. Both would need an expert
label per case, and shipping no number is better than shipping one that
gets believed.

### Recorded: the test suite calls the live API

`test_graph_skeleton` invokes the real graph, so the suite makes real
Gemini calls -- normally ~20 minutes, and 33 during an outage. This was
raised as a defect and deliberately kept: twice in one day a bug was pure
silent degradation (`.env` unloaded, extraction returning empty), and a
stubbed model would have stayed green through both. A suite that passes
while the system is broken is worse than a slow one.

------------------------------------------------------------------------

## 11. Model choice for case analysis (2026-08-24)

Gemma is served by the **same Gemini API on a separate quota pool**.
Demonstrated on one key in the same second:

``` text
gemini-flash-latest    429 RESOURCE_EXHAUSTED
gemma-4-31b-it         OK
gemma-4-26b-a4b-it     OK
```

That alone earns both models a place at the *end* of the default chain: a
Gemini-wide outage stops being a total outage, and nothing changes while
Gemini is healthy.

Then the same contradiction eval, same eight cases:

| model | recall | false alarms | controls clean |
|---|---|---|---|
| gemini-3.6-flash | 0.20 (1/5) | 0 | 3/3 |
| gemma-4-31b-it | **1.00 (5/5)** | 0 | 3/3 |

Gemini flash found only the conflict stated as a plain negation. Gemma
found all four that needed a **date or an amount compared across two
documents** -- a registration number against its denial, a memo received
before it was dated, an instalment accepted after termination, two rents
for one tenancy.

Run twice, once through a patched chain and once through the shipped
wiring, both 1.00 with clean controls. Eight cases is still eight cases,
but 1/5 -> 5/5 with precision holding is not the +/-0.15 noise that §8a
warns about.

`case_model_chain` therefore leads with Gemma, Gemini behind it as
fallback.

**Not applied to research.** `plan_research` drives retrieval, which the
MRR benchmark scores -- not this one. Switching it on the strength of a
contradiction result would be measuring one thing and concluding about
another, which is the specific error §8a exists to record. Whether Gemma
should lead there too is an open question with a benchmark already built
to answer it.

------------------------------------------------------------------------

## 12. Contradiction detection, measured properly (2026-08-24)

The eight-case set moved recall in steps of 0.20 and could not tell a real
change from one-case noise. Grown to **28 cases -- 19 planted conflicts, 9
negative controls** -- weighted at the failure mode Gemini flash showed:
dates and amounts compared across documents.

``` text
planted conflicts   19
detected            18    recall 0.95
false alarms        0
controls clean      9/9   precision 1.00
models used         {gemma-4-31b-it: 28}      one model, no fallthrough
```

Every case added to target the failure mode was caught: a suit instituted
before its cause of action arose, a reply dated before the notice it
answers, a gift deed executed after the donor's death, cheque amount,
interest rate, carpet area, overlapping lease terms. Including the
three-document case, where it identified *which two* of three conflict --
two-document cases can be scored by naming both, so they do not test that.

The controls are the load-bearing half and all nine held, including the
ones written to trip an eager detector: a partial payment against a total,
two amounts for two different things, and a supplementary agreement
expressly varying a possession date. That last matters most -- flagging
ordinary amendments would make the feature noise on every real file.

### Read it as 0.95 +/- 0.05, and as a ceiling

The single miss, `rera-possession-vs-unregistered`, is a case the same
model caught on the eight-case run. Same case, same model, different run:
one flip is 0.05 at this size.

More importantly the dataset is **authored alongside the prompt it scores**.
Cases written by someone who knows what the detector looks for are easier
than reality: real conflicts sit buried in clauses rather than stated in a
line, involve more than two parties, and are often genuinely arguable. This
is an upper bound, not a field result.

### Not measured: whether Gemma should lead research too

Attempted and failed. Runs were given a 20-minute timeout sized by guess
rather than measurement; Gemma runs exceeded it and were killed before
printing, and the retries spent the day's `gemini-3.6-flash` quota that the
comparison needed on the other side.

`evals/run_agent.py --model` and the `chain` argument on `research()` /
`plan_research()` were added for this and are the right tools: without
pinning, a run slides down the fallback chain partway and blends two models
into one score. The comparison itself is still open, and the research chain
stays on Gemini until it is run.

------------------------------------------------------------------------

## 13. Case discovery by issue (2026-08-25)

The gap: asked "give me Supreme Court cases about drugs", the system
returned statute sections. Three causes, all confirmed by reading the code
rather than assuming:

- **Nothing called the tool registry.** `TOOLS`, `get_tool`, `resolve_args`
  had zero callers -- the executor that used them was deleted in the Phase 3
  simplification, leaving `search_judgments` unreachable from any user path.
- **`to_filters` had zero callers.** The context carried "Delhi High Court",
  `MetadataFilters` supported `court=`, and `_search` called
  `hybrid_search(query, limit=limit)` with no filters at all.
- **The archive cannot be searched by issue.** Its index is court, year,
  judge, party, citation, CNR. No subject column, so the word "drugs"
  appears nowhere in it.

### The shape

``` text
question
   |
   +-- wants_case_law(question)        deterministic gate, no model call
   |
   +-- hybrid_search                   statutes, as before
   |      |
   |      +-- section_identifiers      "Section 37 NDPS Act, 1985"
   |
   +-- discover_judgments              full-text, TWO queries fused:
   |        question wording           -> the doctrine
   |        section identifier         -> the provision's own authorities
   |
   +-- store_judgment                  corpus grows, CITES_SECTION fills
```

**Two queries, not one, because they were measured to find different
things.** On "bail in drug cases" the question's wording returned Tofan
Singh and Noor Aga -- NDPS doctrine -- while "Section 37 Narcotic Drugs and
Psychotropic Substances Act" returned Kerala v Rajesh and Rattan Mallik, the
bail authorities actually asked for. Barely any overlap, so neither
replaces the other.

**Section identifiers, never section titles.** An early prototype built the
query from titles and returned *Kesavananda Bharati* for a cheque-bounce
question: "Cognizance of offences" and "Power to direct interim
compensation" say nothing about cheques, and a vague query falls back to
whatever is merely famous. The number and the Act are what a judgment
quotes.

**A court named in the question beats the case file.** A Gujarat matter
routinely turns on a Supreme Court authority, so inheriting the case's High
Court and searching only there would hide the binding precedent.

**The gate is deterministic and deliberately narrow.** Discovery reaches a
third party, so firing it on every statute lookup would cost every user
seconds and an outbound request for something they did not ask for. A false
negative costs one follow-up question; a false positive costs everyone.

### Measured end to end

``` text
"give me supreme court cases related to drugs and bail"
    rewrite : narcotic drugs psychotropic substances offences to be
              cognizable and non-bailable
    result  : 10 statutes + 5 judgments -- Satender Kumar Antil (the
              leading bail authority), Sushanta Kumar Banik (NDPS bail),
              Om Prakash, Vijay Madanlal Choudhary

"what does section 138 say about cheque bounce"
    result  : 10 statutes, 0 judgments -- the gate correctly did not fire
```

And the loop closes. One question moved the corpus and the graph:

``` text
judgments        9 -> 14      (+5)
CITES_SECTION   24 -> 53      (+29)
```

That is the growth bulk ingest was going to buy, obtained from ordinary
use and targeted at what users actually ask about. It is also why the
Supreme Court bulk ingest was dropped rather than shelved.

### Not measured

Judgment relevance has no ground truth. `retrieval.json` grades sections
because the correct provision for a question is a fact; the set of
judgments that correctly answer "cases about NDPS bail" runs to dozens, and
a hand-written list of five grades the list, not the system. A spot check
against authorities named in advance scored 2/5, 3/4 and 1/5 -- but the
misses included Ram Samujh and Surinder Singh Deswal, which are correct
answers that were simply not on the list. Building a real judgment
benchmark is its own piece of work.
