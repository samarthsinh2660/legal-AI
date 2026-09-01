"""Uploading a case's own documents.

Cross-domain: documents x case.

The refusals matter more than the happy path. A file that cannot be read
must fail at upload, while the user is looking at it -- storing it silently
gives the Document Agent an empty exhibit and the user a thinner answer an
hour later with nothing to explain it.

Uploads go to `case_files`, never `documents`: a client's pleading is theirs,
not corpus, and must never come back from a search someone else runs.
"""

import pytest

from api.documents.controller import files_for, upload
from api.databases.postgres import connection
from api.utils.errors import Failure, Ok
from legal_ai.case.files import ensure_case_file_schema
from legal_ai.case.store import create_case, ensure_case_schema

CASE = "test-case-docs"
OWNER = "test-owner"
STRANGER = "test-stranger"


@pytest.fixture(autouse=True)
def case():
    with connection() as conn:
        ensure_case_schema(conn)
        ensure_case_file_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id LIKE 'test-case-%'")
        conn.commit()
        create_case(conn, case_id=CASE, title="Patel v. Shah")
        conn.execute("UPDATE cases SET user_id = %s WHERE case_id = %s", (OWNER, CASE))
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM cases WHERE case_id LIKE 'test-case-%'")
        conn.commit()


def test_a_text_file_is_stored_and_listed():
    with connection() as conn:
        result = upload(conn, CASE, OWNER, "notice.txt", b"The notice dated 12 May 2019.")
        assert isinstance(result, Ok)
        listed = files_for(conn, CASE, OWNER).value
    assert result.value["filename"] == "notice.txt"
    assert any(f["filename"] == "notice.txt" for f in listed)


def test_an_unknown_case_is_refused():
    """Attaching to a matter that does not exist is a silent orphan --
    nothing would ever look for it again."""
    with connection() as conn:
        result = upload(conn, "no-such-case", OWNER, "a.txt", b"text")
    assert isinstance(result, Failure) and result.status == 404


def test_an_unsupported_type_is_refused():
    with connection() as conn:
        result = upload(conn, CASE, OWNER, "photo.jpeg", b"\xff\xd8\xff")
    assert isinstance(result, Failure) and result.status == 400
    assert "jpeg" in result.message.lower()


def test_a_file_with_no_extension_is_refused():
    with connection() as conn:
        assert isinstance(upload(conn, CASE, OWNER, "noextension", b"text"), Failure)


def test_an_empty_file_is_refused():
    with connection() as conn:
        assert isinstance(upload(conn, CASE, OWNER, "empty.txt", b""), Failure)


def test_a_file_with_no_text_layer_is_refused():
    """A scan without OCR. Storing it would hand the Document Agent an empty
    exhibit and give no sign why the answer got thinner."""
    with connection() as conn:
        result = upload(conn, CASE, OWNER, "scan.txt", b"   \n\t  ")
    assert isinstance(result, Failure)
    assert "scan" in result.message.lower() or "no text" in result.message.lower()


def test_an_oversized_file_is_refused():
    from api.documents.controller import MAX_UPLOAD_BYTES

    with connection() as conn:
        result = upload(conn, CASE, OWNER, "big.txt", b"x" * (MAX_UPLOAD_BYTES + 1))
    assert isinstance(result, Failure) and result.status == 400


def test_the_error_does_not_leak_library_internals():
    """A parser's own message names paths and byte offsets."""
    with connection() as conn:
        result = upload(conn, CASE, OWNER, "broken.pdf", b"not really a pdf at all")
    assert isinstance(result, Failure)
    for leak in ("traceback", "/home/", "pypdf", "line "):
        assert leak not in result.message.lower()


def test_re_uploading_replaces_rather_than_duplicates():
    """A user correcting a bad scan must not end up with two exhibits."""
    with connection() as conn:
        upload(conn, CASE, OWNER, "deed.txt", b"first version")
        upload(conn, CASE, OWNER, "deed.txt", b"corrected version")
        listed = files_for(conn, CASE, OWNER).value
    assert len([f for f in listed if f["filename"] == "deed.txt"]) == 1


def test_the_upload_never_reaches_the_corpus():
    """The rule that keeps a client's pleading out of everyone's search."""
    with connection() as conn:
        upload(conn, CASE, OWNER, "private.txt", b"privileged and confidential")
        found = conn.execute(
            "SELECT count(*) FROM documents WHERE full_text LIKE %s",
            ("%privileged and confidential%",),
        ).fetchone()[0]
    assert found == 0


def test_listing_an_unknown_case_is_refused():
    with connection() as conn:
        assert isinstance(files_for(conn, "no-such-case", OWNER), Failure)


def test_a_stranger_cannot_upload_to_the_case():
    """The hole this closes: authentication said who you are, nothing said
    which matters are yours."""
    with connection() as conn:
        result = upload(conn, CASE, STRANGER, "intrusion.txt", b"text")
    assert isinstance(result, Failure) and result.status == 404


def test_a_stranger_cannot_list_the_documents():
    with connection() as conn:
        upload(conn, CASE, OWNER, "deed.txt", b"the 1998 deed")
        assert isinstance(files_for(conn, CASE, STRANGER), Failure)


def test_an_unowned_case_belongs_to_nobody():
    """Rows that predate accounts are unreachable through the API rather
    than public."""
    with connection() as conn:
        create_case(conn, case_id="test-case-orphan", title="Legacy")
        assert isinstance(upload(conn, "test-case-orphan", OWNER, "a.txt", b"x"), Failure)
