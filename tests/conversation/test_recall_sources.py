"""A composed follow-up keeps the links of the answers it was composed from.

Without this the ANSWER route produced claims and evidence ids but no
source links, so the screen fell back to printing bare identifiers -- a
follow-up looked materially worse than the answer behind it, for no reason
the reader could see.
"""

from __future__ import annotations

from legal_ai.conversation.recall import _sources_for

STORED = [
    {
        "sources": [
            {"document_id": "act:crpc-1973:sec-438", "title": "Direction for bail",
             "url": "https://indiacode.gov.in/handle/1", "openable": True},
            {"document_id": "judgment:lavesh", "title": "LAVESH v STATE",
             "citation": "[2012] 7 S.C.R. 469", "court": "Supreme Court of India",
             "url": "https://x/tar/2012.tar", "openable": False},
        ]
    }
]


def test_a_carried_id_keeps_its_link():
    found = {s.document_id: s for s in _sources_for(STORED, {"act:crpc-1973:sec-438"})}
    assert found["act:crpc-1973:sec-438"].url == "https://indiacode.gov.in/handle/1"
    assert found["act:crpc-1973:sec-438"].openable is True


def test_a_link_that_was_not_openable_stays_that_way():
    """Copied, never re-derived: an archive URL must not become a link
    because this pass had no Evidence to test it against."""
    found = {s.document_id: s for s in _sources_for(STORED, {"judgment:lavesh"})}
    assert found["judgment:lavesh"].openable is False
    assert found["judgment:lavesh"].citation == "[2012] 7 S.C.R. 469"


def test_an_id_the_composition_dropped_brings_no_link():
    assert _sources_for(STORED, {"act:crpc-1973:sec-438"}) == tuple(
        s for s in _sources_for(STORED, {"act:crpc-1973:sec-438"})
    )
    assert all(s.document_id != "judgment:lavesh"
               for s in _sources_for(STORED, {"act:crpc-1973:sec-438"}))


def test_the_later_turn_wins_when_a_document_was_stored_twice():
    """The most recent link is the one most recently checked."""
    older = {"sources": [{"document_id": "d", "title": "Old", "openable": False}]}
    newer = {"sources": [{"document_id": "d", "title": "New", "openable": True}]}
    found = _sources_for([older, newer], {"d"})
    assert len(found) == 1
    assert found[0].title == "New"


def test_a_malformed_stored_source_is_skipped_not_raised():
    """A turn stored by an older shape must not break a follow-up."""
    assert _sources_for([{"sources": ["not-a-dict", None]}], {"d"}) == ()
    assert _sources_for([{}], {"d"}) == ()
