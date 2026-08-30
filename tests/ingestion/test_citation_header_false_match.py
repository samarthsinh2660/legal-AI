"""A page header is not a citation.

Every page of a Supreme Court Reports judgment is stamped with the volume it
appears in:

    858 SUPREME COURT REPORTS [2023] 2 S.C.R.

    20. However, in the year 2019, in United India Insurance...

The SCR pattern allowed any whitespace before the page number, so it read
across the line break and produced "[2023] 2 S.C.R. 20" -- a citation the
judgment never made, whose key collided with a real and unrelated case. That
produced a CITES edge between an arbitration judgment and a criminal one,
and the treatment classifier then read nearby prose about a different
overruling and marked the phantom edge OVERRULED. A live authority was
reported as doubted.

A reporter citation is printed on one line. Requiring that is the whole fix.
"""

from legal_ai.ingestion.citations import extract_citations


def test_a_page_header_followed_by_a_paragraph_number_is_not_a_citation():
    text = (
        "858 SUPREME COURT REPORTS [2023] 2 S.C.R.\n"
        "20. However, in the year 2019, this Court accepted an objection."
    )
    assert extract_citations(text) == []


def test_a_real_citation_on_one_line_still_matches():
    text = "This Court in Nikhil Chandra Mondal [2023] 2 S.C.R. 20 held otherwise."
    assert extract_citations(text) == ["[2023] 2 S.C.R. 20"]


def test_spacing_variants_on_one_line_still_match():
    assert extract_citations("see [2018] 13 SCR 1188 at 1190") == ["[2018] 13 SCR 1188"]
    assert extract_citations("see [2018] 13 S C R 1188.") == ["[2018] 13 S C R 1188"]


def test_a_citation_is_not_split_across_a_line_break():
    """Wrapping mid-citation is rarer than the header collision, and
    accepting it is what caused the collision. Losing a wrapped citation
    costs one edge; a phantom one costs a false overruling."""
    assert extract_citations("...[2023] 2 S.C.R.\n\n\n20 ...") == []


def test_other_reporters_are_unaffected():
    assert extract_citations("(2019) 8 SCC 729") == ["(2019) 8 SCC 729"]
