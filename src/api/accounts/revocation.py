"""Revoked tokens, so logout actually logs out.

A stateless JWT is valid until it expires; without this a logout could only
ask the client to forget its token, which an attacker holding a copy will
decline to do.

Rows are keyed by `jti` and carry the token's own expiry. Past that moment
the token is refused anyway, so the row is only useful until then and
`purge_expired` reclaims it. Without the purge this table grows by one row
per logout forever.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg


def ensure_revocation_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti TEXT PRIMARY KEY,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS revoked_tokens_expiry_idx "
        "ON revoked_tokens (expires_at)"
    )
    conn.commit()


def revoke(conn: psycopg.Connection, jti: str, expires_at: int) -> None:
    """Refuse this token from now on.

    Idempotent: logging out twice is not an error, and raising on the second
    would make a retried request look like a failure.
    """
    if not jti:
        return
    conn.execute(
        "INSERT INTO revoked_tokens (jti, expires_at) VALUES (%s, %s) "
        "ON CONFLICT (jti) DO NOTHING",
        (jti, datetime.fromtimestamp(expires_at, tz=timezone.utc)),
    )
    conn.commit()


def is_revoked(conn: psycopg.Connection, jti: str) -> bool:
    if not jti:
        # A token with no id cannot be revoked by name. Tokens issued
        # before `jti` existed are the only ones like this, and they expire
        # within the hour.
        return False
    return (
        conn.execute(
            "SELECT 1 FROM revoked_tokens WHERE jti = %s", (jti,)
        ).fetchone()
        is not None
    )


def purge_expired(conn: psycopg.Connection) -> int:
    """Drop rows for tokens that would be refused anyway."""
    deleted = conn.execute(
        "DELETE FROM revoked_tokens WHERE expires_at < now()"
    ).rowcount
    conn.commit()
    return deleted
