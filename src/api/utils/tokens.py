"""Signed access tokens.

A JWT whose `sub` claim is the user id. Stateless, so there is no logout
that invalidates an already-issued token; expiry is the only bound.

`algorithms=["HS256"]` is pinned at decode. A JWT names its own algorithm,
so a decoder that trusts the header will accept `alg: none` -- an unsigned
token with any payload the attacker likes.

A token with no `sub` is refused rather than returning None: a caller handed
None becomes nobody, and every "scope to this user" query reads that as no
filter at all.
"""

from __future__ import annotations

import time
import uuid

import jwt

# One hour. Short enough that a leaked token is a bounded problem given
# there is no revocation, long enough that a working session does not
# re-authenticate mid-task.
DEFAULT_EXPIRY_SECONDS = 3600

_ALGORITHM = "HS256"

# RFC 7518 §3.2: an HMAC key for SHA-256 must be at least as long as the
# hash output. A shorter secret is brute-forcible offline by anyone holding
# one issued token, and PyJWT only warns about it. Enforced here so a
# deployment cannot start with a four-character secret and look healthy.
MIN_SECRET_BYTES = 32


class TokenError(Exception):
    """A token that cannot be trusted, for any reason.

    One exception, not several: they all mean the same thing to a caller.
    """


def issue_access_token(
    user_id: str,
    secret: str,
    expires_in: int = DEFAULT_EXPIRY_SECONDS,
) -> str:
    """A signed token identifying `user_id`.

    Refuses a short secret: an unset variable must not become a token signed
    with the empty string.
    """
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise ValueError(
            f"token secret must be at least {MIN_SECRET_BYTES} bytes"
        )
    claims = {
        "sub": user_id,
        "exp": int(time.time()) + expires_in,
        # Named so it can be revoked. Without it a logout could only
        # invalidate every token a user holds, or none.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def read_access_token(token: str, secret: str) -> str:
    """The user id in `token`, or TokenError.

    Never returns for an expired, forged, unsigned, malformed or
    subject-less token, so a returned id is authenticated. Revocation is
    checked by the caller, which has the database this does not.
    """
    if not secret:
        raise TokenError("no signing secret configured")
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    subject = claims.get("sub")
    if not subject or not isinstance(subject, str):
        raise TokenError("token carries no subject")
    return subject


def read_claims(token: str, secret: str) -> dict:
    """Every verified claim, for a caller that needs the `jti` as well.

    Same refusals as `read_access_token`; this returns the whole payload so
    the revocation check does not have to decode the token twice.
    """
    if not secret:
        raise TokenError("no signing secret configured")
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if not claims.get("sub") or not isinstance(claims["sub"], str):
        raise TokenError("token carries no subject")
    return claims
