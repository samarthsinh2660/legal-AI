"""What the wire contracts refuse before anything is spent.

`min_length` counts characters, so a message of four spaces passed it. Found
by QA against the live stack on 2026-09-06: it queued a run, titled the
thread "   ", and spent a full research turn -- two model calls and a
minute of the thread's one run slot -- on nothing a reader had asked. The
same hole was open on case titles and profile names.

Refusing it here is the cheapest of the places it could be caught, and the
only one where the client learns why.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.accounts.schemas import RenameRequest
from api.cases.schemas import NewCaseRequest, UpdateCaseRequest
from api.threads.schemas import MessageRequest, NewThreadRequest, RenameThreadRequest


@pytest.mark.parametrize("blank", ["", " ", "   \n\t  ", "  "])
def test_a_message_of_only_whitespace_is_refused(blank):
    with pytest.raises(ValidationError):
        MessageRequest(message=blank)


def test_a_real_message_keeps_its_own_shape():
    """Only the ends are trimmed. What is inside is the user's own words."""
    request = MessageRequest(message="  can I get a refund?\n\nthe flat is late  ")
    assert request.message == "can I get a refund?\n\nthe flat is late"


def test_a_message_at_the_ceiling_is_accepted():
    assert len(MessageRequest(message="x" * 4000).message) == 4000


def test_a_message_past_the_ceiling_is_refused():
    with pytest.raises(ValidationError):
        MessageRequest(message="x" * 4001)


def test_padding_does_not_smuggle_a_message_past_the_ceiling():
    """Trimming happens before the length check, or 4000 characters plus
    spaces would be rejected while meaning the same thing."""
    assert len(MessageRequest(message="  " + "x" * 4000 + "  ").message) == 4000


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_title_of_only_whitespace_is_refused(blank):
    """A sidebar row with no visible text cannot be clicked back to."""
    with pytest.raises(ValidationError):
        RenameThreadRequest(title=blank)


def test_a_title_is_trimmed():
    assert RenameThreadRequest(title="  Refund question  ").title == "Refund question"


def test_a_new_thread_may_still_have_no_title():
    """None is how a caller says "use the default"; a blank string is not."""
    assert NewThreadRequest(title=None).title is None
    with pytest.raises(ValidationError):
        NewThreadRequest(title="   ")


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_case_title_of_only_whitespace_is_refused(blank):
    """A matter with no visible name cannot be found again."""
    with pytest.raises(ValidationError):
        NewCaseRequest(title=blank)
    with pytest.raises(ValidationError):
        UpdateCaseRequest(title=blank)


def test_a_patch_that_names_no_title_still_validates():
    """Every field on a PATCH is optional; absent is not blank."""
    assert UpdateCaseRequest().title is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_profile_name_of_only_whitespace_is_refused(blank):
    with pytest.raises(ValidationError):
        RenameRequest(name=blank)


def test_a_password_is_not_trimmed():
    """A password may begin or end with a space. Stripping one would
    silently change the credential and lock the account out."""
    from api.accounts.schemas import RegisterRequest

    padded = " " + "x" * 12 + " "
    assert RegisterRequest(email="a@b.co", password=padded).password == padded
