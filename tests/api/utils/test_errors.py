"""The error catalogue.

It exists so two routers cannot spell the same condition two ways, and so
the full set of what a client may receive can be read in one place. These
tests pin the parts a client actually depends on: that a `code` is stable
enough to branch on, and that two conditions which must be indistinguishable
stay indistinguishable.
"""

from api.utils.errors import (
    Failure,
    Ok,
    conflict,
    forbidden,
    internal_error,
    invalid_credentials,
    invalid_request,
    not_found,
    rate_limited,
    service_unavailable,
    timeout,
    unauthorized,
)

ALL = [
    invalid_request("x"),
    unauthorized(),
    invalid_credentials(),
    forbidden(),
    not_found(),
    conflict("taken", "x"),
    rate_limited(),
    internal_error(),
    service_unavailable("down", "x"),
    timeout("x"),
]


def test_every_failure_carries_a_code_a_message_and_a_status():
    for failure in ALL:
        assert isinstance(failure, Failure)
        assert failure.code and failure.message and failure.status


def test_statuses_are_in_the_error_range():
    for failure in ALL:
        assert 400 <= failure.status < 600


def test_a_failure_has_nowhere_to_put_an_exception():
    """The property that keeps a DSN or a traceback out of a response body.
    If a field is ever added for a cause, this is the test that should
    stop it."""
    assert set(Failure.__dataclass_fields__) == {"code", "message", "status"}


def test_unauthenticated_and_bad_credentials_are_different_codes():
    """A client shown 401 on /auth/me should re-authenticate; one shown 401
    from a login should re-prompt. Same status, different meaning."""
    assert unauthorized().code != invalid_credentials().code


def test_forbidden_is_not_unauthorized():
    """403 tells a client not to retry with the same credential; 401 tells
    it to get a new one. Collapsing them makes a UI loop."""
    assert forbidden().status == 403
    assert unauthorized().status == 401


def test_internal_error_says_nothing_about_what_broke():
    message = internal_error().message.lower()
    for leak in ("traceback", "exception", "postgres", "psycopg", "line "):
        assert leak not in message


def test_invalid_request_carries_the_detail_it_was_given():
    """The one message built from caller input -- it names the offending
    field, and is assembled only from what the client sent."""
    assert "question" in invalid_request("question: Field required").message


def test_ok_carries_a_value_and_defaults_to_none():
    assert Ok().value is None
    assert Ok("token").value == "token"


def test_ok_and_failure_are_distinguishable_by_type():
    """The whole no-throw convention rests on a caller being able to tell
    these apart with isinstance."""
    assert isinstance(Ok(), Ok) and not isinstance(Ok(), Failure)
    assert isinstance(unauthorized(), Failure) and not isinstance(unauthorized(), Ok)
