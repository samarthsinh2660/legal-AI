# HTTP API — Pramāṇa AI

The backend lives in `src/api/`. It is a FastAPI service over the research
system in `src/legal_ai/`, which it calls and never imports the other way
round.

```
POST /auth/register            create an account
POST /auth/login               exchange credentials for a bearer token
GET  /auth/me                  who the token belongs to

POST /threads                  start a research thread
GET  /threads                  this user's threads
POST /threads/{id}/messages    ask, or follow up
POST /threads/{id}/messages/stream   the same, as Server-Sent Events
GET  /threads/{id}/messages    the conversation

POST /cases                    create a matter
GET  /cases                    this user's matters
GET  /cases/{id}               one matter
PATCH  /cases/{id}             rename or re-tag it
DELETE /cases/{id}             delete it; its threads detach, not vanish
POST /cases/{id}/threads       "Save to case" -- attach an existing thread

POST /cases/{id}/documents     upload a file for the Document Agent
GET  /cases/{id}/documents     what is attached

GET  /health                   liveness plus store connectivity
```

**A thread is the conversation.** `design/UX_FLOWS.md` Screen 3 is one pane
of follow-ups; there is no one-shot research mode in the product, so there
is no one-shot endpoint. A *case* is the container above a thread, holding
the documents and findings that many threads share.

Interactive docs are at `/docs` when the server is running.

---

## 1. Running it locally

Everything, in containers:

```bash
export LEGAL_AI_JWT_SECRET="$(openssl rand -hex 32)"   # required, >= 32 bytes
docker compose up -d
```

That starts Postgres, Neo4j and the API. The schema in
`src/api/databases/001_init.sql` is applied automatically on a **fresh**
Postgres volume, before the server accepts connections. An existing volume
is left alone -- to re-apply it, remove the volume.

The API alone, against containerised stores:

```bash
docker compose up -d postgres neo4j
export LEGAL_AI_JWT_SECRET="$(openssl rand -hex 32)"
.venv/bin/uvicorn api.main:app --reload --port 8000
```

Postgres and Neo4j must be up either way. Without them the
service still starts and `/health` reports `degraded` — that is deliberate,
so an orchestrator does not restart a process that cannot fix a database by
dying.

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `LEGAL_AI_JWT_SECRET` | *(unset — every request rejected)* | Token signing key. Must be at least 32 bytes. |
| `DATABASE_URL` | `postgresql://legal_ai:legal_ai_dev@localhost:5433/legal_ai` | Postgres DSN. |
| `LEGAL_AI_DB_POOL_MIN` / `_MAX` | `1` / `10` | Connection pool size. |
| `LEGAL_AI_RESEARCH_TIMEOUT` | `300` | Seconds before a research request answers 504. |
| `LEGAL_AI_VERIFICATION_LEVEL` | `quick` | Default mode when a request omits one. |
| `LEGAL_AI_TRUST_PROXY_HEADER` | `false` | Read `X-Forwarded-For` for rate limiting. Only true behind a proxy. |
| `API_PORT` | `8000` | Host port for the API container. |
| `LEGAL_AI_CORS_ORIGINS` | *(unset — no cross-origin access)* | Comma-separated origins a browser may call from. No wildcard: any site a user visits could otherwise call this with their token. |

**No secret means no service.** An unset `LEGAL_AI_JWT_SECRET` rejects every
authenticated request with 503. The alternative default — no secret means
auth disabled — turns one missing variable into an open endpoint.

### Schema

`src/api/databases/001_init.sql` is the whole Postgres schema -- corpus,
cases and accounts -- in one file. The application also creates these tables
itself through its `ensure_*` functions, and both paths exist on purpose:
the SQL makes a fresh deployment work with one command, the functions keep a
long-lived database working. Every statement is `IF NOT EXISTS`, so they
cannot conflict.

**If you add a column in Python, add it to that file.** Nothing checks the
two agree.

Neo4j has no equivalent: its nodes and relationships are created by the
ingest pipeline, not declared up front.

---

## 2. The response envelope

Every response has the same outer shape. A client checks `success` to know
which it got.

```json
{ "success": true,  "data": { ... } }
{ "success": false, "error": { "code": "...", "message": "..." } }
```

`error.code` is stable and is what a client should branch on. `error.message`
is a sentence for whoever made the request, and its wording may change.

Nothing in an error body is ever built from an exception — no stack traces,
no driver messages, no connection strings.

---

## 3. Authentication

A bearer token, obtained from `/auth/login`.

