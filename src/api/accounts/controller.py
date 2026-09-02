"""Accounts: register, log in, identify the caller.

Validates, calls the repository, returns `Ok`/`Failure`. No SQL, no HTTP.

Login answers identically for an unknown address and a wrong password, and
hashes a dummy password on the unknown path so the two also take the same
time. Either difference would let an attacker enumerate accounts.

No signing secret configured rejects every request rather than admitting
them.
"""

from __future__ import annotations

import logging

import os

from fastapi import Header

from api.utils.passwords import hash_password, verify_password
from api.accounts.repository import (
    DuplicateEmail,
    User,
    create_user,
    ensure_account_schema,
    find_by_email,
    find_by_id,
)
from api.utils.tokens import TokenError, issue_access_token, read_access_token
from api.utils.errors import (
    Ok,
    Result,
    conflict,
    invalid_credentials,
    invalid_request,
    service_unavailable,
    unauthorized,
)

def _no_secret():
    return service_unavailable(
        "auth_unavailable", "Authentication is not configured on this server."
    )

log = logging.getLogger(__name__)


# Burned when the address is unknown, so that path costs the same as a
# wrong password. The value is irrelevant; the time it takes is the point.
_DUMMY_HASH = hash_password("timing-equaliser-never-a-real-password")


def _secret() -> str:
    return os.environ.get("LEGAL_AI_JWT_SECRET", "")


def register(conn, email: str, password: str) -> Result:
    """Create an account and return its user id.

    The length floor is product policy, not cryptography, so it lives here
    rather than in the hashing helper.
    """
    email = (email or "").strip()
    if "@" not in email or len(email) < 3:
        return invalid_request("A valid email is required.")
    if len(password or "") < 12:
        return invalid_request("Password must be at least 12 characters.")
    ensure_account_schema(conn)
    try:
        user = create_user(conn, email, hash_password(password))
    except DuplicateEmail:
        # An enumeration surface by nature: the caller has to be told the
        # address is taken. Rate limiting is the mitigation.
        return conflict("email_taken", "An account with that email already exists.")
    return Ok(user.user_id)


def login(conn, email: str, password: str) -> Result:
    """Verify credentials and return a signed access token.

    Sign-ins are audited here rather than in `middleware.audit`, which is
    where every other event is recorded. It has to be: `/auth/login` is a
    public path, so nobody is attached to the request by the time the
    middleware runs, and this is the only place that learns who the
    attempt was for.
    """
    if not _secret():
        return _no_secret()
    ensure_account_schema(conn)
    user = find_by_email(conn, email or "")
    if user is None:
        # Hash anyway: returning early here is a timing oracle for which
        # addresses exist, however identical the response text is.
        verify_password(password or "", _DUMMY_HASH)
        # Nothing is recorded: there is no account to attribute it to, and
        # a row keyed by the address would turn the trail into a register
        # of who does *not* have an account here.
        return invalid_credentials()
    if not verify_password(password or "", user.password_hash):
        _audit(conn, user.user_id, 401)
        return invalid_credentials()
    _audit(conn, user.user_id, 200)
    return Ok(issue_access_token(user.user_id, secret=_secret()))


def _audit(conn, user_id: str, status: int) -> None:
    """Record a sign-in attempt. Written before the reply, on purpose.

    This costs the known-address branch about 5ms that the unknown-address
    branch does not pay (61.8ms against 57.0ms, measured 2026-09-02), which
    is a weak account-enumeration oracle of the kind `_DUMMY_HASH` exists
    to close. It is accepted rather than removed: `POST /auth/register`
    already answers the same question outright with a 409, so the timing
    tells an attacker nothing new -- and writing the row in a background
    thread to equalise it would lose sign-in events whenever the process
    stopped, which is the one thing an audit trail may not do.

    No ensure_audit_schema: `CREATE TABLE IF NOT EXISTS` takes a lock even
    when it does nothing, and this is the hottest unauthenticated route --
    CLAUDE.md section 8. Startup creates the table.

    A failure here must not stop the sign-in; the gap is loud in the logs.
    """
    from api.audit.repository import record

    try:
        record(conn, user_id, "sign-in", "account", None, status)
    except Exception:
        log.error("audit: could not record sign-in for %s", user_id, exc_info=True)


def current_user_id(authorization: str = Header(default="")) -> Result:
    """The authenticated user id, from an `Authorization: Bearer` header."""
    if not _secret():
        return _no_secret()
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return unauthorized()
    try:
        return Ok(read_access_token(token, secret=_secret()))
    except TokenError:
        # Expired, forged, unsigned and malformed all answer the same.
        return unauthorized()


def user_for(conn, user_id: str) -> User | None:
    """The account behind an already-verified token id."""
    return find_by_id(conn, user_id)
