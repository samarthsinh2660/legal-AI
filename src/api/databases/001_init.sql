-- Pramana AI -- the whole Postgres schema, in one file.
--
-- Runs automatically on an empty database: docker-compose mounts this into
-- the Postgres image's /docker-entrypoint-initdb.d, which executes it once,
-- on first start, before the server accepts connections.
--
-- The application also creates these tables itself, through the ensure_*
-- functions in legal_ai/knowledge/static/db.py, legal_ai/case/ and
-- api/accounts/repository.py. Both paths exist on purpose: this file makes a
-- fresh deployment or a new laptop work with `docker compose up`, and the
-- ensure_* functions keep a long-lived database that predates this file
-- working too. Every statement here is IF NOT EXISTS, so they cannot
-- conflict.
--
-- Keep the two in step. If you add a column in Python, add it here.

CREATE EXTENSION IF NOT EXISTS vector;


-- ---------------------------------------------------------------- corpus

-- Statutes and judgments. `full_text` is the document; `embedding` is set
-- only for documents short enough to embed whole -- longer ones are
-- represented by their rows in document_chunks instead, and carry NULL here.
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    document_type   TEXT NOT NULL,
    title           TEXT NOT NULL,
    court           TEXT,
    citation        TEXT,
    case_number     TEXT,
    parties         JSONB,
    decision_date   DATE,
    enactment_date  DATE,
    disposal_nature TEXT,
    act_id          TEXT,
    full_text       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    provenance      JSONB NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL,
    embedding       VECTOR(768),

    -- Read from the judgment's own header. NULL means the bench could not
    -- be parsed, never that it was one judge.
    judges          JSONB,
    bench_size      INT
);

-- Keyword search. Generated, so it cannot drift from the text it indexes.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(full_text, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS documents_search_vector_gin
    ON documents USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS documents_embedding_hnsw
    ON documents USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS documents_bench_size_idx
    ON documents (bench_size DESC NULLS LAST);


-- The embeddable pieces of a long document. A document is represented in
-- vector search exactly once: short ones by documents.embedding, long ones
-- by these rows.
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id    TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal     INT NOT NULL,
    label       TEXT,
    text        TEXT NOT NULL,
    embedding   VECTOR(768),
    UNIQUE (document_id, ordinal)
);

CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx
    ON document_chunks (document_id);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops);


-- Superseded text. `documents` always holds current law; when re-ingestion
-- finds different text, the old row is copied here first, so an amendment
-- never destroys what it replaced.
--
-- Both timestamps are observation times, not legal dates: `first_seen_at` is
-- when we ingested that text, `superseded_at` when we ingested something
-- different. Neither is a commencement date.
CREATE TABLE IF NOT EXISTS document_versions (
    version_id    BIGSERIAL PRIMARY KEY,
    document_id   TEXT NOT NULL,
    title         TEXT NOT NULL,
    full_text     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    provenance    JSONB NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    superseded_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS document_versions_lookup_idx
    ON document_versions (document_id, superseded_at);


-- ------------------------------------------------------------------ cases

CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    court       TEXT,
    state       TEXT,
    case_number TEXT,
    parties     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
    -- NOTE: no owner column. Any authenticated caller can read any case.
    -- This is the gap that makes the API not multi-tenant safe; see
    -- docs/API.md section 9.
);

CREATE TABLE IF NOT EXISTS case_documents (
    case_id     TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    attached_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (case_id, document_id)
);

-- What a case has established, so the fourth question about a matter does
-- not re-derive what the first three settled.
CREATE TABLE IF NOT EXISTS case_findings (
    finding_id     BIGSERIAL PRIMARY KEY,
    case_id        TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    claim          TEXT NOT NULL,
    evidence_ids   JSONB NOT NULL,
    depends_on     JSONB NOT NULL DEFAULT '[]'::jsonb,
    established_at TIMESTAMPTZ NOT NULL,
    UNIQUE (case_id, claim)
);

CREATE TABLE IF NOT EXISTS case_sessions (
    session_id BIGSERIAL PRIMARY KEY,
    case_id    TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    question   TEXT NOT NULL,
    asked_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS case_sessions_case_idx
    ON case_sessions (case_id, asked_at);


-- A client's uploaded documents. Deliberately NOT in `documents`: an
-- uploaded pleading is the client's, not corpus, and must never be returned
-- by a corpus search.
CREATE TABLE IF NOT EXISTS case_files (
    document_id  TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    media_type   TEXT NOT NULL,
    full_text    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL,

    -- Extracted structure, cached so opening a case does not re-run the
    -- Document Agent over every file.
    facts        JSONB
);

CREATE INDEX IF NOT EXISTS case_files_case_idx
    ON case_files (case_id, uploaded_at);


-- --------------------------------------------------------------- accounts

-- Email is stored lower-cased, and unique, so one mailbox cannot become two
-- accounts. Ids are random rather than sequential: a caller holding one
-- valid id must not be able to guess its neighbours.
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
