"""`Ok` / `Failure`, and every error this API can return.

Expected outcomes are values, not exceptions. A raise is invisible in a
signature, unwinds past the code that knows what to say, and carries text --
a DSN, a stack trace -- that must never reach a client. `Failure` has
nowhere to put a cause, so it cannot leak one.

Genuine bugs still raise; the router catches them once and answers 500.

The constructors below exist so two routers cannot spell the same condition
two ways.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Ok:
    """A success, and what it produced. `value` is None for a check that
    only had to pass."""

    value: Any = None


@dataclass(frozen=True)
class Failure:
    """An expected failure.

    `code` is what a client branches on; `message` is for whoever made the
    request; `status` is decided here so the router's mapping is a lookup.

    No field for a cause, deliberately: an exception object this far out is
    one f-string away from a response body.
    """

    code: str
    message: str
    status: int


Result = Ok | Failure


def invalid_request(detail: str) -> Failure:
    """A malformed body. `detail` is built only from what the client sent."""
    return Failure(code="invalid_request", message=detail, status=400)


def unauthorized() -> Failure:
    """No usable credential. One message for missing, expired, forged and
    malformed alike."""
    return Failure(
        code="not_authenticated",
        message="A valid bearer token is required.",
        status=401,
    )


def invalid_credentials() -> Failure:
    """Login failed. Identical for an unknown address and a wrong password."""
    return Failure(
        code="invalid_credentials",
        message="Email or password is incorrect.",
        status=401,
    )


def forbidden() -> Failure:
    """Authenticated, but not for this. A 401 says re-authenticate; this
    says do not bother."""
    return Failure(
        code="forbidden",
        message="This account may not access that resource.",
        status=403,
    )


def not_found(what: str = "resource") -> Failure:
    return Failure(code="not_found", message=f"No such {what}.", status=404)


def conflict(code: str, message: str) -> Failure:
    return Failure(code=code, message=message, status=409)


def rate_limited() -> Failure:
    return Failure(
        code="rate_limited",
        message="Too many requests. Slow down and retry.",
        status=429,
    )


def internal_error(message: str = "Request failed. See server logs.") -> Failure:
    """The failure nobody planned. Says nothing about what broke."""
    return Failure(code="internal_error", message=message, status=500)


def service_unavailable(code: str, message: str) -> Failure:
    """A dependency is unusable -- no signing secret, a store that is down."""
    return Failure(code=code, message=message, status=503)


def timeout(message: str) -> Failure:
    return Failure(code="timeout", message=message, status=504)