```
Authorization: Bearer <access_token>
```

Tokens are JWTs signed with HS256, valid for **one hour**. They are
stateless, so **there is no logout that invalidates an issued token** —
expiry is the only bound. Revocation would need a token store.

### `POST /auth/register`

```json
{ "email": "advocate@example.com", "password": "at-least-12-characters" }
```

```json
{ "success": true, "data": { "user_id": "9351a80dd822498a8d20790ef8265614" } }
```

Password minimum is 12 characters. Email is stored lower-cased, so
`Sam@x.com` and `sam@x.com` are one account.

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Bad email, or password under 12 characters |
| 409 | `email_taken` | That address already has an account |

### `POST /auth/login`

```json
{ "email": "advocate@example.com", "password": "at-least-12-characters" }
```

```json
{ "success": true, "data": { "access_token": "eyJhbGci...", "token_type": "bearer" } }
```

| Status | `code` | When |
|---|---|---|
| 401 | `invalid_credentials` | Unknown address **or** wrong password |
| 503 | `auth_unavailable` | No signing secret configured |

An unknown address and a wrong password return **byte-identical** responses,
and take the same time. Anything else would let a caller discover which
addresses hold accounts.

### `GET /auth/me`

```json
{ "success": true, "data": { "user_id": "9351a80d...", "email": "advocate@example.com" } }
```

401 for a missing, expired, forged or malformed token, and for a valid token
whose account has since been deleted. All four answer the same.

---

## 4. Threads

A thread is a conversation. Every message is either researched or answered
from the thread so far, and the reply says which.

### `POST /threads`

```json
{ "title": "Late possession refund", "case_id": null }
```

Attaching a `case_id` seeds every question in the thread with that matter's
parties, documents and already-established findings.

### `POST /threads/{id}/messages`

```json
{ "message": "what about bombay" }
```

A follow-up is **rewritten into a standalone question before retrieval** --
"what about bombay" retrieves nothing on its own. The rewrite is a retrieval
device: what is stored and shown back is what the user typed.

```json
{
  "success": true,
  "data": {
    "text": "plain-text rendering",
    "answer": { "...": "the same DraftAnswer shape as before" },
    "route": "RESEARCH",
    "verification_level": "quick"
  }
}
```

`route` is echoed because the two carry different authority:

| `route` | Meaning |
|---|---|
| `RESEARCH` | The corpus was searched for this |
| `ANSWER` | Answered from earlier in the thread |

A UI that renders them identically is making a claim the system did not.
When in doubt the router researches: answering from memory when fresh law
was wanted is a wrong answer, researching unnecessarily is only slow.

**The four claim slots stay four slots** inside `answer` -- see §4.1 below.

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Malformed body |
| 401 | `not_authenticated` | No usable token |
| 404 | `not_found` | No such thread, or not yours |
| 429 | `rate_limited` | Past the per-user AI budget |
| 504 | `timeout` | The run outlived the limit |

A 504 stores nothing: a half-turn in the thread would be resolved against by
the next rewrite as though it were an answer.

### `POST /threads/{id}/messages/stream`

The same turn, as Server-Sent Events. Same body, same reply -- the
difference is that you see the wait.

A researched answer takes **one to two minutes**. Measured on a real run:

```
  0.4s  step  Reading your documents
  0.4s  step  Understanding the question
  0.4s  step  Checking what is missing
 77.7s  step  Searching statutes and judgments      <- 63% of the wall time
123.1s  step  Drafting the analysis
123.1s  step  Checking every claim against its source
123.2s  step  Assembling the answer
123.2s  done
```

Without this a client shows a blank pane for two minutes and the user
assumes the page has hung: the answer is right and the product looks broken.

| Event | Data |
|---|---|
| `step` | `{"node": "research", "label": "Searching statutes and judgments"}` |
| `done` | the same body `POST /messages` returns |
| `error` | `{"code": "...", "message": "..."}` |

`node` is the graph's own node name and is the stable key -- bind UI rows to
it, not to `label`, which is prose and may be reworded. The seven nodes are
`document`, `context_builder`, `clarification`, `research`, `analyst`,
`verification`, `draft`.

**Steps are emitted when a node actually finishes.** There is no timer and no
interpolation: a slow search shows as a step that sits there, which is the
truth. `design/UX_FLOWS.md` requires this pane to "show real work, never fake
thinking", and a progress bar that advances on a clock is exactly the thing
it forbids.

The plain `POST /messages` still exists for clients that would rather block.

