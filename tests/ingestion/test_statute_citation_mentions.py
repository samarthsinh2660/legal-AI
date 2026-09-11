"""How often a judgment invokes a section, not merely whether it does.

The defect this fixes: CITES_SECTION was created from a single regex hit, so
a money-laundering judgment that mentions NI Act s.138 once in passing became
an edge indistinguishable from a cheque-dishonour case that turns on it. Ask
for the leading authorities on s.138 and the passing mention could outrank
them, because "mentions" and "is about" were the same edge.

A count is the cheapest signal that separates them, and it is already in the
text -- the extractor was discarding it during de-duplication.
"""

import pytest

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


# --- a year written once carries to the references that follow -----------


def test_a_reference_without_a_year_takes_the_one_the_judgment_wrote():
    # Judgments name the Act in full once and shorten it after. The later
    # references are the same Act, and "Arbitration Act" alone is two
    # different laws -- 1940 and 1996.
    text = (
        "An application under Section 34 of the Arbitration Act, 1996 was filed. "
        "The court held that Section 11 of the Arbitration Act permits it."
    )
    refs = {r.section_number: r for r in extract_section_references(text)}
    assert refs["34"].act_year == "1996"
    assert refs["11"].act_year == "1996"


def test_the_year_survives_when_the_bare_mention_comes_first():
    # De-duplication keeps the first match; the year must not be lost just
    # because the reference without it happened to appear earlier.
    text = (
        "Section 34 of the Arbitration Act was invoked. Later the court read "
        "Section 34 of the Arbitration Act, 1996 again."
    )
    (ref,) = extract_section_references(text)
    assert ref.act_year == "1996"


def test_two_years_for_one_name_leave_the_bare_mention_unresolved():
    # A judgment written across the Companies Act transition names both. A
    # bare "Companies Act" could be either, so it takes neither.
    text = (
        "Section 391 of the Companies Act, 1956 and Section 230 of the "
        "Companies Act, 2013 were compared. Section 7 of the Companies Act applies."
    )
    refs = {r.section_number: r for r in extract_section_references(text)}
    assert refs["391"].act_year == "1956"
    assert refs["230"].act_year == "2013"
    assert refs["7"].act_year is None


# --- the 2023 criminal codes, which are not named "Act" or "Code" ---------


@pytest.mark.parametrize("text, name", [
    ("Section 318 of the Bharatiya Nyaya Sanhita, 2023", "Bharatiya Nyaya Sanhita"),
    ("Section 480 of the Bharatiya Nagarik Suraksha Sanhita", "Bharatiya Nagarik Suraksha Sanhita"),
    ("Section 63 of the Bharatiya Sakshya Adhiniyam, 2023", "Bharatiya Sakshya Adhiniyam"),
])
def test_a_2023_code_named_in_full_is_found(text, name):
    # They end in "Sanhita" and "Adhiniyam". A pattern that required "Act"
    # or "Code" found none of the 90 judgments that name them in full.
    (ref,) = extract_section_references(text)
    assert ref.act_name == name


@pytest.mark.parametrize("text, abbreviation", [
    ("Section 318 BNS", "BNS"),
    ("u/s 482 BNSS", "BNSS"),
    ("certificate U/s 63 BSA", "BSA"),
])
def test_a_2023_code_abbreviated_is_found(text, abbreviation):
    (ref,) = extract_section_references(text)
    assert ref.act_name == abbreviation
