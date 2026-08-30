"""Stage 3 -- quotation matching.

The check exists for one failure: a real case, correctly cited, quoted for
words it does not contain. Every earlier stage passes that, because the id
resolves and the document was genuinely retrieved.
"""

from legal_ai.verification.quotes import (
    MIN_QUOTE_CHARS,
    check_quotations,
    extract_quotations,
    normalise,
)

SECTION = (
    "18. Return of amount and compensation. If the promoter fails to complete "
    "or is unable to give possession of an apartment, he shall be liable on "
    "demand to return the amount received by him in respect of that apartment "
    "with interest at such rate as may be prescribed."
)
SOURCES = {"act:2158:sec-18": SECTION}


# ---------------------------------------------------------------- extraction

def test_a_quotation_is_found_in_the_cited_section():
    checks = check_quotations(
        'Section 18 requires the promoter "to return the amount received by him '
        'in respect of that apartment with interest".',
        SOURCES,
    )
    assert len(checks) == 1
    assert checks[0].found
    assert checks[0].document_id == "act:2158:sec-18"


def test_an_invented_quotation_is_caught():
    # The Delhi High Court failure: real source, words that are not in it.
    checks = check_quotations(
        'Section 18 provides that "the promoter shall forfeit the entire '
        'project and surrender all licences to the authority".',
        SOURCES,
    )
    assert checks[0].found is False
    assert checks[0].document_id is None


def test_curly_quotes_are_recognised():
    # PDFs and word processors produce these; missing them would silently
    # skip the check rather than fail it.
    checks = check_quotations(
        "Section 18 says “liable on demand to return the amount received "
        "by him in respect of that apartment”.",
        SOURCES,
    )
    assert len(checks) == 1 and checks[0].found


def test_line_breaks_in_the_source_do_not_defeat_a_match():
    wrapped = {"act:2158:sec-18": SECTION.replace(" ", "\n   ", 12)}
    checks = check_quotations(
        'It says "liable on demand to return the amount received by him".',
        wrapped,
    )
    assert checks[0].found


def test_case_differences_do_not_defeat_a_match():
    checks = check_quotations(
        'It says "LIABLE ON DEMAND TO RETURN THE AMOUNT RECEIVED BY HIM".',
        SOURCES,
    )
    assert checks[0].found


# ------------------------------------------------------------------- limits

def test_a_short_quotation_is_ignored():
    # "the promoter" would match thousands of sections; matching it proves
    # nothing, so it must not be treated as evidence of anything.
    assert extract_quotations('It says "the promoter" here.') == []


def test_the_minimum_is_long_enough_to_be_distinctive():
    assert MIN_QUOTE_CHARS >= 40


def test_a_paraphrase_produces_no_checks():
    # Nothing to string-match. Saying nothing is correct here -- the
    # semantic stage handles paraphrase, and inventing a verdict from a
    # check that did not run would be worse than deferring.
    assert check_quotations("Section 18 lets a buyer recover money.", SOURCES) == []


def test_a_quote_may_be_satisfied_by_any_cited_document():
    # A claim citing three sections and quoting one of them is correct.
    many = {"act:1:sec-1": "irrelevant text", "act:2158:sec-18": SECTION}
    checks = check_quotations(
        'It says "liable on demand to return the amount received by him".', many
    )
    assert checks[0].found and checks[0].document_id == "act:2158:sec-18"


def test_no_sources_means_nothing_is_found_rather_than_an_error():
    checks = check_quotations(
        'It says "liable on demand to return the amount received by him".', {}
    )
    assert checks[0].found is False


def test_punctuation_is_not_normalised_away():
    # Dropping punctuation would let "shall not" match "shall", inverting
    # the meaning of a section. Both must stay distinguishable.
    assert normalise("shall not return the amount") != normalise("shall return the amount")


def test_several_quotations_in_one_claim_are_each_checked():
    checks = check_quotations(
        'It says "liable on demand to return the amount received by him" and '
        'also "shall forfeit the entire project and surrender all licences".',
        SOURCES,
    )
    assert [c.found for c in checks] == [True, False]


def test_an_empty_claim_is_handled():
    assert check_quotations("", SOURCES) == []
