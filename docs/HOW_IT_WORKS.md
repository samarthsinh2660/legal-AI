# How this system works

Plain English, no prior context assumed. If you read one document about
Pramāṇa, read this one.

---

## 1. What it is for

A lawyer asks a question about Indian law. The system answers it, and every
statement in that answer points at a real document it can show you.

That second half is the whole product. Ask any general chatbot a legal
question and you get fluent, confident text containing case names that do
not exist and sections that say something else. For legal work that is
worse than no answer, because it looks right.

So the rule the system is built around:

> It reasons **over** legal evidence. It does not invent legal knowledge.

Everything below exists to make that rule hold under load, under failure,
and under a model that would happily make things up.

---

## 2. The four things it does

**Answer a question.** Search the law we hold, read what is relevant, write
an answer where each claim carries the id of the document it came from.

**Read your documents.** Upload a petition or a notice; it extracts the
parties, dates and sections and uses them as context for the questions you
ask afterwards.

**Remember a matter.** A "case" holds documents and findings, so the fourth
question does not re-derive what the first three settled.

**Draft a document.** Turn the conversation into a `.docx` — an opinion, a
notice — citing only law the thread actually established.

---

## 3. The moving parts

Six containers. Each does one thing.

```
   your browser
        │  one HTTPS connection, nothing else
        ▼
   ┌─────────┐        ┌────────────┐
   │   API   │───────►│  POSTGRES  │◄───────┐
   └─────────┘        │            │        │
                      │  the law   │   ┌────────┐
   ┌──────────┐       │  your work │   │ WORKER │
   │  NEO4J   │◄──────│  the queue │   └────────┘
   │ citation │       └────────────┘        │
   │  graph   │                             ▼
   └──────────┘                   ┌──────────────────┐
                                  │ EMBEDDER │ RERANK│
                                  └──────────────────┘
```

| Part | What it does |
|---|---|
| **API** | Takes requests. Writes them down. Never does slow work itself. |
| **Worker** | Does the slow work: searching, reasoning, drafting. |
| **Postgres** | The law, your threads, and the job queue — all one database. |
| **Neo4j** | Which judgment cites which. Used for ranking authority. |
| **Embedder / Reranker** | Two small model servers, so no other container has to load a 1.3 GB model. |

The browser only ever talks to the API. It never sees the worker — that is
what lets a worker run on a different machine with no open ports.

---

## 4. What happens when you ask a question

The important idea: **asking and answering are separate.**

```
  1. You send a question.
     The API writes it down and hands back a ticket. ~20 milliseconds.

  2. A worker picks the ticket up and starts work.

  3. It plans what to search for.                     ~7s
  4. It searches the law and ranks what it found.     ~11s
  5. It writes the answer from what it found.         ~7s
  6. It checks every claim against its source.
  7. It saves the answer.

  Meanwhile your browser watches the ticket and shows each step as it
  finishes. Total: about 18 to 40 seconds.
```

**Why a ticket instead of just waiting?** Because a question takes half a
minute, and in that time anything can happen. You close the tab. Your wifi
drops. We deploy. If the answer only existed inside your HTTP request, all
of those lose it — along with the money already spent on the model.

Because it is a ticket, none of them matter. The work is a row in a
database. Close the laptop and it still finishes; the answer is waiting
when you come back.

---

## 5. What happens when things go wrong

This is most of the engineering, so it is worth stating plainly.

| What happens | What you see |
|---|---|
| You close the tab | Nothing lost. The answer is there when you return. |
| You refresh | It reattaches and replays the steps you missed. |
| You open a second device | Both watch the same run and see the same thing. |
| We deploy mid-question | The worker finishes yours first, then exits. |
| A worker crashes | Another picks the question up within seconds. |
| A worker crashes *after searching* | The replacement reuses the search. ~1s, not ~30s. |
| The same job is retried twice | Only one answer is ever stored. |
| You press Stop | It stops at the next step and stops charging. |
| The whole question fails | The thread says so. It never pretends. |

The last row is the one that matters most. A system like this fails
quietly by default — half an answer looks like a whole one. So every check
has a third state:

    "we checked and it holds"
    "we checked and it does not"
    "we could not check"        ← never rendered as the first

---

## 6. How it avoids making things up

Four mechanisms, in the order they act.

