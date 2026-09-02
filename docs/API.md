# HTTP API — Pramāṇa AI

The backend lives in `src/api/`. It is a FastAPI service over the research
system in `src/legal_ai/`, which it calls and never imports the other way
round.

```
POST /auth/register            create an account
POST /auth/login               a bearer token, and who it is for

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

GET  /search                   the corpus directly, unverified
GET  /graph/{document_id}      the citation graph, read-only

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

Tokens are JWTs signed with HS256, valid for **24 hours** by default — set
`LEGAL_AI_JWT_EXPIRES_IN` (seconds) to change it. They are stateless and
there is no denylist: **an issued token cannot be withdrawn**, so
`POST /auth/logout` ends the session on the client and expiry is the only
bound on a leaked one. Shorten `LEGAL_AI_JWT_EXPIRES_IN` if that window
matters more than staying signed in.

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

**`/auth/login` answers with the identity, not just the token:**

```json
{ "success": true, "data": {
  "access_token": "eyJhbGci...", "token_type": "bearer",
  "user_id": "9351a80d...", "email": "advocate@example.com"
}}
```

Both together because a client needs both. `GET /auth/me` was removed on
2026-09-03: it made every sign-in two round trips and every page load a
third, to return what the login already knew. A client restores a session
from what it stored, checking the token's own `exp` locally.

What that gives up is detecting a *deleted* account: `/auth/me` loaded the
row and 401'd, and it was the only route that did — every other route
verifies the signature and nothing else, so such a token has always worked
everywhere else. No route deletes an account, so reaching that state takes a
manual `DELETE`. Closing it properly means a user lookup on every request.

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
| `ANSWER` | Composed from claims already established in this thread |

A UI that renders them identically is making a claim the system did not.
When in doubt the router researches: answering from memory when fresh law
was wanted is a wrong answer, researching unnecessarily is only slow.

An `ANSWER` turn is **not a replay of the previous reply**. It is a new
answer to the question asked, built out of the claims earlier turns stored,
in the same `answer` shape as a researched one — so §4.1 applies to it
unchanged. Three properties hold by construction:

- **Every id came from a stored claim.** The model is shown the stored
  claims numbered and replies with numbers; it never writes an identifier
  and never rewrites a claim, so a fabricated citation is not representable
  on this path.
- **A carried claim keeps its bucket.** An `unchecked` claim re-used in a
  later turn is still `unchecked`. Nothing is promoted by being re-emitted,
  and where a text was stored in two buckets the less reassuring one wins.
- **`support_not_checked` carries forward** from every answer the claims
  were drawn from.

When the thread holds nothing that answers the question — or the
composition fails — the reply says so and **`answer` is `null`**:

```json
{
  "success": true,
  "data": {
    "text": "I could not answer that from this conversation. …",
    "answer": null,
    "route": "ANSWER"
  }
}
```

`route: "ANSWER"` with `answer: null` is that outcome and is the one case a
client should render as a dead end rather than as a result. It does not fall
back to the previous reply, and it does not quietly research instead: a turn
that never touched the corpus must not read like one that did.

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

## 4.3 Search and the graph

### `GET /search?q=&kind=&limit=`

`kind` is `all`, `judgment` or `section`; `limit` caps at 50.

```json
{ "success": true, "data": [
  { "document_id": "judgment:...", "kind": "judgment",
    "title": "...", "citation": "...", "court": "...", "extract": "..." }
]}
```

Hybrid retrieval -- the same path a thread takes, so anything found here is
something the research agents could also find.

**Results carry no verification.** Nothing has been claimed about a search
hit, so there is nothing to check. A client must not render them with the
badges an answer's citations carry.

### `GET /graph/{document_id}?limit=`

```json
{ "success": true, "data": {
  "nodes": [{ "id": "...", "kind": "Judgment", "title": "...", "hops": 0 }],
  "edges": [{ "source": "...", "target": "...", "kind": "CITES" }],
  "truncated": true
}}
```

`kind` on a node is `Judgment`, `Section`, `Act` or `Court`; on an edge it is
`CITES`, `CITES_SECTION`, `CONTAINS` or `DECIDED_BY`. The anchor is the
first node, at `hops: 0`.

One step out, `limit` capped at **120**. The graph holds ~48,800 nodes; the
point of this view is one document and what touches it, and a landmark with
88 citations drawn all at once says less than a list would. The `hops`
parameter was removed on 2026-09-03 — a second hop showed what the
*neighbours* cite, which is not what the reader asked about, and the UI that
offered the choice found nobody changing it.

**Render `truncated` where the reader can see it.** A graph quietly missing
half its edges is a picture that lies about how connected something is.

Read-only. There is no write path, and the corpus is not a reader's to edit.

---

## 4.4 The audit trail

### `GET /audit?limit=&offset=`

```json
{ "success": true, "data": { "items": [
  { "event_id": 41, "action": "read", "resource_type": "case",
    "resource_id": "5a4759f7...", "status": 404,
    "at": "2026-09-02T09:14:22Z" }
], "total": 128, "limit": 50, "offset": 0, "has_more": true } }
```

Your own events, newest first. There is no route that reads another user's
trail: no firm-administrator role exists yet, and adding the route before
the role would be an access-control hole dressed as a feature.

Events are written by middleware, so a route cannot forget to record one.
Sign-ins are the exception and are recorded in the accounts controller --
`/auth/login` is public, so nobody is attached to the request by the time
the middleware runs, and that is the only place that learns who the attempt
was for.

**A refused request is recorded as refused.** A 404 on someone else's case
is the row a firm looks for first.

**The trail holds no privileged content** -- no question, no answer, no
document text. All of that is stored once already under the user's own row,
and a second copy here would be another place for it to leak from.

Append-only: nothing updates or deletes an event.

Reading the trail is itself recorded: for a compliance feature, "who read
the trail" is the row a firm asks for.

| Not recorded | Why |
|---|---|
| `/health`, `/docs` | a liveness probe every ten seconds buries the rest |
| a sign-in for an unknown address | no account to attribute it to, and a row keyed by the address would be a register of who has *no* account here |
| an unauthenticated request to a protected route | auth refuses it before the audit layer runs |
| `/auth/logout` | no resource id to record; storing the path segment (`"logout"`) would fill the resource index with junk |
| a request refused by the rate limiter | the 429 is returned before auth identifies anyone |

**Known limits.**

- A failed sign-in against a *real* address is recorded, so anyone who
  knows an address can append 401 rows to that account's trail, one per
  attempt, bounded only by the per-address rate limit. Recording them is
  right; the trail has no retention or coalescing yet.
- Recording a sign-in costs the known-address branch about 5ms the
  unknown-address branch does not pay, which is a weak enumeration oracle.
  It is accepted because `POST /auth/register` already answers the same
  question with a 409, and because writing the row in the background to
  equalise it would lose events when the process stops.

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

- **`ANSWER` composes only over claims stored in the same thread.** A fact
  established in another thread on the same case is not reachable from it,
  and the turn will report that it could not answer rather than looking.
- **Logout does not invalidate the token.** There is no denylist, so a
  copy of a token keeps working until `exp` — up to
  `LEGAL_AI_JWT_EXPIRES_IN` seconds after the user signed out. The route
  exists for the client to discard its token against; it is not
  revocation, and there is no "sign out everywhere".
- **Open registration.** Anyone who can reach the service can create an
  account and spend model budget.
- **`POST /auth/register` is an enumeration surface** — 409 reveals that an
  address exists. Registration cannot hide this the way login does; rate
  limiting is the only mitigation.
- **No cancellation.** `/messages/stream` reports progress, but a client
  that disconnects leaves the run going. See §8.
- **No per-user audit** of who asked what.
- **No password change, reset, or email verification.** An account is an
  address and a hash; a forgotten password needs a DBA.
- **No refresh token.** One token, one lifetime — so
  `LEGAL_AI_JWT_EXPIRES_IN` trades staying signed in against the window a
  leaked token works. A short access token plus a refresh flow would
  separate the two.
- **CORS is off until `LEGAL_AI_CORS_ORIGINS` is set.** Deliberate: a
  wildcard would let any site a user visits make authenticated calls.
