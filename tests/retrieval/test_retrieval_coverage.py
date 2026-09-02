"""Naming a code we do not hold.

The corpus holds the Bharatiya Sakshya Adhiniyam and not the Indian
Evidence Act it replaced. An offence committed before 1 July 2024 is still
tried under the old law, so a lawyer asking about s.65B is asking a live
question -- and search answered it with unrelated near-misses instead of
saying we do not hold it.

The IPC and the CrPC were ingested on 2026-09-02, so naming either is no
longer a gap; the tests below hold that line, because a note sending a
reader to the BNS for a section we now carry verbatim is a worse error
than no note at all.
"""

from legal_ai.retrieval.coverage import coverage_note


def test_the_evidence_act_is_recognised():
    note = coverage_note("Section 65B of the Indian Evidence Act")
    assert note and "Bharatiya Sakshya Adhiniyam" in note


def test_the_note_says_the_old_code_still_governs_older_offences():
    """Without this the note reads as "that law is gone", which is wrong and
    would mislead on every pre-July-2024 matter."""
    note = coverage_note("Indian Evidence Act 1872")
    assert "1 July 2024" in note or "before" in note.lower()


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


def test_naming_the_replacement_gets_no_note():
    """Asking about the code we DO hold is not a coverage gap."""
    assert coverage_note("What does BSA section 63 say about electronic records?") is None


def test_an_empty_question_is_not_a_gap():
    assert coverage_note("") is None
    assert coverage_note(None) is None
