"""Persistence for cases. The only thing that writes case state.

Normalised rather than one JSONB blob because the three child relations
have genuinely different cardinality and are queried differently: documents
are joined against `documents`, findings are read on every new research
session, and questions are an append-only log. A blob would make "which
cases cite this section" impossible to ask.

Schema is created idempotently by ensure_case_schema, following the pattern
in knowledge.static.db.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg

from legal_ai.case.models import Case
from legal_ai.context.models import EstablishedFinding


def ensure_case_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            court TEXT,
            state TEXT,
            case_number TEXT,
            parties JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,

            -- Nullable because cases predate accounts. A case with no owner
            -- is readable by nobody through the API; the column is what the
            -- API filters on, and NULL matches no user.
            user_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_documents (
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            document_id TEXT NOT NULL,
            attached_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (case_id, document_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_findings (
            finding_id BIGSERIAL PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            claim TEXT NOT NULL,
            evidence_ids JSONB NOT NULL,
            depends_on JSONB NOT NULL DEFAULT '[]'::jsonb,
            established_at TIMESTAMPTZ NOT NULL,
            UNIQUE (case_id, claim)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_sessions (
            session_id BIGSERIAL PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            asked_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    # The catalog is checked before any ALTER is issued. `ADD COLUMN IF NOT
    # EXISTS` still requests ACCESS EXCLUSIVE when it has nothing to do, and
    # a *pending* request for that lock blocks every reader queued behind
    # it. Measured three times in this codebase: called per operation, it
    # froze the database for readers each time.
    has_owner = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'cases' AND column_name = 'user_id'"
    ).fetchone()
    if has_owner is None:
        conn.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS user_id TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS case_sessions_case_idx ON case_sessions (case_id, asked_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS cases_user_idx ON cases (user_id)")
    conn.commit()

    # Uploaded files, last because they reference cases. Imported here
    # rather than at module scope: case.files imports nothing from this
    # module, and keeping it that way makes the direction obvious.
    from legal_ai.case.files import ensure_case_file_schema

    ensure_case_file_schema(conn)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_case(
    conn: psycopg.Connection,
    case_id: str,
    title: str,
    court: str | None = None,
    state: str | None = None,
    case_number: str | None = None,
    parties: tuple[str, ...] = (),
) -> Case:
    """Create a case, or return the existing one unchanged.

    Idempotent rather than raising: Flow B (create case -> upload -> research)
    is a UI wizard a user can resubmit, and a duplicate submission must not
    lose the documents already attached to the first attempt.
    """
    now = _now()
    conn.execute(
        """
        INSERT INTO cases (case_id, title, court, state, case_number, parties,
                           created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id) DO NOTHING
        """,
        (case_id, title, court, state, case_number, json.dumps(list(parties)), now, now),
    )
    conn.commit()
    stored = get_case(conn, case_id)
    assert stored is not None  # just inserted or already present
    return stored


def attach_document(conn: psycopg.Connection, case_id: str, document_id: str) -> None:
    """Put a document in the case. Re-attaching is a no-op, not an error."""
    conn.execute(
        """
        INSERT INTO case_documents (case_id, document_id, attached_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (case_id, document_id) DO NOTHING
        """,
        (case_id, document_id, _now()),
    )
    _touch(conn, case_id)


def record_finding(
    conn: psycopg.Connection,
    case_id: str,
    finding: EstablishedFinding,
) -> None:
    """Promote a research finding to the case.

    Re-establishing the same claim updates its evidence rather than storing
    it twice -- a later session that grounds a claim better should improve
    the record, not duplicate it.
    """
    conn.execute(
        """
        INSERT INTO case_findings (case_id, claim, evidence_ids, depends_on, established_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (case_id, claim) DO UPDATE SET
            evidence_ids = EXCLUDED.evidence_ids,
            depends_on = EXCLUDED.depends_on,
            established_at = EXCLUDED.established_at
        """,
        (
            case_id,
            finding.claim,
            json.dumps(list(finding.evidence_ids)),
            json.dumps(list(finding.depends_on)),
            _now(),
        ),
    )
    _touch(conn, case_id)


def record_session(conn: psycopg.Connection, case_id: str, question: str) -> None:
    """Log that a question was researched against this case."""
    conn.execute(
        "INSERT INTO case_sessions (case_id, question, asked_at) VALUES (%s, %s, %s)",
        (case_id, question, _now()),
    )
    _touch(conn, case_id)


def _touch(conn: psycopg.Connection, case_id: str) -> None:
    conn.execute("UPDATE cases SET updated_at = %s WHERE case_id = %s", (_now(), case_id))
    conn.commit()


def get_case(conn: psycopg.Connection, case_id: str) -> Case | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, court, state, case_number, parties, created_at, updated_at
            FROM cases WHERE case_id = %s
            """,
            (case_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        title, court, state, case_number, parties, created_at, updated_at = row

        cur.execute(
            "SELECT document_id FROM case_documents WHERE case_id = %s ORDER BY attached_at, document_id",
            (case_id,),
        )
        document_ids = tuple(r[0] for r in cur.fetchall())

        cur.execute(
            """
            SELECT claim, evidence_ids, depends_on FROM case_findings
            WHERE case_id = %s ORDER BY established_at, finding_id
            """,
            (case_id,),
        )
        findings = tuple(
            EstablishedFinding(
                claim=claim,
                evidence_ids=tuple(evidence_ids),
                depends_on=tuple(depends_on),
                source_case_id=case_id,
            )
            for claim, evidence_ids, depends_on in cur.fetchall()
        )

        cur.execute(
            "SELECT question FROM case_sessions WHERE case_id = %s ORDER BY asked_at, session_id",
            (case_id,),
        )
        questions = tuple(r[0] for r in cur.fetchall())

    return Case(
        case_id=case_id,
        title=title,
        court=court,
        state=state,
        case_number=case_number,
        parties=tuple(parties),
        document_ids=document_ids,
        findings=findings,
        research_questions=questions,
        created_at=created_at,
        updated_at=updated_at,
    )


def list_cases(conn: psycopg.Connection, limit: int = 50) -> list[tuple[str, str, datetime]]:
    """(case_id, title, updated_at), most recently touched first.

    Deliberately not full Case objects: the case picker in Flow A renders a
    list, and loading every case's documents and findings to draw it would
    read the whole workspace to show a dozen titles.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT case_id, title, updated_at FROM cases ORDER BY updated_at DESC LIMIT %s",
            (limit,),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]
