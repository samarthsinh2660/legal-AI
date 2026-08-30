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
    conn.commit()


def create_user(conn: psycopg.Connection, email: str, password_hash: str) -> User:
    """Insert a user, or raise DuplicateEmail.

    Takes an already-hashed password, so plaintext never reaches a query log.
    """
    folded = email.strip().lower()
    user_id = uuid.uuid4().hex
    try:
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash) VALUES (%s, %s, %s)",
            (user_id, folded, password_hash),
        )
        conn.commit()
    except psycopg.errors.UniqueViolation as exc:
        conn.rollback()
        raise DuplicateEmail(folded) from exc
    return User(user_id=user_id, email=folded, password_hash=password_hash)


def find_by_email(conn: psycopg.Connection, email: str) -> User | None:
    """The user with this address, hash included, or None.

    The only query returning a password hash -- authentication is its only
    caller. None rather than an exception, so a login can answer an unknown
    address exactly as it answers a wrong password.
    """
    row = conn.execute(
        "SELECT user_id, email, password_hash FROM users WHERE email = %s",
        (email.strip().lower(),),
    ).fetchone()
    return User(*row) if row else None


def find_by_id(conn: psycopg.Connection, user_id: str) -> User | None:
    """The user behind a verified token, or None if the account is gone."""
    row = conn.execute(
        "SELECT user_id, email, password_hash FROM users WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    return User(*row) if row else None
