# HTTP API — Pramāṇa AI

The backend lives in `src/api/`. It is a FastAPI service over the research
system in `src/legal_ai/`, which it calls and never imports the other way
round.

```
POST /auth/register   create an account
POST /auth/login      exchange credentials for a bearer token
GET  /auth/me         who the token belongs to
POST /research        answer one legal question
GET  /health          liveness plus store connectivity
```

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

## 4. `POST /research`

Requires a bearer token.

```json
{
  "question": "builder failed to give possession on time, can I get a refund",
  "case_id": null,
  "document_ids": [],
  "verification_level": "verified"
}
```

| Field | Required | Notes |
|---|---|---|
| `question` | yes | 1–4000 characters, not only whitespace |
| `case_id` | no | Scopes the thread to a case |
| `document_ids` | no | Up to 50 |
| `verification_level` | no | `quick` or `verified`; omitted uses the configured default |

### Response

```json
{
  "success": true,
  "data": {
    "answer": {
      "question": "...",
      "lede": "Yes, on demand.",
      "key_elements": [{ "text": "...", "evidence_ids": ["act:2158:sec-18"], "paragraph": null }],
      "applicable_law": ["act:2158:sec-18"],
      "key_judgments": ["judgment:escr010003392021"],
      "needs_verification": [],
      "partially_supported": [],
      "unchecked": [],
      "support_not_checked": false,
      "citations": ["act:2158:sec-18"],
      "disclaimer": "..."
    },
    "clarification_needed": null,
    "text": "plain-text rendering",
    "verification_level": "verified"
  }
}
```

**The four claim slots stay four slots.** Do not merge them in a client:

| Slot | Meaning |
|---|---|
| `key_elements` | Checked, and the source supports it |
| `partially_supported` | The source is narrower than the claim |
| `needs_verification` | Evidence is *against* the claim |
| `unchecked` | Nobody looked |

`unchecked` and `needs_verification` are different facts. Collapsing them
presents an unexamined claim as a refuted one, or worse, the reverse.

`key_judgments` is ordered strongest first — by how often other judgments
cite it, with bench size as the tie-breaker.

### Clarification

When a missing fact makes the question unanswerable, the graph halts and
asks. That is a **200 with `answer: null`**, not an error — nothing went
wrong, and the client needs the user's next sentence rather than a fixed
request.

```json
{ "success": true, "data": { "answer": null, "clarification_needed": "Which state?", "text": null, "verification_level": "quick" } }
```

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Malformed body |
| 401 | `not_authenticated` | No usable token |
| 429 | `rate_limited` | Past the per-user AI budget |
| 500 | `internal_error` | A bug. Details are in the server log only |
| 504 | `timeout` | The run outlived `LEGAL_AI_RESEARCH_TIMEOUT` |

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
| `/research` | 20 / minute | **User id** |

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
  caller can read any case by id. **This is not multi-tenant safe.**
- **No logout or revocation.** Expiry is the only bound on a leaked token.
- **Open registration.** Anyone who can reach the service can create an
  account and spend model budget.
- **`POST /auth/register` is an enumeration surface** — 409 reveals that an
  address exists. Registration cannot hide this the way login does; rate
  limiting is the only mitigation.
- **No pagination or list endpoints.** `utils/pagination.py` exists for the
  first one that needs it.
- **No streaming, no progress, no cancellation.**
- **No per-user audit** of who asked what.
- **No CORS configuration**, so a browser on another origin cannot call this.
