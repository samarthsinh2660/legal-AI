"""Naming a code we do not hold.

There are none left. The IPC, the CrPC and the Indian Evidence Act were
all ingested by 2026-09-02, so the register is empty and every question
gets no note. The tests below hold that line, because a note sending a
reader to the BNS or the BSA for a section we now carry verbatim is a
worse error than no note at all.

The last test keeps the empty mechanism honest: it puts one entry back and
checks the sentence still reaches the caller, so the path does not rot
while unused.
"""

import re

import legal_ai.retrieval.coverage as coverage
from legal_ai.retrieval.coverage import coverage_note


def test_no_code_is_a_gap_any_more():
    assert coverage._REPEALED == ()


def test_the_evidence_act_is_no_longer_a_gap():
    assert coverage_note("Section 65B of the Indian Evidence Act") is None
    assert coverage_note("Indian Evidence Act 1872") is None


def test_the_penal_code_is_no_longer_a_gap():
    assert coverage_note("What does Section 498A IPC require?") is None
    assert coverage_note("section 302 of the Indian Penal Code") is None


def test_the_criminal_procedure_code_is_no_longer_a_gap():
    assert coverage_note("What does CrPC section 482 say?") is None
    assert coverage_note("anticipatory bail under the Code of Criminal Procedure") is None


def test_a_question_naming_no_repealed_code_gets_no_note():
    for question in (
        "Can a homebuyer claim a refund under RERA?",
        "What does Section 138 of the Negotiable Instruments Act require?",
        "What is the limitation period for recovery of money?",
    ):
        assert coverage_note(question) is None, question


def test_naming_a_replacement_gets_no_note():
    assert coverage_note("What does BSA section 63 say about electronic records?") is None


def test_an_empty_question_is_not_a_gap():
    assert coverage_note("") is None
    assert coverage_note(None) is None


def test_an_entry_still_produces_a_note(monkeypatch):
    monkeypatch.setattr(
        coverage,
        "_REPEALED",
        ((re.compile(r"\bcompanies act, 1956\b", re.IGNORECASE),
          "the Companies Act, 1956",
          "the Companies Act, 2013"),),
    )
    note = coverage_note("oppression under the Companies Act, 1956")
    assert note and "Companies Act, 2013" in note
    assert coverage_note("oppression under the Companies Act, 2013") is None
