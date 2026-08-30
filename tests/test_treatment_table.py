"""Treatment read from the reporter's own Case Law Reference table.

Supreme Court Reports print, at the end of the headnote, how the judgment
dealt with each authority it cites:

    [2020] 3 SCR 1      followed        Para 7.5
    [2014] 1 SCR 783    referred to     Para 2

Found in 36% of stored Supreme Court judgments (measured 2026-08-29 over an
800-judgment sample). Where it exists it beats a model outright: it is the
reporter's editorial classification, it costs nothing, and it cannot
hallucinate. The model is for the other 64%.

The mapping to our four treatments is the delicate part. "Relied on" is
following; "referred to" is not. "Held inapplicable" is distinguishing, not
overruling -- reading it as overruling would retire an authority that still
binds.
"""

from legal_ai.agents.treatment import Treatment
from legal_ai.ingestion.treatment_table import extract_treatment_table

HEADER = "Case Law Reference\n"


def _table(body: str) -> dict[str, Treatment]:
    from legal_ai.ingestion.citations import normalise_citation
    return {
        normalise_citation(c): t for c, t in extract_treatment_table(HEADER + body)
    }


def test_followed():
    assert _table("[2020] 3 SCR 1 followed Para 7.5")["20203SCR1"] is Treatment.FOLLOWED


def test_relied_on_is_following():
    """Relying on an authority is applying it, not merely noting it."""
    assert _table("[2012] 2 SCR 1127 relied on Para 15")["20122SCR1127"] is Treatment.FOLLOWED


def test_referred_to_is_only_considered():
    """The reporter's commonest label, and the weakest: noted, not adopted."""
    assert _table("[2014] 1 SCR 783 referred to Para 2")["20141SCR783"] is Treatment.CONSIDERED


def test_overruled():
    assert _table("[1998] 1 SCR 50 overruled Para 9")["19981SCR50"] is Treatment.OVERRULED


def test_hyphenated_overruled():
    assert _table("[1998] 1 SCR 50 over-ruled Para 9")["19981SCR50"] is Treatment.OVERRULED


def test_distinguished():
    assert _table("[2001] 2 SCR 10 distinguished Para 4")["20012SCR10"] is Treatment.DISTINGUISHED


def test_held_inapplicable_is_distinguishing_not_overruling():
    """It confines the case, it does not retire it. Reading this as
    overruling would kill an authority that still binds."""
    result = _table("[2001] 2 SCR 10 held inapplicable Para 4")["20012SCR10"]
    assert result is Treatment.DISTINGUISHED
    assert not result.is_negative


def test_several_rows():
    body = (
        "[2020] 3 SCR 1 followed Para 7.5\n"
        "[2012] 2 SCR 1127 relied on Para 15.1\n"
        "[2012] 4 SCR 74 referred to Para 15.1"
    )
    table = _table(body)
    assert table["20203SCR1"] is Treatment.FOLLOWED
    assert table["20122SCR1127"] is Treatment.FOLLOWED
    assert table["20124SCR74"] is Treatment.CONSIDERED


def test_spacing_variants_in_the_reporter():
    assert _table("[2020] 3 S.C.R. 1 followed Para 7")["20203SCR1"] is Treatment.FOLLOWED


def test_a_judgment_without_the_table():
    assert extract_treatment_table("An ordinary judgment citing [2020] 3 SCR 1.") == []


def test_an_unknown_label_is_not_guessed():
    """A word the reporter uses that we have not mapped must be skipped,
    never defaulted to FOLLOWED."""
    assert extract_treatment_table(HEADER + "[2020] 3 SCR 1 obliterated Para 7") == []


def test_empty():
    assert extract_treatment_table("") == []


def test_the_strongest_label_wins_when_a_case_appears_twice():
    """A judgment may refer to a case in one paragraph and overrule it in
    another. The overruling is the one that matters."""
    body = "[2020] 3 SCR 1 referred to Para 2\n[2020] 3 SCR 1 overruled Para 9"
    assert _table(body)["20203SCR1"] is Treatment.OVERRULED


# --- unlabelled entries in the citation block -------------------------------

CITED_BLOCK = "Case Law Cited\n"


def test_an_unlabelled_citation_in_the_block_is_considered():
    """The reporter labels a treatment when there is one. A case listed in
    the citation block with no label was cited and neither adopted nor
    doubted, which is exactly CONSIDERED."""
    text = CITED_BLOCK + "Sarla Verma v. DTC [2009] 5 SCR 1098 : (2009) 6 SCC 121."
    assert _table(text)["20095SCR1098"] is Treatment.CONSIDERED


def test_a_label_still_wins_inside_the_block():
    text = CITED_BLOCK + "Pune Municipal Corporation [2014] 1 SCR 783 - overruled."
    assert _table(text)["20141SCR783"] is Treatment.OVERRULED


def test_the_alternate_block_heading_is_recognised():
    text = (
        "LIST OF CITATIONS AND OTHER REFERENCES\n"
        "Indore Development Authority [2020] 3 SCR 1 : (2020) 8 SCC 129."
    )
    assert _table(text)["20203SCR1"] is Treatment.CONSIDERED


def test_citations_outside_any_block_are_not_classified():
    """Body prose is where the model is needed. Assuming CONSIDERED for
    every citation in a judgment would let good_law report 'no negative
    treatment' from an assumption rather than a reading."""
    text = "In the course of argument counsel referred to [2009] 5 SCR 1098 at length."
    assert extract_treatment_table(text) == []


def test_a_judgment_with_neither_block_nor_table():
    assert extract_treatment_table("Plain judgment text with no headnote.") == []