**1. It can only cite what it retrieved.** The writing step is handed a
list of documents and their ids. It answers from those. A case name it has
not been given is not available to it.

**2. Every claim carries its source ids.** Not prose with footnotes — a
structured list, where each statement names the documents behind it.

**3. Every claim is checked before you see it.** The claims are compared
back against their sources. Anything that does not hold is moved into a
different bucket, not deleted:

    key_elements          checked, and the source supports it
    partially_supported   the source supports part of it
    needs_verification    the source does not support it
    unchecked             we could not check this one

**4. It says what it does not have.** The corpus is central Indian
legislation and about 12,000 judgments, mostly Supreme Court. It does not
hold most state rules. Asked something outside that, it says so rather
than guessing — and the wording is careful: *"no negative treatment among
the judgments we hold"*, never *"this is good law"*.

### Checked, not assumed

`scripts/qa/run_grounding_qa.py` puts real questions through the live
system and looks up every id the answer cites in the database. Last run,
10/10:

    every citation resolved to a document we hold      3/3 and 4/4
    every claim shown as supported carried its sources 4 grounded, 0 bare
    a question about state rules invented nothing      and said why
    a question the retrieved law did not cover         invented nothing

The suite is worth running after any change to retrieval or the analyst.
It is the only test that checks the thing the product is named after.

---

## 7. Why it is as fast as it is, and not faster

A warm question is 18–40 seconds. Where that goes:

    planning what to search      ~7s   a model call
    searching and ranking       ~11s   mostly one CPU model
    writing the answer           ~7s   a model call

The first question after a restart used to take 108 seconds. Most of that
was the worker loading its models while you waited. It now loads them
before it says it is ready, so nobody waits for that.

**The two things that would actually make it faster:**

- **A GPU.** The ranking step is a model running on CPU. On a GPU the same
  model over the same documents takes 0.61s instead of 5.12s, with an
  identical result. That is about 8 seconds off every question.
- **A paid model key.** On the free tier the model refuses requests when
  the quota runs out, and the system waits and retries. That wait can be
  most of a slow question, and it is also why running three workers does
  not answer three times as fast — they share one quota.

---

## 8. The words you will see in the code

| Word | Means |
|---|---|
| **run** | One unit of work — a question or a draft. A row in `runs`. |
| **thread** | A conversation. Holds messages. |
| **case** | A matter. Holds documents and findings across threads. |
| **evidence** | A retrieved passage plus where it came from. |
| **claim** | One statement in an answer, with the ids behind it. |
| **checkpoint** | The evidence a run found, kept so a retry need not search again. |
| **heartbeat** | A worker saying "still alive". A stale one means nobody is working. |
| **the reaper** | The sweep that finds runs nobody is working on. |

---

## 9. Running it

```bash
export LEGAL_AI_JWT_SECRET="$(openssl rand -hex 32)"
docker compose up -d
```

Six containers come up. The API is on `:8000`. The first start downloads
the two models, which takes a few minutes; after that they live in a
volume.

**Both the API and the worker are needed.** An API on its own accepts
questions that nothing will ever answer.

To run the tests, stop the worker first — several of them queue a job and
then claim it, and a live worker takes it instead:

```bash
docker compose stop worker
pytest -q --ignore=tests/evals
```

---

## 10. What is not built

Named plainly, because a gap you know about is a decision and a gap you do
not is a bug:

- **No GPU in the containers.** Measured and worth doing; needs a host
  package (`nvidia-container-toolkit`) that is not installed.
- **Closing the tab does not cancel.** The Stop button does. Walking away
  does not, and you keep paying for that run.
- **A draft slower than ten minutes could be retried while still running.**
  It heartbeats once before the model call, not during it.
- **State rules are not in the corpus.** This is why it cannot give a
  homebuyer the prescribed interest rate.
- **Nobody has driven the UI in a browser recently.** The screens are
  covered by tests, not by eyes.

---

## 11. Where to read more

    RELIABILITY_ARCHITECTURE.md   why the queue, the worker and the streams
                                  are shaped the way they are
    API.md                        every endpoint, and what it returns

And three suites you can run yourself against a live stack:

    scripts/qa/run_grounding_qa.py   does it invent law?
    scripts/qa/run_queue_qa.py       does the queue behave?
    scripts/qa/run_failure_qa.sh     what happens when processes die?
    TODO.md                       what is known to be missing
