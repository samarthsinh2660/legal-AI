"""Access tokens.

A signed JWT carrying one claim that matters: which user is asking. Every
protected route reads it and scopes its work to that id, so a token that
verifies when it should not is the whole system's authorisation gone at once.

The tests below are mostly about refusing things. That is the point: a token
check earns its keep by what it rejects, and each rejection here is a real
attack -- a forged signature, an expired session, an unsigned token whose
header claims no algorithm is needed.
"""

import time

import pytest

from api.utils.tokens import (
    TokenError,
    issue_access_token,
    read_access_token,
)

SECRET = "test-secret-not-a-real-one-but-long-enough-for-hs256"


def test_a_token_round_trips_to_its_user():
    token = issue_access_token("user-123", secret=SECRET)
    assert read_access_token(token, secret=SECRET) == "user-123"


def test_a_token_signed_with_another_secret_is_refused():
    """The forgery case. Anyone can write the payload; only the holder of
    the secret can sign it."""
    token = issue_access_token("user-123", secret="attacker-secret-also-32-bytes-or-more!!")
    with pytest.raises(TokenError):
        read_access_token(token, secret=SECRET)


def test_a_tampered_token_is_refused():
    token = issue_access_token("user-123", secret=SECRET)
    header, payload, signature = token.split(".")
    with pytest.raises(TokenError):
        read_access_token(f"{header}.{payload}x.{signature}", secret=SECRET)


def test_an_expired_token_is_refused():
    token = issue_access_token("user-123", secret=SECRET, expires_in=-1)
    with pytest.raises(TokenError):
        read_access_token(token, secret=SECRET)


def test_a_token_expires_at_the_configured_horizon():
    import jwt

    token = issue_access_token("user-123", secret=SECRET, expires_in=60)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert 55 < claims["exp"] - time.time() <= 60


def test_an_unsigned_token_is_refused():
    """alg=none is the classic JWT attack: a header asserting the token
    needs no signature. A library told to expect HS256 must not accept it."""
    import jwt

    token = jwt.encode({"sub": "user-123"}, key="", algorithm="none")
    with pytest.raises(TokenError):
        read_access_token(token, secret=SECRET)


def test_garbage_is_refused_rather_than_crashing():
    for junk in ("", "not-a-token", "a.b.c", "....."):
        with pytest.raises(TokenError):
            read_access_token(junk, secret=SECRET)


def test_a_token_without_a_subject_is_refused():
    """A validly signed token with no user in it must not authenticate a
    request. Returning None here would let a caller be nobody in
    particular, which every scoped query would then read as "no filter"."""
    import jwt

    token = jwt.encode({"exp": time.time() + 60}, SECRET, algorithm="HS256")
    with pytest.raises(TokenError):
        read_access_token(token, secret=SECRET)


def test_an_empty_secret_is_refused_at_issue():
    """No secret configured must not silently mean "sign with nothing"."""
    with pytest.raises(ValueError):
        issue_access_token("user-123", secret="")


def test_a_short_secret_is_refused_at_issue():
    """RFC 7518 wants >= 32 bytes for HS256; PyJWT only warns. A deployment
    started with a four-character secret would look perfectly healthy while
    every token it issues is brute-forcible offline."""
    with pytest.raises(ValueError):
        issue_access_token("user-123", secret="tooshort")


def test_an_empty_secret_is_refused_at_read():
    token = issue_access_token("user-123", secret=SECRET)
    with pytest.raises(TokenError):
        read_access_token(token, secret="")
