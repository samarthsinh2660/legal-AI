"""The users table -- the only place that reads or writes it.

Email is folded to lower case and unique, so "Sam@x.com" and "sam@x.com"
cannot become two accounts. Uniqueness is a database constraint, not a
check-then-insert, which two simultaneous registrations would both pass.

Ids are random: sequential ones would let a caller with one valid id guess
its neighbours.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import psycopg


class DuplicateEmail(Exception):
    """That address already has an account.

    Raised rather than upserting: re-registering must not take over an
    existing account.
    """


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    password_hash: str
    # Nullable: the accounts created before names existed have none, and
    # inventing one from the address would put a guess in the sidebar.
    name: str | None = None


def ensure_account_schema(conn: psycopg.Connection) -> None:
    """Create the users table if it is absent. Idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Added after the table shipped, so it arrives by ALTER rather than in
    # the CREATE above -- an existing database never re-runs that.
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
    conn.commit()


def create_user(
    conn: psycopg.Connection, email: str, password_hash: str, name: str | None = None
) -> User:
    """Insert a user, or raise DuplicateEmail.

    Takes an already-hashed password, so plaintext never reaches a query log.
    """
    folded = email.strip().lower()
    user_id = uuid.uuid4().hex
    try:
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, name) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, folded, password_hash, name),
        )
        conn.commit()
    except psycopg.errors.UniqueViolation as exc:
        conn.rollback()
        raise DuplicateEmail(folded) from exc
    return User(
        user_id=user_id, email=folded, password_hash=password_hash, name=name
    )


def find_by_email(conn: psycopg.Connection, email: str) -> User | None:
    """The user with this address, hash included, or None.

    The only query returning a password hash -- authentication is its only
    caller. None rather than an exception, so a login can answer an unknown
    address exactly as it answers a wrong password.
    """
    row = conn.execute(
        "SELECT user_id, email, password_hash, name FROM users WHERE email = %s",
        (email.strip().lower(),),
    ).fetchone()
    return User(*row) if row else None


def find_by_id(conn: psycopg.Connection, user_id: str) -> User | None:
    """The user behind a verified token, or None if the account is gone."""
    row = conn.execute(
        "SELECT user_id, email, password_hash, name FROM users WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    return User(*row) if row else None


def update_name(conn: psycopg.Connection, user_id: str, name: str) -> User | None:
    """Set the display name, returning the updated row or None if gone.

    RETURNING rather than a second SELECT: the row a caller renders is then
    the row that was written, with no window in between.
    """
    row = conn.execute(
        "UPDATE users SET name = %s WHERE user_id = %s "
        "RETURNING user_id, email, password_hash, name",
        (name, user_id),
    ).fetchone()
    conn.commit()
    return User(*row) if row else None


def update_email(conn: psycopg.Connection, user_id: str, email: str) -> User | None:
    """Change the address, or raise DuplicateEmail if it is taken.

    Folded to lower case like `create_user`, so "Sam@x.com" cannot become a
    second account for the same person. Uniqueness is the constraint's job,
    not a check-then-update, which two simultaneous changes would both pass.
    """
    folded = email.strip().lower()
    try:
        row = conn.execute(
            "UPDATE users SET email = %s WHERE user_id = %s "
            "RETURNING user_id, email, password_hash, name",
            (folded, user_id),
        ).fetchone()
        conn.commit()
    except psycopg.errors.UniqueViolation as exc:
        conn.rollback()
        raise DuplicateEmail(folded) from exc
    return User(*row) if row else None


def created_at(conn: psycopg.Connection, user_id: str) -> str | None:
    """When the account was made, ISO-8601, for the profile screen."""
    row = conn.execute(
        "SELECT created_at FROM users WHERE user_id = %s", (user_id,)
    ).fetchone()
    return row[0].isoformat() if row else None