### 4.1 The answer shape

```json
{
  "question": "...", "lede": "Yes, on demand.",
  "key_elements": [{ "text": "...", "evidence_ids": ["act:2158:sec-18"] }],
  "applicable_law": ["act:2158:sec-18"],
  "key_judgments": ["judgment:escr010003392021"],
  "needs_verification": [], "partially_supported": [], "unchecked": [],
  "support_not_checked": false, "citations": [], "disclaimer": "..."
}
```

| Slot | Meaning |
|---|---|
| `key_elements` | Checked, and the source supports it |
| `partially_supported` | The source is narrower than the claim |
| `needs_verification` | Evidence is *against* the claim |
| `unchecked` | Nobody looked |

`unchecked` and `needs_verification` are different facts. Collapsing them
presents an unexamined claim as a refuted one, or worse, the reverse.

`key_judgments` is ordered strongest first -- citation count, with bench size
as the tie-breaker.

---

## 4.2 Documents

### `POST /cases/{case_id}/documents`

`multipart/form-data`, field `file`. PDF, DOCX, TXT or MD, up to 25MB.

```json
{ "success": true, "data": { "document_id": "case-file:...", "filename": "deed.pdf", "characters": 48210 } }
```

Text is extracted **at upload**, not at question time: parsing a 300-page PDF
per question puts seconds on every answer, and an unreadable file should fail
while the user is still looking at it.

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Unsupported type, empty, too large, or no text layer (an un-OCR'd scan) |
| 404 | `not_found` | No such case |

Uploads go to `case_files`, **never** the corpus. A client's pleading is
theirs, and must never come back from a search someone else runs.

---

## 5. `GET /health`

Unauthenticated and never rate limited: a liveness probe runs outside any
secret the app holds, and throttling it turns load into a restart loop.

```json
{ "success": true, "data": { "status": "ok", "postgres": true, "neo4j": true } }
```

**Always 200 while the process is up.** A store being down shows as
`"status": "degraded"` with the offending flag false. Returning 503 would
make an orchestrator restart a process that is running correctly.

---

## 6. Rate limiting

| Scope | Limit | Keyed by |
|---|---|---|
| Everything except `/health` | 60 / minute | Client address |
| Sending a message | 20 / minute | **User id** |

A 429 carries `Retry-After` in seconds.

The AI budget is per user rather than per address, so one account behind a
shared office address cannot spend everyone else's model quota.

**Counters are per process.** Four workers means four times the limit; two
replicas, eight. A limit that holds across processes needs shared state.

---

## 7. Verification levels

| | `quick` | `verified` |
|---|---|---|
| Deterministic checks | yes | yes |
| Model-based support check | no | yes |
| Extra model calls | 0 | 1 per answer |

Two invariants hold across both, and are tested:

1. **The answer body is identical.** `verified` adds annotation; it never
   rewrites, softens or removes what was said.
2. **A run that asks for `verified` and cannot get it says so.** It never
   returns `quick` output wearing a `verified` label.

---

## 8. Long-running requests

A research call runs the graph in a worker thread under a timeout, so it
cannot block the event loop and stall `/health`.

The timeout bounds **the client's wait, not the run**. Python cannot
interrupt a blocking call, so a request that answers 504 leaves a thread
still working and still spending model budget until it finishes. Cancelling
properly needs a job queue.

---

## 9. Limits

Present because they are absent, not because they are planned.

- **No case ownership.** `cases` has no owner column, so any authenticated
  caller can read any case by id, and upload documents to it. Threads *are*
  owned; cases are not. **This is not multi-tenant safe.**
- **`ANSWER` returns the previous reply verbatim.** It is honest -- that is
  what the user is asking about -- but it is not yet a real answer over the
  stored claims.
- **Logout revokes one token, not a whole account.** Signing out on a laptop
  leaves a phone signed in, which is usually what is wanted; there is no
  "sign out everywhere".
- **Open registration.** Anyone who can reach the service can create an
  account and spend model budget.
- **`POST /auth/register` is an enumeration surface** — 409 reveals that an
  address exists. Registration cannot hide this the way login does; rate
  limiting is the only mitigation.
- **No pagination or list endpoints.** `utils/pagination.py` exists for the
  first one that needs it.
- **No streaming, no progress, no cancellation.**
- **No per-user audit** of who asked what.
- **CORS is off until `LEGAL_AI_CORS_ORIGINS` is set.** Deliberate: a
  wildcard would let any site a user visits make authenticated calls.
