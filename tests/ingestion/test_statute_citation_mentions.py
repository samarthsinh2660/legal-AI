"""How often a judgment invokes a section, not merely whether it does.

The defect this fixes: CITES_SECTION was created from a single regex hit, so
a money-laundering judgment that mentions NI Act s.138 once in passing became
an edge indistinguishable from a cheque-dishonour case that turns on it. Ask
for the leading authorities on s.138 and the passing mention could outrank
them, because "mentions" and "is about" were the same edge.

A count is the cheapest signal that separates them, and it is already in the
text -- the extractor was discarding it during de-duplication.
"""

from legal_ai.ingestion.statute_citations import extract_section_references


def _by_number(text: str) -> dict[str, int]:
    return {r.section_number: r.mentions for r in extract_section_references(text)}


def test_a_single_mention_counts_once():
    text = "The appellant relied on Section 18 of the Real Estate Act, 2016."
    assert _by_number(text)["18"] == 1


def test_repeated_mentions_accumulate():
    text = (
        "Section 138 of the Negotiable Instruments Act, 1881 is the charging "
        "provision. Section 138 of the Negotiable Instruments Act, 1881 requires "
        "notice. The scheme of Section 138 of the Negotiable Instruments Act, "
        "1881 is therefore complete."
    )
    assert _by_number(text)["138"] == 3


def test_the_reference_is_still_returned_once():
    """Counting must not turn one section into three separate references."""
    one = "Section 138 of the Negotiable Instruments Act, 1881. "
    refs = [r for r in extract_section_references(one * 3) if r.section_number == "138"]
    assert len(refs) == 1


def test_different_sections_are_counted_separately():
    act = "the Negotiable Instruments Act, 1881"
    text = (
        f"Section 138 of {act} applies. Section 138 of {act} again. "
        f"Section 141 of {act} is different."
    )
    counts = _by_number(text)
    assert counts["138"] == 2
    assert counts["141"] == 1


def test_abbreviated_form_is_counted_too():
    text = "Charged u/s 302 IPC. The ingredients of Section 302 IPC are settled."
    assert _by_number(text)["302"] == 2


def test_no_references():
    assert extract_section_references("A judgment about nothing in particular.") == []
