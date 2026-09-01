"""Signed access tokens.

A JWT whose `sub` claim is the user id. Stateless, and there is no
denylist behind it: once issued, a token works until `exp` and nothing can
withdraw it early. `LEGAL_AI_JWT_EXPIRES_IN` is therefore the only bound on
a leaked token, which is why it is a deployment setting and not a constant.

`algorithms=["HS256"]` is pinned at decode. A JWT names its own algorithm,
so a decoder that trusts the header will accept `alg: none` -- an unsigned
token with any payload the attacker likes.

A token with no `sub` is refused rather than returning None: a caller handed
None becomes nobody, and every "scope to this user" query reads that as no
filter at all.
"""

from __future__ import annotations

import os
import time
import uuid

import jwt

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


def read_expiry() -> int:
    """How long a new token lives, in seconds, from the environment.

    Read per call so a deployment can shorten it without a rebuild. The
    fallback is a last resort for a missing variable, not the place to
    tune this -- set LEGAL_AI_JWT_EXPIRES_IN, which .env.example and
    docker-compose.yml both carry. A bad value degrades to the fallback
    rather than refusing to start, same as the pool sizes.
    """
    try:
        return int(os.environ.get("LEGAL_AI_JWT_EXPIRES_IN") or 86400)
    except ValueError:
        return 86400


def issue_access_token(
    user_id: str,
    secret: str,
    expires_in: int | None = None,
) -> str:
    """A signed token identifying `user_id`.

    Refuses a short secret: an unset variable must not become a token signed
    with the empty string.
    """
    if expires_in is None:
        expires_in = read_expiry()
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise ValueError(
            f"token secret must be at least {MIN_SECRET_BYTES} bytes"
        )
    claims = {
        "sub": user_id,
        "exp": int(time.time()) + expires_in,
        # Makes two tokens issued to one user in the same second
        # distinguishable, and is what a denylist would key on if one is
        # ever added.
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
    """Every verified claim, for a caller that needs more than the subject.

    Same refusals as `read_access_token`.
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
