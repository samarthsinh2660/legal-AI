"""Naming a code we do not hold.

The corpus holds the Bharatiya Nyaya Sanhita, Nagarik Suraksha Sanhita and
Sakshya Adhiniyam, and none of the three codes they replaced. An offence
committed before 1 July 2024 is still charged under the old code, so a
lawyer asking about IPC s.498A is asking a live question -- and search
answered it with unrelated near-misses instead of saying we do not hold it.
"""

from legal_ai.retrieval.coverage import coverage_note


def test_naming_the_penal_code_says_we_do_not_hold_it():
    note = coverage_note("What does Section 498A IPC require?")
    assert note
    assert "Indian Penal Code" in note
    assert "Bharatiya Nyaya Sanhita" in note


def test_the_spelled_out_name_is_recognised_too():
    assert coverage_note("section 302 of the Indian Penal Code")


def test_the_criminal_procedure_code_is_recognised():
    note = coverage_note("What does CrPC section 482 say?")
    assert note and "Bharatiya Nagarik Suraksha Sanhita" in note


def test_the_evidence_act_is_recognised():
    note = coverage_note("Section 65B of the Indian Evidence Act")
    assert note and "Bharatiya Sakshya Adhiniyam" in note


def test_the_note_says_the_old_code_still_governs_older_offences():
    """Without this the note reads as "that law is gone", which is wrong and
    would mislead on every pre-July-2024 matter."""
    note = coverage_note("IPC 420")
    assert "1 July 2024" in note or "before" in note.lower()


def test_a_question_naming_no_repealed_code_gets_no_note():
    for question in (
        "Can a homebuyer claim a refund under RERA?",
        "What does Section 138 of the Negotiable Instruments Act require?",
        "What is the limitation period for recovery of money?",
    ):
        assert coverage_note(question) is None, question


def test_naming_the_replacement_gets_no_note():
    """Asking about the code we DO hold is not a coverage gap."""
    assert coverage_note("What does BNS section 85 say about cruelty?") is None


def test_an_empty_question_is_not_a_gap():
    assert coverage_note("") is None
    assert coverage_note(None) is None
